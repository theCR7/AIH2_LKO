"""Narrative Agent (LLM) — draft the 5-section SAR narrative (PRD F5.3).

Every factual sentence carries non-empty ``evidence_ids``. The deterministic mock
builder constructs each sentence directly from evidence items (echoing their exact
amounts/dates/accounts and citing them), so the mock narrative passes the
validator at 100% grounding — the safe offline/demo path.
"""

from __future__ import annotations

from functools import lru_cache

from core.agents.evidence import pack_to_prompt
from core.agents.llm import LLMResult, call_llm
from core.config import CONFIG_DIR
from core.schemas import EvidenceItem, EvidencePack, NarrativeSentence, SARNarrative, TypologyResult
from core.utils import fmt_amount


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (CONFIG_DIR / "prompts" / "narrative.md").read_text(encoding="utf-8")


def _items_by_kind(pack: EvidencePack, kind: str) -> list[EvidenceItem]:
    return [it for it in pack.items if it.kind == kind]


def _case_metric(pack: EvidencePack) -> EvidenceItem | None:
    """The case-total metric item (carries total_amount, n_txns, date_range)."""
    metrics = [it for it in _items_by_kind(pack, "metric") if "n_txns" in it.data]
    return metrics[-1] if metrics else None


def _mock_narrative(pack: EvidencePack, typology: TypologyResult) -> SARNarrative:
    """Build a fully-grounded template narrative from the evidence pack."""
    patterns_items = _items_by_kind(pack, "pattern")
    txn_items = _items_by_kind(pack, "txn")
    ident_items = _items_by_kind(pack, "identifier")
    metric = _case_metric(pack)

    def s(text: str, ids: list[str]) -> NarrativeSentence:
        return NarrativeSentence(text=text, evidence_ids=ids)

    summary: list[NarrativeSentence] = []
    if metric:
        total = fmt_amount(metric.data["total_amount"])
        rng = metric.data["date_range"]
        n = metric.data["n_txns"]
        summary.append(s(f"During the period {rng}, {total} moved across {n} transactions "
                         f"in connection with case {pack.case_id}.", [metric.id]))
    summary.append(s(f"The activity is consistent with {typology.typology}.",
                     typology.evidence_ids))

    subjects: list[NarrativeSentence] = []
    for subj in pack.subjects[:3]:
        aid = subj["account_id"]
        cite = next((it.id for it in patterns_items
                     if aid in it.data.get("accounts", [])), None)
        cite = cite or next((it.id for it in txn_items
                             if aid in (it.data.get("sender"), it.data.get("receiver"))), None)
        if cite:
            subjects.append(s(f"Account {aid} is a subject in the flagged activity.", [cite]))
    if not subjects and patterns_items:
        subjects.append(s("The subjects are the accounts named in the detected patterns.",
                          [patterns_items[0].id]))

    activity: list[NarrativeSentence] = []
    for it in patterns_items:
        activity.append(s(it.summary, [it.id]))  # echoes exact facts -> grounded
    for it in txn_items[:3]:
        d = it.data
        activity.append(s(f"Transaction {d['txn_id']} transferred {fmt_amount(d['amount'])} "
                          f"from {d['sender']} to {d['receiver']} on {d['date']}.", [it.id]))

    red_flags: list[NarrativeSentence] = []
    for it in ident_items:
        red_flags.append(s(it.summary, [it.id]))
    if patterns_items:
        red_flags.append(s("The timing and structure of the transfers are inconsistent with "
                           "ordinary commercial activity.", [patterns_items[0].id]))

    conclusion: list[NarrativeSentence] = []
    if metric:
        conclusion.append(s(f"Based on {metric.data['n_txns']} transactions totalling "
                            f"{fmt_amount(metric.data['total_amount'])}, this activity "
                            f"warrants a Suspicious Activity Report.", [metric.id]))
    else:
        conclusion.append(s("The detected activity warrants a Suspicious Activity Report.",
                            [patterns_items[0].id] if patterns_items else []))

    return SARNarrative(summary=summary, subjects=subjects, activity=activity,
                        red_flags=red_flags, conclusion=conclusion)


def draft_narrative(pack: EvidencePack, typology: TypologyResult,
                    feedback: list[str] | None = None) -> tuple[SARNarrative, LLMResult]:
    """Draft (or repair) the SAR narrative; returns the narrative and gateway metadata."""
    user = (f"TYPOLOGY: {typology.typology} (confidence {typology.confidence})\n"
            f"{pack_to_prompt(pack)}")
    if feedback:
        user += "\n\nVALIDATOR FEEDBACK (fix only these sentences):\n" + \
            "\n".join(f"- {f}" for f in feedback)
    result = call_llm(
        system=_system_prompt(),
        user=user,
        schema=SARNarrative,
        purpose="narrative",
        mock_builder=lambda: _mock_narrative(pack, typology),
        # Different feedback must not collide in the cache across retries.
        prompt_version=f"1.{len(feedback)}" if feedback else "1",
    )
    narrative = result.parsed
    assert isinstance(narrative, SARNarrative)
    return narrative, result
