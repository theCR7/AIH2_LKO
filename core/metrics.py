"""Detection-quality metrics vs planted ground truth (PRD F7.2).

Reports precision / recall / F1 per pattern at two levels (ARCHITECTURE §7a):
- **ring level**: a planted ring counts as recalled if >= ``ring_match_threshold``
  of its accounts appear in one detected alert group of the same pattern.
- **transaction level**: over transactions labelled ``is_laundering`` vs the
  transaction ids covered by alerts.
"""

from __future__ import annotations

from collections import defaultdict

from core.config import Rules, load_rules
from core.db import session_scope
from core.models import Transaction
from core.schemas import Alert, PatternMetrics


def _f1(precision: float, recall: float) -> float:
    return 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)


def ground_truth_rings(dataset_id: str) -> dict[str, dict]:
    """Load planted rings from the DB as ``ring_id -> {pattern, accounts, txn_ids}``."""
    rings: dict[str, dict] = {}
    with session_scope() as session:
        rows = (
            session.query(Transaction)
            .filter(Transaction.dataset_id == dataset_id,
                    Transaction.gt_ring_id.isnot(None))
            .all()
        )
    for t in rows:
        ring = rings.setdefault(
            t.gt_ring_id, {"pattern": t.gt_pattern, "accounts": set(), "txn_ids": set()}
        )
        ring["accounts"].update([t.sender_id, t.receiver_id])
        ring["txn_ids"].add(t.txn_id)
    return rings


def ring_level_metrics(dataset_id: str, alerts: list[Alert],
                       rules: Rules | None = None) -> list[PatternMetrics]:
    """Compute ring-level precision/recall/F1 per pattern."""
    rules = rules or load_rules()
    threshold = rules.metrics.ring_match_threshold
    rings = ground_truth_rings(dataset_id)

    gt_by_pattern: dict[str, list[set[str]]] = defaultdict(list)
    for ring in rings.values():
        gt_by_pattern[ring["pattern"]].append(set(ring["accounts"]))

    alerts_by_pattern: dict[str, list[set[str]]] = defaultdict(list)
    for a in alerts:
        alerts_by_pattern[a.pattern].append(set(a.accounts))

    patterns = sorted(set(gt_by_pattern) | set(alerts_by_pattern))
    results: list[PatternMetrics] = []
    for p in patterns:
        gt_rings = gt_by_pattern.get(p, [])
        det_groups = alerts_by_pattern.get(p, [])

        def overlaps(gt: set[str]) -> bool:
            return any(len(gt & g) / len(gt) >= threshold for g in det_groups)  # noqa: B023

        def matches_gt(group: set[str]) -> bool:
            return any(len(gt & group) / len(gt) >= threshold for gt in gt_rings)  # noqa: B023

        tp = sum(1 for gt in gt_rings if overlaps(gt))
        fn = len(gt_rings) - tp
        fp = sum(1 for g in det_groups if not matches_gt(g))
        precision = tp / (tp + fp) if (tp + fp) else (1.0 if not gt_rings else 0.0)
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        results.append(PatternMetrics(
            pattern=p, level="ring", precision=round(precision, 3),
            recall=round(recall, 3), f1=round(_f1(precision, recall), 3),
            tp=tp, fp=fp, fn=fn,
        ))
    return results


def txn_level_metrics(dataset_id: str, alerts: list[Alert]) -> PatternMetrics:
    """Compute transaction-level precision/recall/F1 over all laundering txns."""
    with session_scope() as session:
        rows = (
            session.query(Transaction.txn_id, Transaction.is_laundering)
            .filter(Transaction.dataset_id == dataset_id)
            .all()
        )
    gt_pos = {txn_id for txn_id, lab in rows if lab == 1}
    flagged = {t for a in alerts for t in a.txn_ids}

    tp = len(gt_pos & flagged)
    fp = len(flagged - gt_pos)
    fn = len(gt_pos - flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return PatternMetrics(
        pattern="all", level="txn", precision=round(precision, 3),
        recall=round(recall, 3), f1=round(_f1(precision, recall), 3),
        tp=tp, fp=fp, fn=fn,
    )


def overall_ring_recall(dataset_id: str, alerts: list[Alert],
                        rules: Rules | None = None) -> float:
    """Fraction of all planted rings recalled (pattern-agnostic account overlap)."""
    rules = rules or load_rules()
    threshold = rules.metrics.ring_match_threshold
    rings = ground_truth_rings(dataset_id)
    if not rings:
        return 1.0
    det_groups = [set(a.accounts) for a in alerts]
    recalled = 0
    for ring in rings.values():
        gt = set(ring["accounts"])
        if any(len(gt & g) / len(gt) >= threshold for g in det_groups):
            recalled += 1
    return recalled / len(rings)
