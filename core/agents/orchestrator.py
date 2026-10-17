"""SAR drafting orchestrator (PRD F5) — plain-Python state machine.

Pipeline: Evidence Builder -> Typology -> Narrative <-> Validator (retry up to
``LLM_MAX_RETRIES``) -> persist versioned ``sar_drafts`` + ``audit_log`` entry +
``decision_log`` (ConfidenceSignals). Never raises on LLM failure — the agents
fall back to deterministic mock output (CLAUDE.md rule #7).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.agents.evidence import build_evidence_pack
from core.agents.narrative import draft_narrative
from core.agents.typology import classify_typology
from core.agents.validator import validate_narrative
from core.audit import record_audit
from core.config import load_settings
from core.db import init_db, session_scope
from core.models import DecisionLog, SarDraft
from core.schemas import (
    ConfidenceSignals,
    EvidencePack,
    SARNarrative,
    TraceStep,
    TypologyResult,
    ValidationResult,
)
from core.utils import utcnow


@dataclass
class SarPipelineResult:
    """Everything the UI needs after a drafting run."""

    case_id: str
    draft_id: str
    version: int
    pack: EvidencePack
    typology: TypologyResult
    narrative: SARNarrative
    validation: ValidationResult
    trace: list[TraceStep]
    status: str
    elapsed_ms: int
    signals: ConfidenceSignals
    fallback_used: bool = False
    extra: dict = field(default_factory=dict)


def _issues_as_feedback(validation: ValidationResult) -> list[str]:
    return [f"{i.section}[{i.index}]: {i.problem}" for i in validation.issues]


def _cited_ids(narrative: SARNarrative) -> set[str]:
    ids: set[str] = set()
    for section in ("summary", "subjects", "activity", "red_flags", "conclusion"):
        for sent in getattr(narrative, section):
            ids.update(sent.evidence_ids)
    return ids


def _next_version(case_id: str) -> int:
    with session_scope() as session:
        existing = session.query(SarDraft).filter(SarDraft.case_id == case_id).all()
        return max((d.version for d in existing), default=0) + 1


def run_sar_pipeline(case_id: str) -> SarPipelineResult:
    """Run the full SAR drafting pipeline for a case and persist the draft."""
    init_db()
    settings = load_settings()
    trace: list[TraceStep] = []
    t_start = time.perf_counter()

    # 1. Evidence Builder (deterministic).
    t0 = time.perf_counter()
    pack = build_evidence_pack(case_id)
    trace.append(TraceStep(step="Evidence Builder", model="deterministic",
                           latency_ms=int((time.perf_counter() - t0) * 1000),
                           notes=f"{len(pack.items)} evidence items"))

    # 2. Typology Agent.
    typology, typo_res = classify_typology(pack)
    trace.append(TraceStep(step="Typology Agent", model=typo_res.model_used,
                           latency_ms=typo_res.latency_ms, cache_hit=typo_res.cache_hit,
                           notes=f"{typology.typology} (conf {typology.confidence:.2f})"))

    # 3. Narrative Agent.
    narrative, narr_res = draft_narrative(pack, typology)
    trace.append(TraceStep(step="Narrative Agent", model=narr_res.model_used,
                           latency_ms=narr_res.latency_ms, cache_hit=narr_res.cache_hit,
                           notes="initial draft"))

    # 4. Validate (+ retries).
    validation = validate_narrative(narrative, pack)
    first_try_pass_rate = _pass_rate(validation)
    trace.append(TraceStep(step="Validator", model="deterministic",
                           notes=f"grounding {validation.grounding_score}%, "
                                 f"{len(validation.issues)} issue(s)"))

    retries = 0
    fallback_used = typo_res.fallback_used or narr_res.fallback_used
    while not validation.passed and retries < settings.llm_max_retries:
        retries += 1
        narrative, narr_res = draft_narrative(pack, typology,
                                              feedback=_issues_as_feedback(validation))
        fallback_used = fallback_used or narr_res.fallback_used
        trace.append(TraceStep(step="Narrative Agent", model=narr_res.model_used,
                               latency_ms=narr_res.latency_ms, cache_hit=narr_res.cache_hit,
                               retries=retries, notes=f"retry {retries}"))
        validation = validate_narrative(narrative, pack)
        trace.append(TraceStep(step="Validator", model="deterministic", retries=retries,
                               notes=f"grounding {validation.grounding_score}%, "
                                     f"{len(validation.issues)} issue(s)"))

    status = "drafted" if validation.passed else "needs_review"
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    # Confidence signals (M.Tech research hook).
    coverage = len(_cited_ids(narrative) & {it.id for it in pack.items}) / max(len(pack.items), 1)
    dq_flags: list[str] = []
    if not any(it.kind == "identifier" for it in pack.items):
        dq_flags.append("no_shared_identifiers")
    if any(it.kind == "txn" and not it.data.get("device_id") for it in pack.items):
        dq_flags.append("missing_device_id")
    signals = ConfidenceSignals(
        evidence_coverage=round(coverage, 3),
        validator_pass_rate_first_try=round(first_try_pass_rate, 3),
        retries_used=retries,
        llm_self_confidence=typology.confidence,
        fallback_used=fallback_used,
        data_quality_flags=dq_flags,
    )

    version = _next_version(case_id)
    draft_id = f"D-{case_id.split('-')[-1]}-v{version}"
    _persist(case_id, draft_id, version, typology, narrative, validation,
             narr_res.model_used, status, signals)

    return SarPipelineResult(
        case_id=case_id, draft_id=draft_id, version=version, pack=pack,
        typology=typology, narrative=narrative, validation=validation, trace=trace,
        status=status, elapsed_ms=elapsed_ms, signals=signals,
        fallback_used=fallback_used,
    )


def _pass_rate(validation: ValidationResult) -> float:
    """First-try pass rate from grounding score (0..1)."""
    return validation.grounding_score / 100.0


def _persist(case_id: str, draft_id: str, version: int, typology: TypologyResult,
             narrative: SARNarrative, validation: ValidationResult, model_used: str,
             status: str, signals: ConfidenceSignals) -> None:
    """Persist the draft, audit entry and decision-log row."""
    with session_scope() as session:
        session.add(SarDraft(
            draft_id=draft_id, case_id=case_id, version=version,
            typology_json=typology.model_dump_json(),
            narrative_json=narrative.model_dump_json(),
            grounding_score=validation.grounding_score, model_used=model_used,
            status=status,
        ))
        record_audit(session, actor="system", action="draft_created", case_id=case_id,
                     after={"draft_id": draft_id, "version": version,
                            "grounding_score": validation.grounding_score, "status": status})
        outcome = "drafted" if validation.passed else "needs_more_evidence"
        session.add(DecisionLog(
            case_id=case_id, draft_id=draft_id, step="sar_pipeline",
            signals_json=signals.model_dump_json(), outcome=outcome, created_at=utcnow(),
        ))
