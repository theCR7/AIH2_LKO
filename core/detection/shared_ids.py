"""Shared-identifier clustering detection (PRD F2.4).

Flags >= min_accounts distinct accounts sharing an IP or device id. Accounts of
excluded types (merchant/payroll) are not counted, so a shared payment processor
does not create noise.
"""

from __future__ import annotations

from collections import defaultdict

from core.config import Rules
from core.detection.graph_builder import GraphBundle, RawAlert


def detect_shared_ids(bundle: GraphBundle, rules: Rules) -> list[RawAlert]:
    """Detect clusters of accounts sharing an identifier value."""
    cfg = rules.shared_identifiers
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for account_id, id_type, value in bundle.identifiers:
        if id_type not in cfg.id_types:
            continue
        if bundle.is_excluded(account_id, rules.exclude_account_types):
            continue
        groups[(id_type, value)].add(account_id)

    alerts: list[RawAlert] = []
    for (id_type, value), accounts in groups.items():
        if len(accounts) < cfg.min_accounts:
            continue
        reason = (f"{len(accounts)} accounts share {id_type} {value}: "
                  f"{', '.join(sorted(accounts))}.")
        alerts.append(
            RawAlert(pattern="shared_identifier", accounts=sorted(accounts),
                     txn_ids=[], total_amount=0.0, reason=reason, severity="medium")
        )
    return alerts
