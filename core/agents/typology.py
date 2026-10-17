"""Typology Agent (LLM) — classify a case's laundering typology (PRD F5.2).

Sends the compact EvidencePack to the gateway and parses a ``TypologyResult``
(typology, confidence, rationale, cited evidence_ids). A deterministic mock
builder provides the offline/fallback classification from the detected patterns.
"""

from __future__ import annotations

from functools import lru_cache

from core.agents.evidence import pack_to_prompt
from core.agents.llm import LLMResult, call_llm
from core.config import CONFIG_DIR
from core.schemas import EvidencePack, TypologyResult

# Dominant detector pattern -> canonical typology label.
_PATTERN_TYPOLOGY = {
    "cycle": "Layering via circular transfers",
    "fan_in": "Structuring / smurfing",
    "fan_out": "Mule fan-out distribution",
    "shared_identifier": "Account takeover / shared device",
    "passthrough": "Rapid pass-through",
}


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (CONFIG_DIR / "prompts" / "typology.md").read_text(encoding="utf-8")


def _mock_typology(pack: EvidencePack) -> TypologyResult:
    """Deterministic typology from the detected patterns (offline/fallback)."""
    patterns = pack.patterns
    pattern_ids = [it.id for it in pack.items if it.kind == "pattern"] or \
        [it.id for it in pack.items[:1]]
    if len({*patterns}) >= 3:
        typology = "Mixed typology"
    else:
        typology = _PATTERN_TYPOLOGY.get(patterns[0] if patterns else "", "Mixed typology")
    rationale = ("Classification derived from the detected patterns "
                 f"({', '.join(patterns)}) and their supporting evidence.")
    return TypologyResult(typology=typology, confidence=0.9, rationale=rationale,
                          evidence_ids=pattern_ids)


def classify_typology(pack: EvidencePack) -> tuple[TypologyResult, LLMResult]:
    """Classify the case typology, returning the result and the gateway metadata."""
    result = call_llm(
        system=_system_prompt(),
        user=pack_to_prompt(pack),
        schema=TypologyResult,
        purpose="typology",
        mock_builder=lambda: _mock_typology(pack),
    )
    typology = result.parsed
    assert isinstance(typology, TypologyResult)
    # Keep only evidence ids that actually exist in the pack.
    valid_ids = {it.id for it in pack.items}
    typology.evidence_ids = [e for e in typology.evidence_ids if e in valid_ids] or \
        [it.id for it in pack.items if it.kind == "pattern"][:1]
    return typology, result
