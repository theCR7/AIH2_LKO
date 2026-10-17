"""LiteLLM gateway — the single entry point for every LLM call (CLAUDE.md rule #3).

Behaviour (ARCHITECTURE §7):
- Provider chain ``PRIMARY_MODEL`` -> ``FALLBACK_MODEL`` -> ``mock``.
- JSON output parsed into a Pydantic schema; one repair attempt on parse failure.
- ``tenacity`` exponential backoff with jitter on HTTP 429/5xx (max 3 per model).
- SQLite cache keyed by ``sha256(purpose + prompt_version + schema + system + user)``.
  The model is stored but NOT part of the key, so a fallback-model response still
  replays as a cache hit in the demo (CLAUDE.md rule #6; this is why the key does
  not follow P1's literal ``model+system+user`` wording).
- ``LLM_MODE=mock`` returns deterministic output from the caller's ``mock_builder``.
- Temperature 0 and no volatile values in prompts keep the cache stable (rule #12).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from core.config import load_settings
from core.db import init_db, session_scope
from core.models import LlmCache
from core.utils import utcnow

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    """Outcome of a single gateway call."""

    parsed: BaseModel | None
    raw_text: str
    model_used: str
    latency_ms: int
    cache_hit: bool
    fallback_used: bool


def _cache_key(purpose: str, prompt_version: str, schema_name: str,
               system: str, user: str) -> str:
    """Deterministic cache key — model intentionally excluded (rule #6)."""
    payload = "\x1f".join([purpose, prompt_version, schema_name, system, user])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of a model response (handles code fences)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _completion(model: str, system: str, user: str, temperature: float) -> str:
    """Call litellm for one model and return the raw text. Monkeypatched in tests."""
    import litellm  # imported lazily so offline/mock runs never need it

    resp = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def _call_with_retry(model: str, system: str, user: str, temperature: float) -> str:
    """Call one model with exponential backoff on transient errors."""
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_random_exponential,
    )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=8),
        retry=retry_if_exception_type(Exception),
    )
    def _do() -> str:
        return _completion(model, system, user, temperature)

    return _do()


def _parse(schema: type[T], raw: str) -> T:
    """Parse raw model text into the schema, extracting JSON if needed."""
    try:
        return schema.model_validate_json(raw)
    except ValidationError:
        return schema.model_validate_json(_extract_json(raw))


def _cache_get(key: str) -> tuple[str, str] | None:
    """Return (response_text, model) for a cache key, or None."""
    with session_scope() as session:
        row = session.get(LlmCache, key)
        if row:
            return row.response_text, row.model
    return None


def _cache_put(key: str, purpose: str, prompt_version: str, model: str, text: str) -> None:
    """Store a response in the cache (idempotent)."""
    with session_scope() as session:
        if session.get(LlmCache, key) is None:
            session.add(LlmCache(prompt_hash=key, purpose=purpose,
                                 prompt_version=prompt_version, model=model,
                                 response_text=text, created_at=utcnow()))


def call_llm(system: str, user: str, schema: type[T], purpose: str,
             mock_builder: Callable[[], T] | None = None,
             prompt_version: str = "1") -> LLMResult:
    """Call the LLM (or mock) and return a parsed, typed result.

    Args:
        system: system prompt (stable — no volatile values).
        user: user prompt (stable — no volatile values).
        schema: Pydantic model the response is parsed into.
        purpose: short tag (e.g. "typology", "narrative") for cache + trace.
        mock_builder: deterministic fallback producing a ``schema`` instance; used
            in ``LLM_MODE=mock`` and as the final fallback if all providers fail.
        prompt_version: bump to invalidate cached responses when a prompt changes.
    """
    settings = load_settings()
    t0 = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - t0) * 1000)

    # --- Mock mode -----------------------------------------------------------
    if settings.llm_mode == "mock":
        if mock_builder is None:
            raise RuntimeError(f"LLM_MODE=mock but no mock_builder for purpose '{purpose}'.")
        parsed = mock_builder()
        return LLMResult(parsed=parsed, raw_text=parsed.model_dump_json(),
                         model_used="mock", latency_ms=elapsed(), cache_hit=False,
                         fallback_used=False)

    init_db()
    key = _cache_key(purpose, prompt_version, schema.__name__, system, user)

    # --- Cache hit -----------------------------------------------------------
    cached = _cache_get(key)
    if cached is not None:
        text, model = cached
        try:
            parsed = _parse(schema, text)
            return LLMResult(parsed=parsed, raw_text=text, model_used=model,
                             latency_ms=elapsed(), cache_hit=True, fallback_used=False)
        except ValidationError:
            logger.warning("Cached response for %s failed to parse; recomputing.", purpose)

    # --- Live providers ------------------------------------------------------
    models = [settings.primary_model, settings.fallback_model]
    for idx, model in enumerate(models):
        try:
            raw = _call_with_retry(model, system, user, settings.llm_temperature)
            try:
                parsed = _parse(schema, raw)
            except ValidationError as exc:
                # One repair attempt with the error message appended.
                repair_user = (f"{user}\n\nYour previous reply failed JSON schema "
                               f"validation with: {exc}. Return ONLY valid JSON.")
                raw = _call_with_retry(model, system, repair_user, settings.llm_temperature)
                parsed = _parse(schema, raw)
            _cache_put(key, purpose, prompt_version, model, raw)
            return LLMResult(parsed=parsed, raw_text=raw, model_used=model,
                             latency_ms=elapsed(), cache_hit=False,
                             fallback_used=idx > 0)
        except Exception as exc:
            logger.warning("Model %s failed for %s: %s", model, purpose, exc)
            continue

    # --- Final fallback: mock ------------------------------------------------
    if mock_builder is not None:
        logger.warning("All providers failed for %s; using mock output.", purpose)
        parsed = mock_builder()
        return LLMResult(parsed=parsed, raw_text=parsed.model_dump_json(),
                         model_used="mock", latency_ms=elapsed(), cache_hit=False,
                         fallback_used=True)
    raise RuntimeError(f"All LLM providers failed for purpose '{purpose}' and no mock.")


def get_llm_status() -> dict:
    """Describe gateway readiness for the sidebar pill (no network call)."""
    settings = load_settings()
    if settings.llm_mode == "mock":
        return {"mode": "mock", "label": "Mock mode",
                "primary": settings.primary_model, "fallback": settings.fallback_model}
    return {
        "mode": "live",
        "label": "Live",
        "primary": settings.primary_model,
        "fallback": settings.fallback_model,
        "primary_key": bool(os.getenv("GEMINI_API_KEY")),
        "fallback_key": bool(os.getenv("GROQ_API_KEY")),
    }
