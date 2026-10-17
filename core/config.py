"""Configuration loading for RingSight.

Loads environment variables from ``.env`` and detection/scoring thresholds
from ``config/rules.yaml`` into typed Pydantic models so typos fail fast
(CLAUDE.md hard rule #2: all thresholds/weights come from rules.yaml).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# --- Project paths -----------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
RULES_PATH = CONFIG_DIR / "rules.yaml"

# Load .env once at import time (secrets only from .env — hard rule #9).
load_dotenv(PROJECT_ROOT / ".env")


# --- Rules models (mirror config/rules.yaml) ---------------------------------


class CycleRules(BaseModel):
    min_length: int = 3
    max_length: int = 6
    max_window_hours: int = 168
    min_value_retention: float = 0.80
    min_amount: float = 1000
    max_candidates: int = 50000


class FanInRules(BaseModel):
    min_senders: int = 5
    max_senders: int = 100        # more payers than this looks like an institution
    max_amount_each: float = 10000
    window_hours: int = 48


class FanOutRules(BaseModel):
    min_receivers: int = 5
    max_receivers: int = 100      # more receivers than this looks like a mass payer
    min_total: float = 50000
    window_hours: int = 48


class SharedIdRules(BaseModel):
    min_accounts: int = 3
    id_types: list[str] = Field(default_factory=lambda: ["ip", "device"])


class PassthroughRules(BaseModel):
    min_outflow_ratio: float = 0.90
    window_hours: int = 24
    min_inflow: float = 5000


class CentralityRules(BaseModel):
    pagerank_weight: float = 10
    betweenness_weight: float = 10
    # Exact betweenness is O(V*E); above this node count switch to a seeded sample.
    betweenness_exact_max_nodes: int = 2000
    betweenness_sample_k: int = 256
    betweenness_seed: int = 42


class ScoringRules(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)
    centrality: CentralityRules = Field(default_factory=CentralityRules)
    bands: dict[str, float] = Field(default_factory=lambda: {"high": 70, "medium": 40})


class CaseRules(BaseModel):
    min_case_score: float = 40
    # Components with more accounts are split into one case per alert (see cases.py).
    max_case_accounts: int = 50


class MetricsRules(BaseModel):
    ring_match_threshold: float = 0.6


class ValidatorRules(BaseModel):
    amount_tolerance: float = 0.01
    use_llm_judge: bool = False
    speculation_lexicon: list[str] = Field(default_factory=list)


class SarRules(BaseModel):
    max_evidence_items: int = 40
    max_repair_rounds: int = 2
    baseline_manual_minutes_per_case: int = 240


class IbmIngestRules(BaseModel):
    """Sampling knobs for the IBM AML (HI-Small) loader (PRD F1.4)."""

    max_transactions: int = 30000   # total sampled rows (keeps detection tractable)
    context_share: float = 0.6      # share of the normal budget drawn from laundering neighbours
    seed: int = 42                  # deterministic sampling
    currency: str = "US Dollar"     # keep one currency so amounts are comparable (labelled USD)


class IngestRules(BaseModel):
    ibm: IbmIngestRules = Field(default_factory=IbmIngestRules)


class Rules(BaseModel):
    """Typed view over ``config/rules.yaml`` (CLAUDE.md hard rule #2)."""

    version: int = 1
    currency: str = "USD"
    ingest: IngestRules = Field(default_factory=IngestRules)
    exclude_account_types: list[str] = Field(default_factory=lambda: ["merchant", "payroll"])
    cycles: CycleRules = Field(default_factory=CycleRules)
    fan_in: FanInRules = Field(default_factory=FanInRules)
    fan_out: FanOutRules = Field(default_factory=FanOutRules)
    shared_identifiers: SharedIdRules = Field(default_factory=SharedIdRules)
    passthrough: PassthroughRules = Field(default_factory=PassthroughRules)
    scoring: ScoringRules = Field(default_factory=ScoringRules)
    cases: CaseRules = Field(default_factory=CaseRules)
    metrics: MetricsRules = Field(default_factory=MetricsRules)
    validator: ValidatorRules = Field(default_factory=ValidatorRules)
    sar: SarRules = Field(default_factory=SarRules)


# --- Environment settings ----------------------------------------------------


class Settings(BaseModel):
    """Runtime settings sourced from environment variables (.env)."""

    database_url: str = "sqlite:///data/ringsight.db"
    primary_model: str = "gemini/gemini-2.5-flash"
    fallback_model: str = "groq/openai/gpt-oss-120b"
    ollama_model: str | None = None
    llm_mode: str = "live"  # live | mock
    llm_max_retries: int = 2
    llm_temperature: float = 0.0
    analyst_name: str = "Demo Analyst"


@lru_cache(maxsize=1)
def load_rules(path: str | Path | None = None) -> Rules:
    """Load and validate ``config/rules.yaml`` into a typed :class:`Rules`.

    Cached so repeated detector calls do not re-read the file. A bad key or
    type raises a Pydantic ``ValidationError`` immediately.
    """
    rules_path = Path(path) if path else RULES_PATH
    raw = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    return Rules.model_validate(raw)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Read environment settings from the process environment (.env already loaded)."""
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/ringsight.db"),
        primary_model=os.getenv("PRIMARY_MODEL", "gemini/gemini-2.5-flash"),
        fallback_model=os.getenv("FALLBACK_MODEL", "groq/openai/gpt-oss-120b"),
        ollama_model=os.getenv("OLLAMA_MODEL") or None,
        llm_mode=os.getenv("LLM_MODE", "live"),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        analyst_name=os.getenv("ANALYST_NAME", "Demo Analyst"),
    )
