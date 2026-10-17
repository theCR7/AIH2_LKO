"""Cached read helpers between the Streamlit UI and the core/DB layer.

Keeps heavy reads behind ``st.cache_data`` (conventions: use cache for heavy
reads). The cache is keyed by dataset and a ``version`` token the pages bump
after a generate/run so stale results never show.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.db import session_scope
from core.detection.runner import load_bundle, run_all_detectors
from core.models import AlertRow, CaseAccount, CaseRow, SarDraft, Transaction
from core.schemas import Alert


def current_dataset() -> str:
    """The dataset the UI is currently working with."""
    return st.session_state.get("rs_dataset", "demo_seed42")


def bump_version() -> None:
    """Invalidate cached reads after data changes."""
    st.session_state["rs_data_version"] = st.session_state.get("rs_data_version", 0) + 1


def _version() -> int:
    return st.session_state.get("rs_data_version", 0)


@st.cache_data(show_spinner=False)
def load_cases(dataset_id: str, version: int) -> pd.DataFrame:
    """Return persisted cases for a dataset as a DataFrame, ranked by score."""
    run_id = f"RUN_{dataset_id}"
    with session_scope() as session:
        rows = session.query(CaseRow).filter(CaseRow.run_id == run_id).all()
        data = [
            {
                "case_id": c.case_id, "title": c.title,
                "patterns": ", ".join(json.loads(c.patterns_json)),
                "accounts": len(json.loads(c.accounts_json)),
                "total_amount": c.total_amount, "n_txns": c.n_txns,
                "score": c.score, "status": c.status,
            }
            for c in rows
        ]
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def load_kpis(dataset_id: str, version: int) -> dict:
    """Return headline KPIs for the dashboard."""
    run_id = f"RUN_{dataset_id}"
    with session_scope() as session:
        n_txns = (session.query(Transaction)
                  .filter(Transaction.dataset_id == dataset_id).count())
        cases = session.query(CaseRow).filter(CaseRow.run_id == run_id).all()
        alerts = session.query(AlertRow).filter(AlertRow.run_id == run_id).all()
        case_ids = [c.case_id for c in cases]
        high_risk_accts = 0
        drafts = []
        if case_ids:
            high_risk_accts = (
                session.query(CaseAccount)
                .filter(CaseAccount.case_id.in_(case_ids), CaseAccount.risk_score >= 70)
                .count()
            )
            drafts = session.query(SarDraft).filter(SarDraft.case_id.in_(case_ids)).all()
    # Latest draft per case for avg grounding.
    latest: dict[str, SarDraft] = {}
    for d in drafts:
        if d.case_id not in latest or d.version > latest[d.case_id].version:
            latest[d.case_id] = d
    n_drafted = len(latest)
    avg_grounding = (sum(d.grounding_score for d in latest.values()) / n_drafted
                     if n_drafted else None)
    n_cases = len(cases)
    suspicious = sum(c.total_amount for c in cases)
    return {
        "n_txns": n_txns,
        "n_cases": n_cases,
        "high_risk": high_risk_accts,
        "suspicious_amount": suspicious,
        "n_alerts": len(alerts),
        "n_drafted": n_drafted,
        "avg_grounding": avg_grounding,
    }


@st.cache_data(show_spinner=False)
def cases_by_pattern(dataset_id: str, version: int) -> pd.DataFrame:
    """Count alerts per pattern for the dashboard bar chart."""
    run_id = f"RUN_{dataset_id}"
    with session_scope() as session:
        rows = session.query(AlertRow).filter(AlertRow.run_id == run_id).all()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.pattern] = counts.get(r.pattern, 0) + 1
    return pd.DataFrame({"pattern": list(counts), "alerts": list(counts.values())})


@st.cache_data(show_spinner=False)
def load_alerts(dataset_id: str, version: int) -> list[Alert]:
    """Recompute in-memory alerts (used by the metrics page)."""
    from core.config import load_rules
    bundle = load_bundle(dataset_id)
    return run_all_detectors(bundle, load_rules())


@st.cache_data(show_spinner=False)
def case_timeline(case_id: str, version: int) -> pd.DataFrame:
    """Return the case's transaction edges for the money-flow timeline (cached).

    Keyed by ``case_id`` + data ``version`` so the subgraph is loaded once per
    run instead of on every rerun (ITERATIONS P9 perf).
    """
    from core.casegraph import load_case_subgraph
    sub = load_case_subgraph(case_id)
    if not sub.edges:
        return pd.DataFrame()
    tdf = pd.DataFrame(sub.edges)
    tdf["flow"] = tdf["source"] + " → " + tdf["target"]
    return tdf


def refresh_token(dataset_id: str) -> int:
    """Convenience: the version token for the active dataset (for cache keys)."""
    _ = dataset_id
    return _version()
