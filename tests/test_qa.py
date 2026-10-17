"""Tests for the Ask-the-case Q&A agent (ITERATIONS P10a, PRD F7.3)."""

from __future__ import annotations

from core.agents.evidence import build_evidence_pack
from core.agents.qa import answer_question

CASE = "C-001"


def _pack():
    return build_evidence_pack(CASE, persist=False)


def test_total_amount_answer_is_grounded(seeded):
    """A 'how much' question is answered from a real evidence item with a citation."""
    pack = _pack()
    answer, _ = answer_question(pack, "What is the total amount involved?")
    assert not answer.refused
    assert answer.evidence_ids
    assert all(e in {it.id for it in pack.items} for e in answer.evidence_ids)


def test_pattern_question_cites_pattern_evidence(seeded):
    """A typology/pattern question cites pattern evidence items."""
    pack = _pack()
    answer, _ = answer_question(pack, "What patterns were detected in this case?")
    assert not answer.refused
    pattern_ids = {it.id for it in pack.items if it.kind == "pattern"}
    assert pattern_ids
    assert set(answer.evidence_ids) & pattern_ids


def test_account_question_cites_account_evidence(seeded):
    """A question about a specific case account cites evidence referencing it."""
    pack = _pack()
    subject = pack.subjects[0]["account_id"]
    answer, _ = answer_question(pack, f"What do we know about {subject}?")
    assert not answer.refused
    assert answer.evidence_ids


def test_out_of_scope_question_is_refused(seeded):
    """An unrelated question is refused with no citations (grounded refusal)."""
    pack = _pack()
    answer, _ = answer_question(pack, "What is the weather today?")
    assert answer.refused
    assert answer.evidence_ids == []


def test_advice_question_is_refused(seeded):
    """The assistant refuses advice/opinion questions (read-only over evidence)."""
    pack = _pack()
    answer, _ = answer_question(pack, "Should I file the SAR and call a lawyer?")
    assert answer.refused


def test_unknown_account_is_refused(seeded):
    """Asking about an account not in the case is refused, not fabricated."""
    pack = _pack()
    answer, _ = answer_question(pack, "What about ACC_9999?")
    assert answer.refused
    assert answer.evidence_ids == []
