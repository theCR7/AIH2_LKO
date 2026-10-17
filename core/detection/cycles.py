"""Circular-flow (layering) detection (PRD F2.1).

Follows ARCHITECTURE §7a to avoid cycle explosion:
1. Build the cycle graph from a *filtered* edge set — drop merchant/payroll
   endpoints and amounts below ``cycles.min_amount``.
2. Collapse the MultiDiGraph to a simple DiGraph for enumeration.
3. Enumerate with ``nx.simple_cycles(length_bound=max_length)``, capped at
   ``cycles.max_candidates`` (log a warning on overflow).
4. Re-check each candidate on the *real* transactions: hop times within the
   window and value retention per hop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import networkx as nx

from core.config import Rules
from core.detection.graph_builder import GraphBundle, RawAlert
from core.utils import fmt_amount, fmt_date

logger = logging.getLogger(__name__)


def _filtered_digraph(bundle: GraphBundle, rules: Rules) -> nx.DiGraph:
    """Collapse to a DiGraph of edges eligible to form a laundering cycle."""
    exclude = rules.exclude_account_types
    min_amount = rules.cycles.min_amount
    dg: nx.DiGraph = nx.DiGraph()
    for u, v, data in bundle.graph.edges(data=True):
        if data["amount"] < min_amount:
            continue
        if bundle.is_excluded(u, exclude) or bundle.is_excluded(v, exclude):
            continue
        dg.add_edge(u, v)
    return dg


def _edges_between(bundle: GraphBundle, u: str, v: str) -> list[dict]:
    """Return real transaction edge-attrs from u to v, sorted by timestamp."""
    if not bundle.graph.has_edge(u, v):
        return []
    out = [data for _key, data in bundle.graph[u][v].items()]
    return sorted(out, key=lambda d: d["ts"])


def _validate_rotation(hop_edges: list[list[dict]], window: timedelta,
                       retention: float) -> list[dict] | None:
    """DFS over one rotation: pick a real txn per hop with monotonic time + retention."""
    n = len(hop_edges)

    def dfs(hop: int, start_ts, prev_ts, prev_amt, chosen: list[dict]) -> list[dict] | None:
        if hop == n:
            return chosen
        for edge in hop_edges[hop]:
            if edge["ts"] < prev_ts:
                continue
            if start_ts is not None and edge["ts"] - start_ts > window:
                continue
            if prev_amt is not None and edge["amount"] < retention * prev_amt:
                continue
            result = dfs(hop + 1, start_ts or edge["ts"], edge["ts"],
                         edge["amount"], [*chosen, edge])
            if result is not None:
                return result
        return None

    return dfs(0, None, datetime.min, None, [])


def _validate_cycle(bundle: GraphBundle, nodes: list[str], rules: Rules) -> list[dict] | None:
    """Confirm a candidate node cycle is realisable on real transactions.

    ``nx.simple_cycles`` returns nodes from an arbitrary starting point, but a
    real laundering loop's closing hop wraps around in time. So every rotation of
    the node list is tried; a rotation is valid if a transaction can be picked
    per hop with non-decreasing timestamps inside ``max_window_hours`` and each
    hop retaining at least ``min_value_retention`` of the previous amount.
    Returns the chosen transaction attrs in flow order, or None.
    """
    window = timedelta(hours=rules.cycles.max_window_hours)
    retention = rules.cycles.min_value_retention
    n = len(nodes)
    for start in range(n):
        rotated = [nodes[(start + i) % n] for i in range(n)]
        hop_edges = [_edges_between(bundle, rotated[i], rotated[(i + 1) % n]) for i in range(n)]
        if any(not e for e in hop_edges):
            continue
        result = _validate_rotation(hop_edges, window, retention)
        if result is not None:
            return result
    return None


def detect_cycles(bundle: GraphBundle, rules: Rules) -> list[RawAlert]:
    """Detect circular transaction flows that satisfy the cycle rules."""
    dg = _filtered_digraph(bundle, rules)
    if dg.number_of_edges() == 0:
        return []

    alerts: list[RawAlert] = []
    seen: set[frozenset[str]] = set()
    count = 0
    for cycle in nx.simple_cycles(dg, length_bound=rules.cycles.max_length):
        count += 1
        if count > rules.cycles.max_candidates:
            logger.warning("Cycle candidates exceeded max_candidates=%d; stopping enumeration.",
                           rules.cycles.max_candidates)
            break
        if len(cycle) < rules.cycles.min_length:
            continue
        key = frozenset(cycle)
        if key in seen:
            continue
        chosen = _validate_cycle(bundle, cycle, rules)
        if chosen is None:
            continue
        seen.add(key)
        txn_ids = sorted(e["txn_id"] for e in chosen)
        total = round(sum(e["amount"] for e in chosen), 2)
        first_ts = min(e["ts"] for e in chosen)
        last_ts = max(e["ts"] for e in chosen)
        hop_days = max(1, (last_ts - first_ts).days or 1)
        reason = (f"{len(cycle)}-hop circular flow ({' -> '.join(sorted(cycle))}) "
                  f"totalling {fmt_amount(total)} within {hop_days} day(s), "
                  f"first hop {fmt_date(first_ts)}.")
        alerts.append(
            RawAlert(pattern="cycle", accounts=sorted(cycle), txn_ids=txn_ids,
                     total_amount=total, reason=reason, severity="high")
        )
    return alerts
