"""Tests for the LLM gateway (ITERATIONS P1) — no network, litellm monkeypatched."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from core import agents
from core.agents import llm as llm_mod
from core.config import load_settings
from core.db import init_db, session_scope
from core.models import LlmCache


class _Toy(BaseModel):
    value: int


@pytest.fixture(autouse=True)
def _clean_cache_and_mode():
    """Clear only the LLM cache (not the seeded data) and restore mock mode after."""
    init_db()
    with session_scope() as session:
        session.query(LlmCache).delete()
    yield
    with session_scope() as session:
        session.query(LlmCache).delete()
    os.environ["LLM_MODE"] = "mock"
    load_settings.cache_clear()


def test_mock_mode_uses_builder(monkeypatch):
    """LLM_MODE=mock returns the mock builder output without any provider call."""
    monkeypatch.setenv("LLM_MODE", "mock")
    from core.config import load_settings
    load_settings.cache_clear()
    res = llm_mod.call_llm("sys", "user", _Toy, "toy", mock_builder=lambda: _Toy(value=7))
    assert res.parsed.value == 7
    assert res.model_used == "mock"
    load_settings.cache_clear()


def test_live_caches_and_replays(monkeypatch):
    """A live call is cached; the second identical call is a cache hit."""
    monkeypatch.setenv("LLM_MODE", "live")
    from core.config import load_settings
    load_settings.cache_clear()
    calls = {"n": 0}

    def fake_completion(model, system, user, temperature):
        calls["n"] += 1
        return '{"value": 42}'

    monkeypatch.setattr(llm_mod, "_completion", fake_completion)
    r1 = llm_mod.call_llm("sys", "user", _Toy, "toy")
    r2 = llm_mod.call_llm("sys", "user", _Toy, "toy")
    assert r1.parsed.value == 42 and r2.parsed.value == 42
    assert r1.cache_hit is False and r2.cache_hit is True
    assert calls["n"] == 1  # second call served from cache
    load_settings.cache_clear()


def test_fallback_to_second_model(monkeypatch):
    """If the primary model fails, the fallback model is used."""
    monkeypatch.setenv("LLM_MODE", "live")
    from core.config import load_settings
    load_settings.cache_clear()
    settings = load_settings()

    def fake_completion(model, system, user, temperature):
        if model == settings.primary_model:
            raise RuntimeError("primary down")
        return '{"value": 5}'

    monkeypatch.setattr(llm_mod, "_completion", fake_completion)
    res = llm_mod.call_llm("sys", "user2", _Toy, "toy")
    assert res.parsed.value == 5
    assert res.fallback_used is True
    load_settings.cache_clear()


def test_all_fail_uses_mock(monkeypatch):
    """If every provider fails, the mock builder is the final fallback."""
    monkeypatch.setenv("LLM_MODE", "live")
    from core.config import load_settings
    load_settings.cache_clear()

    def boom(model, system, user, temperature):
        raise RuntimeError("no network")

    monkeypatch.setattr(llm_mod, "_completion", boom)
    res = llm_mod.call_llm("sys", "user3", _Toy, "toy", mock_builder=lambda: _Toy(value=1))
    assert res.parsed.value == 1
    assert res.model_used == "mock"
    assert res.fallback_used is True
    load_settings.cache_clear()


def test_agents_package_importable():
    """Sanity: the agents package imports without side effects."""
    assert agents is not None
    # Restore mock mode for the rest of the suite.
    os.environ["LLM_MODE"] = "mock"
    from core.config import load_settings
    load_settings.cache_clear()
