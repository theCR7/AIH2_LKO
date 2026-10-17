"""Tests for the synthetic data generator (PRD F1.1)."""

from __future__ import annotations

from core.detection.runner import run_detection
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


def test_upload_replaces_prior_dataset_without_collision(seeded, rules):
    """Uploading after the sample must not collide on txn_id or leak prior data.

    Regression: the generator and CSV loader both mint ``T000001`` ids (a global
    PK). The DB holds one active dataset, so a load clears the prior one; a prior
    run's identifiers must not survive to contaminate detection.
    """
    import pandas as pd

    from core.db import session_scope
    from core.ingest.csv_loader import load_dataframe
    from core.models import Identifier, Transaction

    df = pd.DataFrame({
        "sender": ["ACC_1", "ACC_2", "ACC_3"],
        "receiver": ["ACC_2", "ACC_3", "ACC_1"],
        "amount": [100.0, 90.0, 80.0],
        "timestamp": ["2026-09-01 10:00", "2026-09-01 12:00", "2026-09-01 14:00"],
    })
    mapping = {"sender": "sender", "receiver": "receiver",
               "amount": "amount", "timestamp": "timestamp"}
    result = load_dataframe(df, mapping, dataset_id="upload")  # must not raise
    assert result.ok and result.n_txns == 3
    with session_scope() as session:
        assert session.query(Transaction).count() == 3
        assert session.query(Transaction).filter(
            Transaction.dataset_id == "demo_seed42").count() == 0
        assert session.query(Identifier).count() == 0  # no leaked demo identifiers
    # Restore the demo dataset for the remaining session-scoped tests.
    generate(seed=42, persist=True, write_csv=False)
    run_detection("demo_seed42", rules)
