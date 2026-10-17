"""Detection orchestrator: run all detectors, score, build cases, persist.

Loads a dataset from the DB, builds the graph, runs every detector, assigns
deterministic alert and case IDs, scores accounts and groups cases, then
persists a ``detection_run`` with its alerts, cases and case-account rows.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from core.config import Rules, load_rules
from core.db import init_db, session_scope
from core.detection.cycles import detect_cycles
from core.detection.fan_patterns import detect_fan_in, detect_fan_out
from core.detection.graph_builder import GraphBundle, RawAlert, TxnRecord, build_graph
from core.detection.passthrough import detect_passthrough
from core.detection.shared_ids import detect_shared_ids
from core.models import (
    Account,
    AlertRow,
    CaseAccount,
    CaseRow,
    DetectionRun,
    Identifier,
    Transaction,
)
from core.schemas import Alert, RunSummary
from core.scoring.cases import build_cases
from core.scoring.risk import score_accounts
from core.utils import utcnow


def load_bundle(dataset_id: str) -> GraphBundle:
    """Load accounts, transactions and identifiers for a dataset into a bundle."""
    init_db()
    with session_scope() as session:
        accounts = session.query(Account).all()
        account_type = {a.account_id: a.account_type for a in accounts}
        txn_rows = (
            session.query(Transaction)
            .filter(Transaction.dataset_id == dataset_id)
            .all()
        )
        txns = [
            TxnRecord(
                txn_id=t.txn_id, sender_id=t.sender_id, receiver_id=t.receiver_id,
                amount=t.amount, ts=t.ts, ip=t.ip, device_id=t.device_id,
            )
            for t in txn_rows
        ]
        ident_rows = session.query(Identifier).all()
        identifiers = [(i.account_id, i.id_type, i.value) for i in ident_rows]
    return build_graph(txns, account_type, identifiers)


def _assign_alert_ids(raw: list[RawAlert]) -> list[Alert]:
    """Sort raw alerts deterministically and assign ``AL-0001`` ids."""
    raw_sorted = sorted(raw, key=lambda a: (a.pattern, tuple(a.accounts), tuple(a.txn_ids)))
    alerts: list[Alert] = []
    for i, r in enumerate(raw_sorted, start=1):
        alerts.append(
            Alert(alert_id=f"AL-{i:04d}", pattern=r.pattern, accounts=r.accounts,
                  txn_ids=r.txn_ids, total_amount=r.total_amount, reason=r.reason,
                  severity=r.severity)
        )
    return alerts


def _suppress_subsumed_passthrough(raw: list[RawAlert]) -> list[RawAlert]:
    """Drop pass-through alerts fully covered by a cycle alert.

    A pass-through hub inside a cycle is already explained by the cycle alert
    (ARCHITECTURE §7a: a pass-through can sit inside a cycle). Removing the
    redundant alert keeps precision and the case graph clean without losing the
    account from the case (the cycle alert still carries it).
    """
    cycle_account_sets = [set(a.accounts) for a in raw if a.pattern == "cycle"]
    kept: list[RawAlert] = []
    for alert in raw:
        if alert.pattern == "passthrough":
            accts = set(alert.accounts)
            if any(accts <= cyc for cyc in cycle_account_sets):
                continue
        kept.append(alert)
    return kept


def run_all_detectors(bundle: GraphBundle, rules: Rules) -> list[Alert]:
    """Run every detector and return alerts with stable IDs."""
    raw: list[RawAlert] = []
    raw += detect_cycles(bundle, rules)
    raw += detect_fan_in(bundle, rules)
    raw += detect_fan_out(bundle, rules)
    raw += detect_shared_ids(bundle, rules)
    raw += detect_passthrough(bundle, rules)
    raw = _suppress_subsumed_passthrough(raw)
    return _assign_alert_ids(raw)


def run_detection(dataset_id: str = "demo_seed42", rules: Rules | None = None,
                  persist: bool = True) -> RunSummary:
    """Run the full detection pipeline over a dataset and persist the results."""
    rules = rules or load_rules()
    started = utcnow()
    t0 = time.perf_counter()

    bundle = load_bundle(dataset_id)
    alerts = run_all_detectors(bundle, rules)
    account_risk = score_accounts(bundle, alerts, rules)
    cases, case_to_alerts = build_cases(alerts, account_risk, rules)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    run_id = f"RUN_{dataset_id}"

    by_pattern: dict[str, int] = {}
    for a in alerts:
        by_pattern[a.pattern] = by_pattern.get(a.pattern, 0) + 1

    if persist:
        _persist_run(run_id, started, dataset_id, bundle, alerts, cases,
                     case_to_alerts, account_risk, duration_ms, rules)

    return RunSummary(
        run_id=run_id, n_txns=len(bundle.txns), n_accounts=len(bundle.account_type),
        duration_ms=duration_ms, n_alerts=len(alerts), n_cases=len(cases),
        alerts_by_pattern=by_pattern,
    )


def _persist_run(run_id: str, started: datetime, dataset_id: str, bundle: GraphBundle,
                 alerts: list[Alert], cases, case_to_alerts, account_risk,
                 duration_ms: int, rules: Rules) -> None:
    """Write the run, alerts, cases and case-account rows (overwriting prior run)."""
    with session_scope() as session:
        # Clear any previous run for this dataset for repeatable demos.
        session.query(CaseAccount).filter(
            CaseAccount.case_id.in_(
                session.query(CaseRow.case_id).filter(CaseRow.run_id == run_id)
            )
        ).delete(synchronize_session=False)
        session.query(CaseRow).filter(CaseRow.run_id == run_id).delete()
        session.query(AlertRow).filter(AlertRow.run_id == run_id).delete()
        session.query(DetectionRun).filter(DetectionRun.run_id == run_id).delete()
        session.flush()

        session.add(DetectionRun(
            run_id=run_id, started_at=started,
            params_json=json.dumps({"dataset_id": dataset_id, "rules_version": rules.version}),
            n_txns=len(bundle.txns), duration_ms=duration_ms,
        ))
        session.bulk_insert_mappings(AlertRow, [
            {
                "alert_id": a.alert_id, "run_id": run_id, "pattern": a.pattern,
                "accounts_json": json.dumps(a.accounts), "txn_ids_json": json.dumps(a.txn_ids),
                "total_amount": a.total_amount, "reason": a.reason, "severity": a.severity,
            }
            for a in alerts
        ])
        session.bulk_insert_mappings(CaseRow, [
            {
                "case_id": c.case_id, "run_id": run_id, "title": c.title, "score": c.score,
                "status": c.status, "patterns_json": json.dumps(c.patterns),
                "accounts_json": json.dumps(c.accounts), "total_amount": c.total_amount,
                "n_txns": c.n_txns, "created_at": started,
            }
            for c in cases
        ])
        ca_rows = []
        for c in cases:
            for acct in c.accounts:
                ar = account_risk.get(acct)
                ca_rows.append({
                    "case_id": c.case_id, "account_id": acct,
                    "risk_score": ar.score if ar else 0.0,
                    "explanation_json": json.dumps(ar.explanation if ar else []),
                })
        if ca_rows:
            session.bulk_insert_mappings(CaseAccount, ca_rows)


if __name__ == "__main__":
    summary = run_detection()
    print(f"Run {summary.run_id}: {summary.n_alerts} alerts, {summary.n_cases} cases "
          f"over {summary.n_txns} txns in {summary.duration_ms} ms.")
    print(f"Alerts by pattern: {summary.alerts_by_pattern}")
