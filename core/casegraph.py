"""Case subgraph loader shared by the pyvis UI and the PDF's static render.

Lives in ``core`` (no streamlit) so ``core/reporting/pdf.py`` can reuse it. Returns
plain dicts describing the nodes (with risk/band) and edges (with amount/date and a
``suspicious`` flag) of one case's money subgraph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from core.config import load_rules
from core.db import init_db, session_scope
from core.models import Account, AlertRow, CaseAccount, CaseRow, Transaction
from core.utils import fmt_amount, fmt_date


@dataclass
class CaseSubgraph:
    """Nodes and edges for one case, ready for pyvis or matplotlib."""

    case_id: str
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    capped: bool = False  # True if trimmed to the node cap

MAX_NODES = 150


def _band(score: float) -> str:
    bands = load_rules().scoring.bands
    if score >= bands["high"]:
        return "high"
    if score >= bands["medium"]:
        return "medium"
    return "low"


def load_case_subgraph(case_id: str, hops: int = 0) -> CaseSubgraph:
    """Build the money subgraph (accounts + transactions) for a case.

    Args:
        case_id: the case to render.
        hops: 0 = case accounts only; 1 = also include direct (1-hop) counterparties
            and the edges connecting them, marked as neighbours (never the full graph).
    """
    init_db()
    capped = False
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            return CaseSubgraph(case_id=case_id)
        dataset_id = case.run_id[len("RUN_"):] if case.run_id.startswith("RUN_") else case.run_id
        accounts = set(json.loads(case.accounts_json))

        risk = {ca.account_id: ca.risk_score for ca in session.query(CaseAccount)
                .filter(CaseAccount.case_id == case_id).all()}

        alerts = session.query(AlertRow).filter(AlertRow.run_id == case.run_id).all()
        case_alerts = [a for a in alerts if set(json.loads(a.accounts_json)) & accounts]
        suspicious_txns = {t for a in case_alerts for t in json.loads(a.txn_ids_json)}

        # Edges: within-case always; with hops=1 also edges touching one case account.
        if hops >= 1:
            txns = (session.query(Transaction)
                    .filter(Transaction.dataset_id == dataset_id,
                            (Transaction.sender_id.in_(accounts))
                            | (Transaction.receiver_id.in_(accounts)))
                    .all())
        else:
            txns = (session.query(Transaction)
                    .filter(Transaction.dataset_id == dataset_id,
                            Transaction.sender_id.in_(accounts),
                            Transaction.receiver_id.in_(accounts))
                    .all())

        node_ids = set(accounts)
        for t in txns:
            node_ids.add(t.sender_id)
            node_ids.add(t.receiver_id)
        if len(node_ids) > MAX_NODES:
            capped = True
            neighbours = [n for n in node_ids if n not in accounts]
            keep = set(accounts) | set(sorted(neighbours)[: max(0, MAX_NODES - len(accounts))])
            node_ids = keep
            txns = [t for t in txns if t.sender_id in node_ids and t.receiver_id in node_ids]

        acct_rows = {a.account_id: a for a in session.query(Account)
                     .filter(Account.account_id.in_(node_ids)).all()}

        nodes = [
            {"id": aid, "risk": round(risk.get(aid, 0.0), 1),
             "band": _band(risk.get(aid, 0.0)),
             "type": acct_rows[aid].account_type if aid in acct_rows else "individual",
             "bank": acct_rows[aid].bank if aid in acct_rows else "unknown",
             "name": acct_rows[aid].name if aid in acct_rows else aid,
             "is_case": aid in accounts}
            for aid in sorted(node_ids)
        ]
        edges = [
            {"source": t.sender_id, "target": t.receiver_id, "amount": t.amount,
             "date": fmt_date(t.ts), "txn_id": t.txn_id,
             "label": fmt_amount(t.amount), "suspicious": t.txn_id in suspicious_txns}
            for t in sorted(txns, key=lambda t: t.txn_id)
        ]
    return CaseSubgraph(case_id=case_id, nodes=nodes, edges=edges, capped=capped)
