"""Narrative Agent (Phase 1+) — LLM drafts the 5-section SAR narrative.

Later phase: produce ``SARNarrative`` where every sentence carries non-empty
``evidence_ids``; retries on validator feedback (max rounds in rules.yaml).
Phase 0 placeholder only.
"""

from __future__ import annotations
