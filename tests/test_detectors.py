"""Tests for the detection engine, scoring and case grouping (PRD F2/F3)."""

from __future__ import annotations

import time

from core import metrics
from core.detection.runner import load_bundle, run_all_detectors, run_detection
from core.ingest.generator import generate
from core.scoring.cases import build_cases
from core.scoring.risk import score_accounts

DATASET = "demo_seed42"


def test_all_planted_rings_detected(seeded, rules):
    """Ring-level recall is 1.0 on seed 42 with default rules."""
    recall = metrics.overall_ring_recall(DATASET, seeded["alerts"], rules)
    assert recall == 1.0


def test_per_pattern_recall_is_one(seeded, rules):
    """Every planted pattern is fully recalled (recall == 1.0 per pattern)."""
    for m in metrics.ring_level_metrics(DATASET, seeded["alerts"], rules):
        # Patterns that have ground-truth rings must be fully recalled.
        gt_present = (m.tp + m.fn) > 0
        if gt_present:
            assert m.recall == 1.0, f"{m.pattern} recall={m.recall}"


def test_payroll_merchant_not_flagged(seeded):
    """Legitimate payroll/merchant accounts never appear in an alert."""
    bundle = seeded["bundle"]
    flagged = {a for alert in seeded["alerts"] for a in alert.accounts}
    bad = [a for a in flagged if bundle.account_type.get(a) in ("payroll", "merchant")]
    assert bad == []


def test_precision_is_realistic(seeded, rules):
    """Decoys/noise keep precision below 1.0 for at least one pattern (honest metrics)."""
    ms = metrics.ring_level_metrics(DATASET, seeded["alerts"], rules)
    assert any(m.precision < 1.0 for m in ms)


def test_case_ids_are_deterministic(rules):
    """Two independent runs on seed 42 produce identical case IDs and scores."""
    def run_case_ids():
        generate(seed=42, persist=True, write_csv=False)
        bundle = load_bundle(DATASET)
        alerts = run_all_detectors(bundle, rules)
        account_risk = score_accounts(bundle, alerts, rules)
        cases, _ = build_cases(alerts, account_risk, rules)
        return [(c.case_id, tuple(c.accounts), c.score) for c in cases]

    assert run_case_ids() == run_case_ids()


def test_detection_runtime_under_10s(rules):
    """Detection on ~5k transactions completes in under 10 seconds."""
    generate(seed=42, persist=True, write_csv=False)
    t0 = time.perf_counter()
    summary = run_detection(DATASET, rules)
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"detection took {elapsed:.2f}s"
    assert summary.n_cases > 0


def test_cycle_alerts_present(seeded):
    """At least the three planted cycles are detected as cycle alerts."""
    cycle_alerts = [a for a in seeded["alerts"] if a.pattern == "cycle"]
    assert len(cycle_alerts) >= 3
