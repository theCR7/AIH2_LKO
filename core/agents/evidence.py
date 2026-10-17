"""Evidence Builder (deterministic) — compact EvidencePack from a case (PRD F5.1).

Produces an ``EvidencePack`` with stable ``E1..En`` ids (<= 40 items, CLAUDE.md
rule #5) ranked by relevance: pattern alerts first, then the transactions behind
them, then shared identifiers, then per-pattern/per-case metric items so sums are
citeable by the validator (ARCHITECTURE §6 rule 6). Persisted to the ``evidence``
table. No LLM and no streamlit here.
"""

from __future__ import annotations

import json

from core.config import load_rules
from core.db import init_db, session_scope
from core.models import Account, AlertRow, CaseAccount, CaseRow, Evidence, Identifier, Transaction
from core.schemas import EvidenceItem, EvidencePack
from core.utils import fmt_amount, fmt_date, fmt_datetime


def _dataset_from_run(run_id: str) -> str:
    """Derive the dataset id from a run id (``RUN_<dataset>``)."""
    return run_id[len("RUN_"):] if run_id.startswith("RUN_") else run_id


def pack_to_prompt(pack: EvidencePack) -> str:
    """Render an EvidencePack as a compact, deterministic user-prompt string.

    Stable text (no volatile values) so the LLM cache key stays stable (rule #12).
    """
    lines = [f"CASE: {pack.case_id}", f"PATTERNS: {', '.join(pack.patterns)}",
             f"TOTALS: {json.dumps(pack.totals, sort_keys=True)}", "SUBJECTS:"]
    for s in pack.subjects:
        lines.append(f"  - {s['account_id']} ({s.get('name', '')}, {s.get('bank', '')}), "
                     f"risk {s.get('risk_score', 0)}")
    lines.append("EVIDENCE ITEMS:")
    for it in pack.items:
        lines.append(f"  [{it.id}] ({it.kind}) {it.summary}")
    return "\n".join(lines)


def build_evidence_pack(case_id: str, persist: bool = True) -> EvidencePack:
    """Build (and optionally persist) the compact evidence pack for a case."""
    rules = load_rules()
    max_items = rules.sar.max_evidence_items
    init_db()

    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found.")
        dataset_id = _dataset_from_run(case.run_id)
        case_accounts = set(json.loads(case.accounts_json))
        patterns = json.loads(case.patterns_json)

        # Alerts belonging to this case (accounts intersect the case component).
        all_alerts = session.query(AlertRow).filter(AlertRow.run_id == case.run_id).all()
        alerts = [a for a in all_alerts
                  if set(json.loads(a.accounts_json)) & case_accounts]

        # Subjects: case accounts with name/bank/risk, ranked by risk.
        risk_by_acct = {ca.account_id: ca.risk_score
                        for ca in session.query(CaseAccount)
                        .filter(CaseAccount.case_id == case_id).all()}
        acct_rows = {a.account_id: a for a in session.query(Account)
                     .filter(Account.account_id.in_(case_accounts)).all()}
        subjects = [
            {"account_id": aid, "name": acct_rows[aid].name if aid in acct_rows else aid,
             "bank": acct_rows[aid].bank if aid in acct_rows else "unknown",
             "risk_score": round(risk_by_acct.get(aid, 0.0), 1)}
            for aid in sorted(case_accounts, key=lambda a: -risk_by_acct.get(a, 0.0))
        ][:10]

        # Transactions behind the alerts.
        txn_ids = sorted({t for a in alerts for t in json.loads(a.txn_ids_json)})
        txn_rows = {t.txn_id: t for t in session.query(Transaction)
                    .filter(Transaction.txn_id.in_(txn_ids),
                            Transaction.dataset_id == dataset_id).all()}

        # Shared identifiers among case accounts.
        idents = (session.query(Identifier)
                  .filter(Identifier.account_id.in_(case_accounts)).all())
        ident_groups: dict[tuple[str, str], list[str]] = {}
        for i in idents:
            ident_groups.setdefault((i.id_type, i.value), []).append(i.account_id)

        # --- Assemble items in relevance order -------------------------------
        items: list[EvidenceItem] = []
        seq = 1

        def add(kind: str, summary: str, data: dict) -> None:
            nonlocal seq
            items.append(EvidenceItem(id=f"E{seq}", kind=kind, summary=summary, data=data))
            seq += 1

        for a in sorted(alerts, key=lambda a: (a.pattern, a.alert_id)):
            add("pattern", a.reason,
                {"alert_id": a.alert_id, "pattern": a.pattern,
                 "accounts": json.loads(a.accounts_json),
                 "total_amount": a.total_amount})

        all_amounts: list[float] = []
        all_dates: list[str] = []
        for tid in txn_ids:
            t = txn_rows.get(tid)
            if t is None:
                continue
            all_amounts.append(t.amount)
            all_dates.append(fmt_date(t.ts))
            summary = (f"{t.txn_id}: {t.sender_id} -> {t.receiver_id}, "
                       f"{fmt_amount(t.amount)}, {fmt_datetime(t.ts)}")
            add("txn", summary,
                {"txn_id": t.txn_id, "sender": t.sender_id, "receiver": t.receiver_id,
                 "amount": t.amount, "date": fmt_date(t.ts),
                 "device_id": t.device_id, "ip": t.ip})
            if len(items) >= max_items - 3:  # reserve room for metric items
                break

        for (id_type, value), accts in sorted(ident_groups.items()):
            if len(accts) >= rules.shared_identifiers.min_accounts:
                add("identifier",
                    f"{len(accts)} accounts share {id_type} {value}: "
                    f"{', '.join(sorted(accts))}.",
                    {"id_type": id_type, "value": value, "accounts": sorted(accts)})

        # Metric items (per-pattern totals + case total) so sums are citeable.
        for pattern in sorted({a.pattern for a in alerts}):
            p_alerts = [a for a in alerts if a.pattern == pattern]
            p_total = round(sum(a.total_amount for a in p_alerts), 2)
            add("metric",
                f"{pattern}: {len(p_alerts)} alert(s) totalling {fmt_amount(p_total)}.",
                {"pattern": pattern, "total_amount": p_total, "n_alerts": len(p_alerts)})

        case_total = round(sum(all_amounts), 2)
        date_range = (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "n/a")
        add("metric",
            f"Case total: {fmt_amount(case_total)} across {len(txn_ids)} transactions, "
            f"{date_range}.",
            {"total_amount": case_total, "n_txns": len(txn_ids), "date_range": date_range})

        items = items[:max_items]

        totals = {"total_amount": case_total, "n_txns": len(txn_ids),
                  "date_range": date_range}
        pack = EvidencePack(case_id=case_id, subjects=subjects, patterns=patterns,
                            totals=totals, items=items)

        if persist:
            session.query(Evidence).filter(Evidence.case_id == case_id).delete()
            session.flush()
            session.bulk_insert_mappings(Evidence, [
                {"evidence_id": it.id, "case_id": case_id, "kind": it.kind,
                 "payload_json": json.dumps({"summary": it.summary, "data": it.data})}
                for it in items
            ])

    return pack
