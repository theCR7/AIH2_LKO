"""Pydantic contracts for RingSight (ARCHITECTURE.md §5).

These typed models are the boundary between deterministic core logic and the
LLM agents (later phases). LLM output must always be parsed into these models
(CLAUDE.md hard rule #4). Kept free of any DB or Streamlit imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Detection / alert contracts --------------------------------------------


class Alert(BaseModel):
    """A single detector hit. Mirrors the ``alerts`` table."""

    alert_id: str  # "AL-0001"
    pattern: str  # cycle | fan_in | fan_out | shared_identifier | passthrough
    accounts: list[str]
    txn_ids: list[str]
    total_amount: float
    reason: str  # human-readable explanation
    severity: str = "medium"  # low | medium | high


class AccountRisk(BaseModel):
    """Explainable account risk score."""

    account_id: str
    score: float
    band: str  # high | medium | low
    explanation: list[str]  # ["+35 member of cycle", "+10 high betweenness"]


class CaseSummary(BaseModel):
    """A grouped set of alerts sharing accounts (connected component)."""

    case_id: str  # "C-001"
    title: str
    patterns: list[str]
    accounts: list[str]
    score: float
    status: str = "New"
    total_amount: float = 0.0
    n_txns: int = 0


class RunSummary(BaseModel):
    """Result of a full detection run over a dataset."""

    run_id: str
    n_txns: int
    n_accounts: int
    duration_ms: int
    n_alerts: int
    n_cases: int
    alerts_by_pattern: dict[str, int] = Field(default_factory=dict)


# --- Metrics contract --------------------------------------------------------


class PatternMetrics(BaseModel):
    """Precision / recall / F1 for one pattern vs ground truth."""

    pattern: str
    level: str  # "ring" | "txn"
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


# --- SAR / agent contracts (ARCHITECTURE §5; used from later phases) ----------


class EvidenceItem(BaseModel):
    id: str  # "E7"
    kind: Literal["txn", "identifier", "metric", "pattern"]
    summary: str  # "T000412: ACC_0018 -> ACC_0033, 48,200.00 USD, 2026-09-03 10:14"
    data: dict


class EvidencePack(BaseModel):
    case_id: str
    subjects: list[dict]  # account_id, name, bank, risk_score
    patterns: list[str]
    totals: dict  # total_amount, n_txns, date_range
    items: list[EvidenceItem]  # cap ~40 items to stay under free-tier TPM


class TypologyResult(BaseModel):
    typology: str
    confidence: float
    rationale: str
    evidence_ids: list[str]


class NarrativeSentence(BaseModel):
    text: str
    evidence_ids: list[str]  # MUST be non-empty for every sentence


class SARNarrative(BaseModel):
    summary: list[NarrativeSentence]
    subjects: list[NarrativeSentence]
    activity: list[NarrativeSentence]
    red_flags: list[NarrativeSentence]
    conclusion: list[NarrativeSentence]


class ValidationIssue(BaseModel):
    section: str
    index: int
    problem: str


class ValidationResult(BaseModel):
    grounding_score: float  # 0-100
    issues: list[ValidationIssue]
    passed: bool


class ConfidenceSignals(BaseModel):
    """Logged per draft; not used to gate in MVP (M.Tech research hook)."""

    evidence_coverage: float
    validator_pass_rate_first_try: float
    retries_used: int
    llm_self_confidence: float | None = None
    fallback_used: bool = False
    data_quality_flags: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    """One step in the SAR agent pipeline, shown in the Agent Trace panel (F5.6)."""

    step: str  # "Evidence Builder", "Typology Agent", ...
    model: str = "deterministic"
    latency_ms: int = 0
    cache_hit: bool = False
    retries: int = 0
    notes: str = ""
