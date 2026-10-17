"""Shared pytest fixtures.

Points the DB at an isolated temp SQLite file *before* core is imported, so
tests never touch the demo database. ``load_dotenv`` does not override an env
var that is already set, so this takes precedence.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make the project root importable and isolate the test database.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TEST_DB = Path(tempfile.gettempdir()) / "ringsight_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["LLM_MODE"] = "mock"  # tests run offline, deterministically

import pytest

from core.config import load_rules
from core.db import reset_db
from core.detection.runner import load_bundle, run_all_detectors, run_detection
from core.ingest.generator import generate

SEED = 42
DATASET = f"demo_seed{SEED}"


@pytest.fixture(scope="session")
def rules():
    """The default rules from config/rules.yaml."""
    return load_rules()


@pytest.fixture(scope="session")
def seeded(rules):
    """Reset the DB, generate seed-42 data, run + persist detection once."""
    reset_db()
    result = generate(seed=SEED, persist=True, write_csv=True)
    bundle = load_bundle(DATASET)
    alerts = run_all_detectors(bundle, rules)
    summary = run_detection(DATASET, rules)  # persists cases/alerts for SAR tests
    return {
        "dataset": DATASET,
        "result": result,
        "bundle": bundle,
        "alerts": alerts,
        "summary": summary,
    }
