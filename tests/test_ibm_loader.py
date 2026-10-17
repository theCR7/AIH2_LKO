"""Offline tests for the IBM AML loader and the scale fixes it needed (P10b).

No Kaggle access: the transform is exercised on a tiny inline DataFrame.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from core.agents.validator import validate_narrative
from core.config import load_rules
from core.ingest import ibm_loader as ibm
from core.schemas import EvidenceItem, EvidencePack, NarrativeSentence, SARNarrative
from core.scoring.risk import _betweenness


def _frame() -> pd.DataFrame:
    """Tiny HI-Small-shaped frame: two laundering rows, normals, and rows to be dropped."""
    usd = "US Dollar"
    rows = [
        # timestamp, fb, fa, tb, ta, recv, rcur, paid, pcur, fmt, label
        ("2022/09/01 00:10", "1", "A1", "2", "B1", 500.0, usd, 500.0, usd, "Wire", 1),
        ("2022/09/01 01:10", "2", "B1", "3", "C1", 480.0, usd, 480.0, usd, "Wire", 1),
        ("2022/09/01 02:00", "1", "A1", "4", "D1", 50.0, usd, 50.0, usd, "ACH", 0),   # neighbour
        ("2022/09/01 03:00", "5", "E1", "6", "F1", 70.0, usd, 70.0, usd, "ACH", 0),   # background
        ("2022/09/01 04:00", "5", "E1", "6", "G1", 80.0, usd, 80.0, usd, "ACH", 0),   # background
        ("2022/09/01 05:00", "1", "A1", "1", "A1", 9.0, usd, 9.0, usd, "Reinvestment", 0),  # self
        ("2022/09/01 06:00", "7", "H1", "8", "I1", 5.0, "Euro", 5.0, "Euro", "Wire", 0),    # euro
        ("2022/09/01 07:00", "7", "H1", "8", "I1", 0.0, usd, 0.0, usd, "Wire", 0),    # zero amt
        # Same account id "A1" at a different bank is a different account.
        ("2022/09/01 08:00", "9", "A1", "2", "B1", 60.0, usd, 60.0, usd, "ACH", 0),
    ]
    return pd.DataFrame(rows, columns=ibm._COLUMNS)


def _sample(max_total: int = 100, share: float = 0.5, seed: int = 42) -> ibm.IbmSample:
    cleaned = ibm.clean_ibm(_frame(), "US Dollar")
    return ibm.sample_ibm(cleaned, max_transactions=max_total, context_share=share,
                          seed=seed, source_rows=9)


def test_clean_drops_other_currency_self_loops_and_nonpositive():
    cleaned = ibm.clean_ibm(_frame(), "US Dollar")
    assert len(cleaned) == 6                      # 9 minus euro, self-loop, zero amount
    assert (cleaned["from_key"] != cleaned["to_key"]).all()
    assert set(cleaned["from_key"]) >= {"1:A1", "9:A1"}   # same id, different banks


def test_sample_keeps_all_laundering_and_labels():
    s = _sample()
    assert s.stats["laundering_kept"] == 2
    assert sum(t["is_laundering"] for t in s.txns) == 2
    assert all(t["gt_pattern"] is None and t["gt_ring_id"] is None for t in s.txns)
    assert all(t["currency"] == "USD" for t in s.txns)


def test_canonical_ids_and_sorted_transactions():
    s = _sample()
    ids = [a["account_id"] for a in s.accounts]
    assert ids == [f"ACC_{i:04d}" for i in range(1, len(ids) + 1)]
    assert [t["txn_id"] for t in s.txns] == [f"T{i:06d}" for i in range(1, len(s.txns) + 1)]
    assert [t["ts"] for t in s.txns] == sorted(t["ts"] for t in s.txns)
    known = set(ids)
    assert all(t["sender_id"] in known and t["receiver_id"] in known for t in s.txns)
    # Same raw account id at two banks stays two distinct accounts.
    assert len({a["account_id"] for a in s.accounts if a["bank"] in ("Bank 1", "Bank 9")}) == 2


def test_budget_is_respected_and_context_preferred():
    s = _sample(max_total=4, share=1.0)           # 2 laundering + 2 normal slots
    assert len(s.txns) == 4
    # The A1 neighbour (touches a laundering account) outranks pure background rows.
    assert s.stats["context_kept"] == 2 and s.stats["background_kept"] == 0


def test_sampling_is_deterministic():
    a, b = _sample(max_total=5), _sample(max_total=5)
    assert [(t["sender_id"], t["receiver_id"], t["amount"]) for t in a.txns] == \
           [(t["sender_id"], t["receiver_id"], t["amount"]) for t in b.txns]


def test_persist_and_detect_on_ibm_shaped_data(seeded, rules):
    """The remapped data loads and runs through detection (then restore the demo set)."""
    from core.db import session_scope
    from core.detection.runner import run_detection
    from core.ingest.generator import generate
    from core.models import Transaction

    ibm.persist_ibm(_sample(), dataset_id="ibm_test")
    with session_scope() as session:
        n = session.query(Transaction).filter(Transaction.dataset_id == "ibm_test").count()
    assert n == 6
    run_detection("ibm_test", rules)               # must not raise
    generate(seed=42, persist=True, write_csv=False)
    run_detection("demo_seed42", rules)


def test_download_without_token_is_friendly_and_secret_free(monkeypatch, tmp_path):
    monkeypatch.setattr(ibm, "DATA_DIR", tmp_path)
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    with pytest.raises(ibm.IbmLoaderError) as exc:
        ibm.download_hi_small()
    assert "KAGGLE_API_TOKEN" in str(exc.value)


def test_download_skipped_when_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(ibm, "DATA_DIR", tmp_path)
    (tmp_path / ibm.FILENAME).write_text("x")
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    assert ibm.download_hi_small() == tmp_path / ibm.FILENAME


def test_betweenness_exact_small_sampled_large_and_deterministic():
    rules = load_rules().model_copy(deep=True)
    g = nx.gnp_random_graph(30, 0.15, seed=1, directed=True)
    nx.set_edge_attributes(g, 1.0, "weight")
    # Small graph (<= exact_max_nodes): identical to the exact algorithm.
    assert _betweenness(g, rules) == nx.betweenness_centrality(g, weight="weight",
                                                               normalized=True)
    # Force the sampled path; it must be deterministic for the configured seed.
    rules.scoring.centrality.betweenness_exact_max_nodes = 10
    rules.scoring.centrality.betweenness_sample_k = 8
    assert _betweenness(g, rules) == _betweenness(g, rules)


def test_validator_checks_five_digit_account_ids():
    """Accounts past ACC_9999 must still be grounded (regex used to skip them)."""
    pack = EvidencePack(
        case_id="C-001", subjects=[{"account_id": "ACC_10001", "risk_score": 50}],
        patterns=["cycle"], totals={"total_amount": 100.0, "n_txns": 1},
        items=[EvidenceItem(id="E1", kind="pattern",
                            summary="ACC_10001 sent 100.00 USD.",
                            data={"accounts": ["ACC_10001"], "total_amount": 100.0})])
    ok = SARNarrative(summary=[NarrativeSentence(text="ACC_10001 sent 100.00 USD.",
                                                 evidence_ids=["E1"])],
                      subjects=[], activity=[], red_flags=[], conclusion=[])
    bad = SARNarrative(summary=[NarrativeSentence(text="ACC_20002 sent 100.00 USD.",
                                                  evidence_ids=["E1"])],
                       subjects=[], activity=[], red_flags=[], conclusion=[])
    assert validate_narrative(ok, pack).passed
    res = validate_narrative(bad, pack)
    assert not res.passed and "ACC_20002" in res.issues[0].problem
