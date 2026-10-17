"""Fan-in (smurfing/structuring) and fan-out (layering) detection (PRD F2.2/F2.3).

Legitimate fan patterns (payroll fan-out, merchant fan-in) are skipped via
``exclude_account_types`` (ARCHITECTURE §7a).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from core.config import Rules
from core.detection.graph_builder import GraphBundle, RawAlert
from core.utils import fmt_amount, fmt_date


def _incoming(bundle: GraphBundle, exclude: list[str]) -> dict[str, list[dict]]:
    """Map receiver -> incoming edge attrs (with sender), sorted by timestamp.

    Edges from excluded-type senders (payroll/merchant) are dropped so those
    legitimate accounts never enter a smurfing alert as counterparties.
    """
    by_receiver: dict[str, list[dict]] = defaultdict(list)
    for u, v, data in bundle.graph.edges(data=True):
        if bundle.is_excluded(u, exclude):
            continue
        by_receiver[v].append({**data, "sender": u})
    for v in by_receiver:
        by_receiver[v].sort(key=lambda d: d["ts"])
    return by_receiver


def _outgoing(bundle: GraphBundle, exclude: list[str]) -> dict[str, list[dict]]:
    """Map sender -> outgoing edge attrs (with receiver), sorted by timestamp.

    Edges to excluded-type receivers (payroll/merchant) are dropped so legitimate
    merchant payments never enter a layering alert as counterparties.
    """
    by_sender: dict[str, list[dict]] = defaultdict(list)
    for u, v, data in bundle.graph.edges(data=True):
        if bundle.is_excluded(v, exclude):
            continue
        by_sender[u].append({**data, "receiver": v})
    for u in by_sender:
        by_sender[u].sort(key=lambda d: d["ts"])
    return by_sender


def detect_fan_in(bundle: GraphBundle, rules: Rules) -> list[RawAlert]:
    """Detect >= min_senders distinct senders -> one receiver, each small, within window."""
    cfg = rules.fan_in
    window = timedelta(hours=cfg.window_hours)
    alerts: list[RawAlert] = []
    by_receiver = _incoming(bundle, rules.exclude_account_types)

    for receiver, edges in by_receiver.items():
        if bundle.is_excluded(receiver, rules.exclude_account_types):
            continue
        small = [e for e in edges if e["amount"] < cfg.max_amount_each]
        best = _best_window(small, window, key_account="sender", min_distinct=cfg.min_senders)
        if best is None:
            continue
        window_edges, senders = best
        if len(senders) > cfg.max_senders:
            continue  # thousands of payers into one account is an institution, not structuring
        txn_ids = sorted(e["txn_id"] for e in window_edges)
        total = round(sum(e["amount"] for e in window_edges), 2)
        first = min(e["ts"] for e in window_edges)
        reason = (f"{len(senders)} distinct senders paid {fmt_amount(total)} into "
                  f"{receiver} within {cfg.window_hours}h from {fmt_date(first)} "
                  f"(each below {fmt_amount(cfg.max_amount_each)}).")
        alerts.append(
            RawAlert(pattern="fan_in", accounts=sorted({receiver, *senders}),
                     txn_ids=txn_ids, total_amount=total, reason=reason, severity="high")
        )
    return alerts


def detect_fan_out(bundle: GraphBundle, rules: Rules) -> list[RawAlert]:
    """Detect one sender -> >= min_receivers distinct receivers, total large, within window."""
    cfg = rules.fan_out
    window = timedelta(hours=cfg.window_hours)
    alerts: list[RawAlert] = []
    by_sender = _outgoing(bundle, rules.exclude_account_types)

    for sender, edges in by_sender.items():
        if bundle.is_excluded(sender, rules.exclude_account_types):
            continue
        best = _best_window(edges, window, key_account="receiver",
                            min_distinct=cfg.min_receivers)
        if best is None:
            continue
        window_edges, receivers = best
        if len(receivers) > cfg.max_receivers:
            continue  # a mass payer (payroll-like) is not mule layering
        total = round(sum(e["amount"] for e in window_edges), 2)
        if total < cfg.min_total:
            continue
        txn_ids = sorted(e["txn_id"] for e in window_edges)
        first = min(e["ts"] for e in window_edges)
        reason = (f"{sender} dispersed {fmt_amount(total)} to {len(receivers)} receivers "
                  f"within {cfg.window_hours}h from {fmt_date(first)}.")
        alerts.append(
            RawAlert(pattern="fan_out", accounts=sorted({sender, *receivers}),
                     txn_ids=txn_ids, total_amount=total, reason=reason, severity="high")
        )
    return alerts


def _best_window(edges: list[dict], window: timedelta, key_account: str,
                 min_distinct: int) -> tuple[list[dict], set[str]] | None:
    """Find a time window with the most distinct counterparties (>= min_distinct).

    ``edges`` must be sorted by timestamp. Returns the edges inside the best
    window and the distinct counterparty set, or None if the threshold is not met.
    """
    if len(edges) < min_distinct:
        return None
    n = len(edges)
    best: tuple[list[dict], set[str]] | None = None
    left = 0
    for right in range(n):
        while edges[right]["ts"] - edges[left]["ts"] > window:
            left += 1
        window_edges = edges[left : right + 1]
        distinct = {e[key_account] for e in window_edges}
        if len(distinct) >= min_distinct:
            if best is None or len(distinct) > len(best[1]):
                best = (list(window_edges), set(distinct))
    return best
