"""Tests for the synthetic data generator (PRD F1.1)."""

from __future__ import annotations

from core.ingest.generator import PlantedCounts, generate


def test_counts_in_expected_range(seeded):
    """~500 accounts and ~5000 transactions are generated."""
    result = seeded["result"]
    assert result.n_accounts == 500
    # Background target 5000 plus a handful of planted/decoy transactions.
    assert 5000 <= result.n_txns <= 5120


def test_account_types_tagged(seeded):
    """Payroll and merchant accounts exist so exclusion logic can run."""
    types = set(seeded["bundle"].account_type.values())
    assert {"payroll", "merchant", "individual"} <= types


def test_planted_rings_have_ground_truth(seeded):
    """Default planted counts produce the expected rings with labels."""
    rings = seeded["result"].rings
    # 3 cycles + 2 fan-in + 1 fan-out + 1 shared-id + 1 pass-through = 8 rings.
    assert len(rings) == 8
    assert all(accts for accts in rings.values())


def test_csv_written(seeded):
    """A CSV sample is exported for the dataset."""
    assert seeded["result"].csv_path is not None
    assert seeded["result"].csv_path.endswith("demo_seed42.csv")


def test_generation_is_deterministic():
    """Same seed yields identical account and transaction IDs (hard rule #11)."""
    a = generate(seed=42, persist=False, write_csv=False)
    b = generate(seed=42, persist=False, write_csv=False)
    ids_a = [(t["txn_id"], t["sender_id"], t["receiver_id"], t["amount"]) for t in a.txns]
    ids_b = [(t["txn_id"], t["sender_id"], t["receiver_id"], t["amount"]) for t in b.txns]
    assert ids_a == ids_b
    assert a.rings == b.rings


def test_planted_counts_respected():
    """Custom planted counts change the number of rings."""
    res = generate(seed=7, persist=False, write_csv=False,
                   planted=PlantedCounts(cycles=1, fan_in=1, fan_out=0,
                                         shared_id=0, passthrough=0))
    assert len(res.rings) == 2
