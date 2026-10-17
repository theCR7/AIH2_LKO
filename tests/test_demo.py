"""Tests for Demo mode orchestration and determinism (ITERATIONS P9, PRD §4)."""

from __future__ import annotations

from core.demo import demo_fingerprint, run_demo


def test_run_demo_builds_cases_and_prewarms(seeded):
    """Demo mode regenerates data, detects cases and pre-warms the top-N drafts."""
    result = run_demo(seed=42, prewarm_top_n=2)
    assert result.dataset_id == "demo_seed42"
    assert result.n_cases > 0
    assert len(result.top_case_ids) == min(2, result.n_cases)
    # One drafted SAR per top case.
    assert len(result.prewarmed_draft_ids) == len(result.top_case_ids)


def test_demo_is_deterministic_across_runs(seeded):
    """Two Demo-mode runs on seed 42 give identical case ids and fingerprints (PRD §4)."""
    first = run_demo(seed=42, prewarm_top_n=2)
    second = run_demo(seed=42, prewarm_top_n=2)
    assert first.top_case_ids == second.top_case_ids
    assert first.fingerprint == second.fingerprint
    # The fingerprint helper is stable when called again on the same data.
    assert demo_fingerprint("demo_seed42") == second.fingerprint


def test_demo_mock_mode_has_no_cache_hits(seeded):
    """In mock mode there is no LLM cache, so the ratio is 0.0 by design."""
    result = run_demo(seed=42, prewarm_top_n=2)
    assert result.cache_hit_ratio == 0.0


def test_clear_data_preserves_llm_cache(seeded):
    """Demo's reset keeps the LLM cache so live replays hit cache (PRD §4 cached SAR)."""
    from core.db import clear_data, session_scope
    from core.models import CaseRow, LlmCache
    from core.utils import utcnow

    with session_scope() as session:
        session.add(LlmCache(prompt_hash="demo-test-key", purpose="typology",
                             prompt_version="1", model="gemini/test",
                             response_text="{}", created_at=utcnow()))

    clear_data(keep_llm_cache=True)

    with session_scope() as session:
        assert session.get(LlmCache, "demo-test-key") is not None  # cache survived
        assert session.query(CaseRow).count() == 0  # everything else cleared
