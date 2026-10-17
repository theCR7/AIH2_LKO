"""Explainable account risk scoring (PRD F3.1/F3.2).

Score = weighted pattern hits + normalised PageRank/betweenness, capped at 100.
Every score carries an explanation list like ``"+35 member of cycle (AL-0001)"``
so there are no black-box numbers (CLAUDE.md / PRD explainability).
"""

from __future__ import annotations

import networkx as nx

from core.config import Rules
from core.detection.graph_builder import GraphBundle
from core.schemas import AccountRisk, Alert

# Human labels for pattern weight keys.
_PATTERN_LABEL = {
    "cycle": "cycle",
    "fan_in": "fan-in structuring",
    "fan_out": "fan-out layering",
    "shared_identifier": "shared identifier",
    "passthrough": "rapid pass-through",
}


def _simple_digraph(bundle: GraphBundle) -> nx.DiGraph:
    """Aggregate the MultiDiGraph into a weighted DiGraph for centrality."""
    dg: nx.DiGraph = nx.DiGraph()
    dg.add_nodes_from(bundle.graph.nodes())
    for u, v, data in bundle.graph.edges(data=True):
        if dg.has_edge(u, v):
            dg[u][v]["weight"] += data["amount"]
        else:
            dg.add_edge(u, v, weight=data["amount"])
    return dg


def _band(score: float, rules: Rules) -> str:
    """Map a score to a risk band using configured thresholds."""
    if score >= rules.scoring.bands["high"]:
        return "high"
    if score >= rules.scoring.bands["medium"]:
        return "medium"
    return "low"


def score_accounts(bundle: GraphBundle, alerts: list[Alert], rules: Rules,
                   ) -> dict[str, AccountRisk]:
    """Compute an :class:`AccountRisk` for every account appearing in an alert."""
    weights = rules.scoring.weights
    flagged: set[str] = {a for alert in alerts for a in alert.accounts}
    if not flagged:
        return {}

    # Centrality on the aggregated graph, normalised to 0..1.
    dg = _simple_digraph(bundle)
    pagerank = nx.pagerank(dg, weight="weight") if dg.number_of_edges() else {}
    max_pr = max(pagerank.values()) if pagerank else 1.0
    betweenness = (nx.betweenness_centrality(dg, weight="weight", normalized=True)
                   if dg.number_of_edges() else {})

    contributions: dict[str, list[str]] = {a: [] for a in flagged}
    scores: dict[str, float] = {a: 0.0 for a in flagged}

    for alert in alerts:
        pts = float(weights.get(alert.pattern, 0))
        if pts <= 0:
            continue
        label = _PATTERN_LABEL.get(alert.pattern, alert.pattern)
        for acct in alert.accounts:
            scores[acct] += pts
            contributions[acct].append(f"+{pts:.0f} member of {label} ({alert.alert_id})")

    pr_w = rules.scoring.centrality.pagerank_weight
    bt_w = rules.scoring.centrality.betweenness_weight
    for acct in flagged:
        pr_pts = (pagerank.get(acct, 0.0) / max_pr) * pr_w if max_pr else 0.0
        bt_pts = betweenness.get(acct, 0.0) * bt_w
        if pr_pts >= 0.5:
            scores[acct] += pr_pts
            contributions[acct].append(f"+{pr_pts:.0f} high transaction centrality")
        if bt_pts >= 0.5:
            scores[acct] += bt_pts
            contributions[acct].append(f"+{bt_pts:.0f} bridges fund flows (betweenness)")

    result: dict[str, AccountRisk] = {}
    for acct in flagged:
        final = min(100.0, round(scores[acct], 1))
        result[acct] = AccountRisk(
            account_id=acct, score=final, band=_band(final, rules),
            explanation=contributions[acct] or ["+0 no weighted signals"],
        )
    return result
