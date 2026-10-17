"""RingSight — Home / Dashboard (Screen 1).

KPI cards, a one-click "Generate demo data & run detection" button, a cases-by-
pattern bar chart and a top-cases table. Run with ``streamlit run app/Home.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when Streamlit runs this script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.express as px
import streamlit as st

from app.components import data_access as da
from app.components.styles import TOKENS, kpi_card, render_sidebar, set_page
from core.config import load_rules
from core.utils import fmt_amount

set_page("Dashboard")
render_sidebar("Home")

st.markdown("<h2 class='rs-title'>RingSight · AI Fraud-Ring Investigation & SAR Copilot</h2>",
            unsafe_allow_html=True)
st.caption("Batch AML analysis over synthetic data — detect fraud rings, rank cases, "
           "and (Phase 1) draft evidence-grounded SARs.")

dataset = da.current_dataset()
version = da.refresh_token(dataset)


def _run_demo() -> None:
    """One-click: generate seed-42 data and run the full detection pipeline."""
    from core.detection.runner import run_detection
    from core.ingest.generator import generate
    with st.spinner("Generating synthetic data and running all detectors…"):
        generate(seed=42, persist=True, write_csv=True)
        st.session_state["rs_dataset"] = "demo_seed42"
        run_detection("demo_seed42")
    da.bump_version()
    st.success("Demo data generated and detection complete.")


col_btn, _ = st.columns([1, 3])
with col_btn:
    if st.button("▶ Generate demo data & run detection", type="primary",
                 use_container_width=True):
        _run_demo()
        st.rerun()

kpis = da.load_kpis(dataset, version)

if kpis["n_txns"] == 0:
    st.info("No data yet. Click **Generate demo data & run detection** above, "
            "or use the **Data** page to generate or upload transactions.")
    st.stop()

# --- KPI row (PRD F7.1) ------------------------------------------------------
rules = load_rules()
est_hours = kpis["n_cases"] * rules.sar.baseline_manual_minutes_per_case / 60.0
cards = [
    ("Txns analysed", f"{kpis['n_txns']:,}"),
    ("Open cases", f"{kpis['n_cases']}"),
    ("High-risk accounts", f"{kpis['high_risk']}"),
    ("Suspicious amount", fmt_amount(kpis["suspicious_amount"])),
    ("Avg grounding", "— (Phase 1)"),
    ("Est. hours saved*", f"{est_hours:.0f} h"),
]
cols = st.columns(len(cards))
for col, (label, value) in zip(cols, cards, strict=True):
    col.markdown(kpi_card(label, value), unsafe_allow_html=True)
st.caption("*Assumption: "
           f"{rules.sar.baseline_manual_minutes_per_case} min manual baseline per case "
           "(state as an assumption in the demo).")

st.divider()

left, right = st.columns([1, 1])

with left:
    st.subheader("Alerts by pattern")
    by_pattern = da.cases_by_pattern(dataset, version)
    if by_pattern.empty:
        st.caption("No alerts.")
    else:
        fig = px.bar(by_pattern, x="pattern", y="alerts",
                     color_discrete_sequence=[TOKENS["primary"]])
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis_title="", yaxis_title="alerts")
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Top cases")
    cases = da.load_cases(dataset, version)
    if cases.empty:
        st.caption("No cases above threshold.")
    else:
        top = cases.head(5)[["case_id", "title", "patterns", "score", "status"]]
        st.dataframe(top, use_container_width=True, hide_index=True)
        st.caption("Open the **Cases** page to filter and investigate.")
