"""LiteLLM gateway wrapper — Phase 0 stub (ARCHITECTURE §7).

Intentionally not implemented in Phase 0 (foundation + data + detection only).
Phase 1 fills this in as the single entry point for every LLM call
(CLAUDE.md hard rule #3): provider fallback chain (Gemini -> Groq -> mock),
prompt-hash cache, retries with backoff, JSON-mode + Pydantic parse, and an
offline ``LLM_MODE=mock`` path. No other module may call providers directly.
"""

from __future__ import annotations


def complete(*args, **kwargs):  # pragma: no cover - Phase 1 implementation
    """Placeholder for the LiteLLM completion wrapper (implemented in Phase 1)."""
    raise NotImplementedError("LLM wrapper is implemented in Phase 1 (no LLM in Phase 0).")
