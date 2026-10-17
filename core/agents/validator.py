"""Validator Agent (Phase 1+) — the grounding differentiator (ARCHITECTURE §6).

Later phase: deterministic checks per sentence (evidence_ids exist; amounts,
dates, account IDs match cited evidence; totals match metric items; speculation
lexicon) plus optional LLM judge, returning a ``ValidationResult`` with a
Grounding Score. Phase 0 placeholder only.
"""

from __future__ import annotations
