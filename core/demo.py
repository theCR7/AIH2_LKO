"""One-click Demo mode orchestration (ITERATIONS P9) — no Streamlit here.

``run_demo`` resets the data (preserving the LLM cache), generates the seeded
dataset, runs detection and pre-warms the SAR pipeline for the top-N cases so the
live demo replays instantly from cache. ``demo_fingerprint`` returns a stable hash
of the case/evidence IDs so two runs can be proven identical (PRD §4 determinism).

Deterministic for a given seed + ``config/rules.yaml`` (CLAUDE.md rule #11).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from core.agents.evidence import build_evidence_pack
from core.agents.orchestrator import run_sar_pipeline
from core.db import clear_data, init_db, session_scope
from core.detection.runner import run_detection
from core.ingest.generator import generate
from core.models import CaseRow


@dataclass
class DemoResult:
    """Outcome of a Demo-mode run, enough to verify reproducibility."""

    dataset_id: str
    seed: int
    n_cases: int
    top_case_ids: list[str]
    prewarmed_draft_ids: list[str]
    cache_hit_ratio: float
    fingerprint: str
    details: dict = field(default_factory=dict)


def _top_case_ids(dataset_id: str, n: int) -> list[str]:
    """Return the top-``n`` case ids by score (ties broken by case_id for stability)."""
    run_id = f"RUN_{dataset_id}"
    with session_scope() as session:
        cases = session.query(CaseRow).filter(CaseRow.run_id == run_id).all()
        ranked = sorted(cases, key=lambda c: (-c.score, c.case_id))
    return [c.case_id for c in ranked[:n]]


def demo_fingerprint(dataset_id: str) -> str:
    """Stable sha256 over every case id and its ordered evidence ids/summaries.

    Two runs on the same seed + rules must yield the same fingerprint; this is the
    machine-checkable form of the PRD determinism acceptance criterion.
    """
    run_id = f"RUN_{dataset_id}"
    with session_scope() as session:
        case_ids = sorted(
            c.case_id for c in session.query(CaseRow).filter(CaseRow.run_id == run_id).all()
        )
    payload: list[dict] = []
    for cid in case_ids:
        pack = build_evidence_pack(cid, persist=False)
        payload.append({
            "case_id": cid,
            "evidence": [{"id": it.id, "summary": it.summary} for it in pack.items],
        })
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def run_demo(seed: int = 42, prewarm_top_n: int = 2) -> DemoResult:
    """Reset data (keep LLM cache), regenerate, detect and pre-warm the SAR cache.

    Args:
        seed: generator seed (42 for the canonical demo dataset).
        prewarm_top_n: how many top-scoring cases to pre-draft so the live demo
            replays from cache.

    Returns:
        A :class:`DemoResult` including the determinism fingerprint and the
        observed cache-hit ratio across the pre-warm drafts (1.0 once warm, in
        live mode; 0.0 in mock mode, which has no cache by design).
    """
    init_db()
    clear_data(keep_llm_cache=True)

    generate(seed=seed, persist=True, write_csv=False)
    dataset_id = f"demo_seed{seed}"
    summary = run_detection(dataset_id)

    top_ids = _top_case_ids(dataset_id, prewarm_top_n)
    draft_ids: list[str] = []
    cache_hits = 0
    cache_total = 0
    for cid in top_ids:
        result = run_sar_pipeline(cid)
        draft_ids.append(result.draft_id)
        for step in result.trace:
            if step.model == "deterministic":
                continue  # evidence/validator steps never hit the LLM cache
            cache_total += 1
            if step.cache_hit:
                cache_hits += 1

    ratio = (cache_hits / cache_total) if cache_total else 0.0
    return DemoResult(
        dataset_id=dataset_id,
        seed=seed,
        n_cases=summary.n_cases,
        top_case_ids=top_ids,
        prewarmed_draft_ids=draft_ids,
        cache_hit_ratio=round(ratio, 3),
        fingerprint=demo_fingerprint(dataset_id),
        details={"n_alerts": summary.n_alerts, "duration_ms": summary.duration_ms},
    )
