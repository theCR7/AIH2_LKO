"""Build the transaction graph and a shared bundle for all detectors.

The money graph is a NetworkX ``MultiDiGraph`` (one edge per transaction) with
per-edge attributes ``txn_id``, ``amount`` and ``ts``. Nodes carry their
``account_type`` so detectors can honour ``exclude_account_types``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx


@dataclass
class TxnRecord:
    """A normalised transaction used by detectors (DB/CSV agnostic)."""

    txn_id: str
    sender_id: str
    receiver_id: str
    amount: float
    ts: datetime
    ip: str | None = None
    device_id: str | None = None


@dataclass
class RawAlert:
    """A detector hit before a stable alert_id is assigned (CLAUDE.md rule #11).

    ``accounts`` and ``txn_ids`` are kept sorted so the runner can order and id
    alerts deterministically.
    """

    pattern: str
    accounts: list[str]
    txn_ids: list[str]
    total_amount: float
    reason: str
    severity: str = "medium"
    # The account the pattern is about (fan-in receiver, fan-out sender); used for titles.
    focus: str | None = None


@dataclass
class GraphBundle:
    """Everything the detectors need, built once per run."""

    graph: nx.MultiDiGraph
    txns: list[TxnRecord]
    account_type: dict[str, str]
    identifiers: list[tuple[str, str, str]] = field(default_factory=list)  # (account, id_type, value)

    def is_excluded(self, account_id: str, exclude_types: list[str]) -> bool:
        """True if the account's type is in the excluded set."""
        return self.account_type.get(account_id, "individual") in exclude_types


def build_graph(txns: list[TxnRecord], account_type: dict[str, str],
                identifiers: list[tuple[str, str, str]] | None = None) -> GraphBundle:
    """Assemble a :class:`GraphBundle` from normalised transactions."""
    g: nx.MultiDiGraph = nx.MultiDiGraph()
    for acct, atype in account_type.items():
        g.add_node(acct, account_type=atype)
    for t in txns:
        # Ensure endpoints exist even if missing from the account map.
        for node in (t.sender_id, t.receiver_id):
            if node not in g:
                g.add_node(node, account_type=account_type.get(node, "individual"))
        g.add_edge(t.sender_id, t.receiver_id, key=t.txn_id,
                   txn_id=t.txn_id, amount=t.amount, ts=t.ts)
    return GraphBundle(graph=g, txns=txns, account_type=account_type,
                       identifiers=list(identifiers or []))
