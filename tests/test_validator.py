"""Tests for the SAR pipeline and the deterministic validator (PRD F5.4, ITERATIONS P4)."""

from __future__ import annotations

from core.agents.evidence import build_evidence_pack
from core.agents.orchestrator import run_sar_pipeline
from core.agents.validator import validate_narrative
from core.schemas import NarrativeSentence, SARNarrative

CASE = "C-001"


def _blank_narrative() -> SARNarrative:
    return SARNarrative(summary=[], subjects=[], activity=[], red_flags=[], conclusion=[])


def test_mock_pipeline_grounding_100(seeded):
    """The mock pipeline produces a fully grounded draft."""
    result = run_sar_pipeline(CASE)
    assert result.validation.grounding_score == 100.0
    assert result.validation.passed
    assert result.status == "drafted"


def test_real_evidence_id_wrong_amount_and_unknown_account_flagged(seeded):
    """A sentence citing a real E-id but a bogus account and amount is flagged (both)."""
    pack = build_evidence_pack(CASE)
    real_id = pack.items[0].id
    narr = _blank_narrative()
    narr.summary = [NarrativeSentence(
        text="ACC_9999 sent 1,000,000.00 USD to another account.",
        evidence_ids=[real_id])]
    result = validate_narrative(narr, pack)
    assert not result.passed
    problem = result.issues[0].problem
    assert "ACC_9999" in problem
    assert "1,000,000.00 USD" in problem or "1000000" in problem


def test_speculation_lexicon_flagged(seeded):
    """A speculative identity claim is caught even with a valid citation."""
    pack = build_evidence_pack(CASE)
    real_id = pack.items[0].id
    narr = _blank_narrative()
    narr.summary = [NarrativeSentence(
        text="The subject is a known shell company.", evidence_ids=[real_id])]
    result = validate_narrative(narr, pack)
    assert not result.passed
    assert "shell company" in result.issues[0].problem


def test_sentence_without_evidence_ids_flagged(seeded):
    """A sentence with no evidence_ids is flagged."""
    pack = build_evidence_pack(CASE)
    narr = _blank_narrative()
    narr.summary = [NarrativeSentence(text="Funds moved between accounts.", evidence_ids=[])]
    result = validate_narrative(narr, pack)
    assert not result.passed
    assert "evidence_ids" in result.issues[0].problem


def test_unknown_evidence_id_flagged(seeded):
    """A sentence citing a non-existent evidence id is flagged."""
    pack = build_evidence_pack(CASE)
    narr = _blank_narrative()
    narr.summary = [NarrativeSentence(text="Something happened.", evidence_ids=["E999"])]
    result = validate_narrative(narr, pack)
    assert not result.passed
    assert "E999" in result.issues[0].problem


def test_decision_log_and_draft_persisted(seeded):
    """The pipeline persists a versioned draft and a decision-log row."""
    from core.db import session_scope
    from core.models import DecisionLog, SarDraft
    result = run_sar_pipeline(CASE)
    with session_scope() as session:
        draft = session.get(SarDraft, result.draft_id)
        logs = session.query(DecisionLog).filter(DecisionLog.case_id == CASE).all()
    assert draft is not None
    assert draft.grounding_score == 100.0
    assert len(logs) >= 1
