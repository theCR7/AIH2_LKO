"""Case grouping by connected components on the alert graph (ARCHITECTURE §7a).

Components are computed on the *alert graph* (nodes = accounts in any alert; an
edge joins two accounts that co-occur in an alert), never the full transaction
graph which is one giant component. Case score = max member account score.
Case IDs are assigned in a deterministic order (CLAUDE.md hard rule #11).
"""

from __future__ import annotations

import networkx as nx

from core.config import Rules
from core.schemas import AccountRisk, Alert, CaseSummary

# Short human titles per dominant pattern.
_TITLE = {
    "cycle": "Circular flow",
    "fan_in": "Structuring (fan-in)",
    "fan_out": "Layering (fan-out)",
    "shared_identifier": "Shared-identifier cluster",
    "passthrough": "Rapid pass-through",
}


def _alert_graph(alerts: list[Alert]) -> nx.Graph:
    """Build the undirected alert graph linking co-occurring accounts."""
    g: nx.Graph = nx.Graph()
    for alert in alerts:
        accounts = alert.accounts
        g.add_nodes_from(accounts)
        for i in range(len(accounts)):
            for j in range(i + 1, len(accounts)):
                g.add_edge(accounts[i], accounts[j])
    return g


def _case_title(patterns: list[str], accounts: list[str], alerts: list[Alert]) -> str:
    """Generate a readable case title from its dominant pattern and a key account."""
    dominant = patterns[0] if patterns else "pattern"
    label = _TITLE.get(dominant, dominant)
    # Pick the account with the most alert memberships as the hub for the title.
    counts: dict[str, int] = {a: 0 for a in accounts}
    for alert in alerts:
        for a in alert.accounts:
            if a in counts:
                counts[a] += 1
    hub = max(sorted(accounts), key=lambda a: counts.get(a, 0)) if accounts else "?"
    if dominant == "cycle":
        n_hops = max((len(al.accounts) for al in alerts if al.pattern == "cycle"), default=0)
        return f"{n_hops}-hop circular flow via {hub}"
    if dominant in ("fan_in", "fan_out"):
        return f"{label} involving {hub}"
    return f"{label} around {hub}"


def build_cases(alerts: list[Alert], account_risk: dict[str, AccountRisk],
                rules: Rules) -> tuple[list[CaseSummary], dict[str, list[str]]]:
    """Group alerts into ranked cases.

    Returns ``(cases, case_to_alert_ids)``. All cases are returned (including
    those below ``cases.min_case_score``); callers/UI filter for display.
    """
    if not alerts:
        return [], {}

    g = _alert_graph(alerts)
    components = [sorted(c) for c in nx.connected_components(g)]

    # Map each alert to the component (as a frozenset) containing its accounts.
    account_to_comp: dict[str, int] = {}
    for idx, comp in enumerate(components):
        for a in comp:
            account_to_comp[a] = idx
    comp_alerts: dict[int, list[Alert]] = {i: [] for i in range(len(components))}
    for alert in alerts:
        idx = account_to_comp[alert.accounts[0]]
        comp_alerts[idx].append(alert)

    draft: list[tuple[float, list[str], list[str], list[Alert]]] = []
    for idx, comp in enumerate(components):
        members = comp_alerts[idx]
        score = max((account_risk[a].score for a in comp if a in account_risk), default=0.0)
        # Patterns ordered by weight contribution (most impactful first).
        pattern_order = sorted(
            {al.pattern for al in members},
            key=lambda p: -rules.scoring.weights.get(p, 0),
        )
        draft.append((score, comp, pattern_order, members))

    # Deterministic ranking: highest score first, then by accounts.
    draft.sort(key=lambda d: (-d[0], d[1]))

    cases: list[CaseSummary] = []
    case_to_alerts: dict[str, list[str]] = {}
    for i, (score, comp, patterns, members) in enumerate(draft, start=1):
        case_id = f"C-{i:03d}"
        txn_ids = {t for al in members for t in al.txn_ids}
        total_amount = round(sum(al.total_amount for al in members), 2)
        cases.append(
            CaseSummary(
                case_id=case_id,
                title=_case_title(patterns, comp, members),
                patterns=patterns,
                accounts=comp,
                score=round(score, 1),
                status="New",
                total_amount=total_amount,
                n_txns=len(txn_ids),
            )
        )
        case_to_alerts[case_id] = sorted(al.alert_id for al in members)
    return cases, case_to_alerts
