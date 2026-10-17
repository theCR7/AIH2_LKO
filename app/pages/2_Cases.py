"""RingSight — Cases (Screen 3): filterable, ranked case list."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.components import data_access as da
from app.components.styles import render_sidebar, set_page
from app.components.ui import friendly_errors
from core.config import load_rules
from core.utils import fmt_amount

set_page("Cases")
render_sidebar("Cases")
st.markdown("<h2 class='rs-title'>Cases</h2>", unsafe_allow_html=True)

dataset = da.current_dataset()
version = da.refresh_token(dataset)
with friendly_errors("loading cases", stop=True):
    cases = da.load_cases(dataset, version)
rules = load_rules()

if cases.empty:
    st.info("No cases yet. Generate data and run detection on the **Data** page "
            "(or use the one-click button on **Home**).")
    st.stop()

# --- Filters -----------------------------------------------------------------
f1, f2, f3, f4 = st.columns([1.2, 1.2, 1, 1.4])
all_patterns = sorted({p.strip() for row in cases["patterns"] for p in row.split(",") if p})
pattern_sel = f1.multiselect("Pattern", all_patterns, default=[])
min_score = f2.slider("Min score", 0, 100, int(rules.cases.min_case_score))
status_sel = f3.multiselect("Status", sorted(cases["status"].unique()), default=[])
search = f4.text_input("Search title / case id", "")

view = cases[cases["score"] >= min_score]
if pattern_sel:
    view = view[view["patterns"].apply(lambda s: any(p in s for p in pattern_sel))]
if status_sel:
    view = view[view["status"].isin(status_sel)]
if search:
    q = search.lower()
    view = view[view.apply(lambda r: q in r["title"].lower() or q in r["case_id"].lower(),
                           axis=1)]

st.caption(f"{len(view)} of {len(cases)} cases "
           f"(default threshold ≥ {int(rules.cases.min_case_score)}).")

display = view.copy()
display["amount"] = display["total_amount"].apply(fmt_amount)
st.dataframe(
    display[["case_id", "title", "patterns", "accounts", "amount", "n_txns", "score", "status"]],
    use_container_width=True, hide_index=True,
    column_config={
        "case_id": "Case", "title": "Title", "patterns": "Pattern(s)",
        "accounts": "Accts", "amount": "Amount", "n_txns": "Txns",
        "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100,
                                                 format="%d"),
        "status": "Status",
    },
)

st.divider()
if not view.empty:
    pick = st.selectbox("Select a case to investigate", view["case_id"].tolist())
    if st.button("Investigate →", type="primary"):
        st.session_state["rs_case_id"] = pick
        st.success(f"Selected {pick}. Open the **Investigate** page (sidebar) for the "
                   "graph, evidence, SAR drafting and Ask-the-case Q&A.")
