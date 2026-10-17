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


def _betweenness(dg: nx.DiGraph, rules: Rules) -> dict[str, float]:
    """Betweenness centrality: exact on small graphs, seeded sample on large ones.

    Exact weighted betweenness is O(V*E) and does not finish on real-scale graphs
    (e.g. the IBM AML sample), so above ``betweenness_exact_max_nodes`` we estimate
    from ``betweenness_sample_k`` pivots with a fixed seed (deterministic, CLAUDE.md
    rule #11). Small graphs, including the seed-42 demo, keep the exact result.
    """
    cfg = rules.scoring.centrality
    if dg.number_of_nodes() <= cfg.betweenness_exact_max_nodes:
        return nx.betweenness_centrality(dg, weight="weight", normalized=True)
    return nx.betweenness_centrality(dg, k=cfg.betweenness_sample_k, normalized=True,
                                     seed=cfg.betweenness_seed)


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
    betweenness = _betweenness(dg, rules) if dg.number_of_edges() else {}

    contributions: dict[str, list[str]] = {a: [] for a in flagged}
    scores: dict[str, float] = {a: 0.0 for a in flagged}

    # Each pattern counts ONCE per account. Stacking every alert linearly saturated the
    # cap on real data (an account in four pass-through alerts reached 100 and the top
    # ten cases all tied); repeats are noted in the explanation instead.
    hits: dict[tuple[str, str], list[str]] = {}
    for alert in alerts:
        if float(weights.get(alert.pattern, 0)) <= 0:
            continue
        for acct in alert.accounts:
            hits.setdefault((acct, alert.pattern), []).append(alert.alert_id)
    for (acct, pattern), alert_ids in hits.items():
        pts = float(weights[pattern])
        label = _PATTERN_LABEL.get(pattern, pattern)
        more = f", +{len(alert_ids) - 1} more" if len(alert_ids) > 1 else ""
        scores[acct] += pts
        contributions[acct].append(f"+{pts:.0f} member of {label} ({alert_ids[0]}{more})")

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
