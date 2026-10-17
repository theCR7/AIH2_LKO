"""Rapid pass-through detection (PRD F2.5).

Flags an account that receives a sizeable inflow and forwards >= min_outflow_ratio
of it within a short window — a classic mule/layering hop.
"""

from __future__ import annotations

from datetime import timedelta

from core.config import Rules
from core.detection.graph_builder import GraphBundle, RawAlert
from core.utils import fmt_amount, fmt_date


def detect_passthrough(bundle: GraphBundle, rules: Rules) -> list[RawAlert]:
    """Detect inflow-then-rapid-outflow pass-through hubs."""
    cfg = rules.passthrough
    window = timedelta(hours=cfg.window_hours)

    exclude = rules.exclude_account_types
    incoming: dict[str, list[dict]] = {}
    outgoing: dict[str, list[dict]] = {}
    for u, v, data in bundle.graph.edges(data=True):
        # Drop legitimate counterparties so merchant payments / salaries do not
        # masquerade as the inflow or outflow of a pass-through hub.
        if not bundle.is_excluded(u, exclude):
            incoming.setdefault(v, []).append({**data, "sender": u})
        if not bundle.is_excluded(v, exclude):
            outgoing.setdefault(u, []).append({**data, "receiver": v})

    alerts: list[RawAlert] = []
    seen: set[tuple[str, str]] = set()  # (hub, inflow_txn) dedupe

    for hub, in_edges in incoming.items():
        if bundle.is_excluded(hub, rules.exclude_account_types):
            continue
        out_edges = sorted(outgoing.get(hub, []), key=lambda d: d["ts"])
        if not out_edges:
            continue
        for inflow in sorted(in_edges, key=lambda d: d["ts"]):
            if inflow["amount"] < cfg.min_inflow:
                continue
            following = [e for e in out_edges
                         if inflow["ts"] <= e["ts"] <= inflow["ts"] + window]
            outflow_total = sum(e["amount"] for e in following)
            if outflow_total < cfg.min_outflow_ratio * inflow["amount"]:
                continue
            marker = (hub, inflow["txn_id"])
            if marker in seen:
                continue
            seen.add(marker)
            accounts = sorted({inflow["sender"], hub, *(e["receiver"] for e in following)})
            txn_ids = sorted([inflow["txn_id"], *(e["txn_id"] for e in following)])
            ratio = outflow_total / inflow["amount"]
            reason = (f"{hub} received {fmt_amount(inflow['amount'])} on "
                      f"{fmt_date(inflow['ts'])} and forwarded {ratio:.0%} within "
                      f"{cfg.window_hours}h.")
            alerts.append(
                RawAlert(pattern="passthrough", accounts=accounts, txn_ids=txn_ids,
                         total_amount=round(inflow["amount"], 2), reason=reason,
                         severity="high")
            )
    return alerts
