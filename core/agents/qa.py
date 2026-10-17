"""Ask-the-case Q&A agent (LLM) — grounded answers over the EvidencePack (P10a).

Answers an analyst's free-text question using ONLY the compact evidence pack for one
case, citing the exact ``E-ids`` it relied on and refusing out-of-scope questions.
Reuses the single LLM gateway (CLAUDE.md rule #3) and ships a deterministic mock
builder so the feature works offline and in the demo.
"""

from __future__ import annotations

import re
from functools import lru_cache

from core.agents.evidence import pack_to_prompt
from core.agents.llm import LLMResult, call_llm
from core.config import CONFIG_DIR
from core.schemas import CaseAnswer, EvidenceItem, EvidencePack

_ACCT_RE = re.compile(r"\bACC_\d{4,}\b", re.IGNORECASE)

# Question intents the deterministic mock can answer, matched by keyword.
_AMOUNT_WORDS = ("total", "amount", "how much", "sum", "value", "money", "volume")
_WHEN_WORDS = ("when", "date", "period", "timeframe", "time frame", "over what")
_WHO_WORDS = ("who", "which account", "which accounts", "subject", "subjects",
              "accounts involved", "parties")
_PATTERN_WORDS = ("pattern", "typology", "scheme", "laundering", "red flag", "red flags",
                  "why flagged", "why was", "suspicious", "cycle", "fan", "smurf",
                  "structuring", "pass-through", "passthrough", "layering", "mule")
# Out-of-scope cues the mock always refuses (advice / legal / unrelated).
_OUT_OF_SCOPE = ("weather", "stock", "joke", "recommend", "should i", "advice",
                 "legal", "lawyer", "arrest", "prosecute", "file the sar",
                 "who is the ceo", "capital of")


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (CONFIG_DIR / "prompts" / "qa.md").read_text(encoding="utf-8")


def _items_by_kind(pack: EvidencePack, kind: str) -> list[EvidenceItem]:
    return [it for it in pack.items if it.kind == kind]


def _case_metric(pack: EvidencePack) -> EvidenceItem | None:
    metrics = [it for it in _items_by_kind(pack, "metric") if "n_txns" in it.data]
    return metrics[-1] if metrics else None


def _refuse(msg: str) -> CaseAnswer:
    return CaseAnswer(answer=msg, evidence_ids=[], refused=True)


def _mock_answer(pack: EvidencePack, question: str) -> CaseAnswer:
    """Deterministic, evidence-grounded answer for offline/mock mode.

    Routes the question to an intent by keyword and echoes the exact facts from the
    matching evidence items, citing their ids. Refuses when nothing in the pack
    applies, so the demo shows both grounded answers and out-of-scope refusal.
    """
    q = question.lower().strip()
    if not q:
        return _refuse("Please ask a question about this case.")
    if any(term in q for term in _OUT_OF_SCOPE):
        return _refuse("I can only answer questions grounded in this case's evidence.")

    # Specific account mentioned → cite the evidence items referencing it.
    mentioned = {m.upper() for m in _ACCT_RE.findall(question)}
    if mentioned:
        cites: list[str] = []
        facts: list[str] = []
        for it in pack.items:
            accts = {a.upper() for a in it.data.get("accounts", [])}
            accts |= {str(it.data.get(f, "")).upper() for f in ("sender", "receiver")}
            if accts & mentioned:
                cites.append(it.id)
                facts.append(it.summary)
            if len(cites) >= 4:
                break
        if cites:
            return CaseAnswer(
                answer=f"For {', '.join(sorted(mentioned))}: " + " ".join(facts[:3]),
                evidence_ids=cites)
        return _refuse("Those accounts are not part of this case's evidence.")

    metric = _case_metric(pack)
    if any(w in q for w in _AMOUNT_WORDS) and metric:
        return CaseAnswer(answer=metric.summary, evidence_ids=[metric.id])
    if any(w in q for w in _WHEN_WORDS) and metric:
        return CaseAnswer(
            answer=f"The activity spans {metric.data['date_range']}.",
            evidence_ids=[metric.id])
    if any(w in q for w in _WHO_WORDS):
        pats = _items_by_kind(pack, "pattern")
        subs = ", ".join(s["account_id"] for s in pack.subjects[:6])
        cite = [pats[0].id] if pats else ([pack.items[0].id] if pack.items else [])
        if subs and cite:
            return CaseAnswer(
                answer=f"The subjects in case {pack.case_id} are {subs}.", evidence_ids=cite)
    if any(w in q for w in _PATTERN_WORDS):
        pats = _items_by_kind(pack, "pattern")
        if pats:
            return CaseAnswer(
                answer="Detected patterns: " + " ".join(p.summary for p in pats[:3]),
                evidence_ids=[p.id for p in pats[:3]])

    # Fallback: if the question names any pattern token present, answer; else refuse.
    return _refuse("I can only answer questions grounded in this case's evidence "
                   "(subjects, patterns, amounts and dates). Try asking about the "
                   "total amount, the accounts involved, or the detected patterns.")


def answer_question(pack: EvidencePack, question: str) -> tuple[CaseAnswer, LLMResult]:
    """Answer a question about a case from its evidence pack.

    Returns the parsed :class:`CaseAnswer` and the gateway metadata (model, cache).
    Any cited ids not present in the pack are dropped so the UI never shows a
    dangling citation.
    """
    user = f"QUESTION: {question.strip()}\n\n{pack_to_prompt(pack)}"
    result = call_llm(
        system=_system_prompt(),
        user=user,
        schema=CaseAnswer,
        purpose="qa",
        mock_builder=lambda: _mock_answer(pack, question),
    )
    answer = result.parsed
    assert isinstance(answer, CaseAnswer)
    valid_ids = {it.id for it in pack.items}
    answer.evidence_ids = [e for e in answer.evidence_ids if e in valid_ids]
    if not answer.refused and not answer.evidence_ids:
        # No valid citations survived → treat as ungrounded and refuse.
        answer.refused = True
        answer.answer = ("I could not ground an answer in this case's evidence. "
                         "Please rephrase around the case's accounts, amounts or patterns.")
    return answer, result
