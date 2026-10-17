"""Tests for evidence pack sizing and PDF export (ITERATIONS P2, P7)."""

from __future__ import annotations

from core.agents.evidence import build_evidence_pack
from core.agents.orchestrator import run_sar_pipeline
from core.config import load_rules
from core.reporting.pdf import build_sar_pdf

CASE = "C-001"


def test_evidence_pack_within_cap_and_stable_ids(seeded):
    """Evidence pack respects the item cap and uses stable E1..En ids."""
    rules = load_rules()
    pack = build_evidence_pack(CASE)
    assert len(pack.items) <= rules.sar.max_evidence_items
    assert [it.id for it in pack.items] == [f"E{i}" for i in range(1, len(pack.items) + 1)]
    # Rebuild -> identical ids and summaries (determinism).
    pack2 = build_evidence_pack(CASE)
    assert [(it.id, it.summary) for it in pack.items] == \
           [(it.id, it.summary) for it in pack2.items]


def test_pdf_generated(seeded):
    """The SAR PDF is produced and is a non-trivial size."""
    result = run_sar_pipeline(CASE)
    pdf = build_sar_pdf(CASE, result, approved=False)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000
