"""Detect screen: headline KPIs and the ranked case queue."""

from __future__ import annotations

import streamlit as st

from app.components import components as c
from app.components import data_access as da
from app.components.theme import risk_band
from app.components.ui import friendly_errors
from core.config import load_rules
from core.utils import fmt_amount


def render() -> None:
    dataset = da.current_dataset()
    version = da.refresh_token(dataset)
    with friendly_errors("loading the case queue", stop=True):
        kpis = da.load_kpis(dataset, version)
        cases = da.load_cases(dataset, version)

    st.subheader("Case queue")

    c.kpi_row([
        ("Transactions analysed", f"{kpis['n_txns']:,}",
         "Every transaction scanned by the rule-based detectors."),
        ("Accounts", f"{kpis['n_accounts']:,}",
         "Distinct accounts seen across the dataset."),
        ("Cases flagged", f"{kpis['n_cases']}",
         "Groups of accounts linked by at least one detected pattern, above the "
         "case-score threshold."),
        ("Amount involved", fmt_amount(kpis["suspicious_amount"]),
         "Total value across the transactions inside flagged cases."),
    ])

    st.caption("")
    rules = load_rules()
    if cases.empty:
        c.empty_state("search_off", "No cases flagged",
                      "No loops or structuring patterns at the current thresholds. "
                      "Adjust them in the sidebar under Advanced, or load another dataset.")
        return

    threshold = int(rules.cases.min_case_score)
    hidden = int((cases["score"] < threshold).sum())
    view = cases[cases["score"] >= threshold].copy()
    view["Pattern"] = view["patterns"].apply(c.pattern_label)
    view["Band"] = view["score"].apply(lambda s: risk_band(s).title())
    view["Status"] = view["status"].map(
        {"New": "Flagged", "In Review": "In review", "Drafted": "Drafted",
         "Approved": "Approved", "Rejected": "Dismissed"}).fillna(view["status"])
    table = view[["case_id", "Pattern", "accounts", "total_amount", "score",
                  "Band", "Status"]]

    if table.empty:
        c.empty_state("search_off", "Nothing above the threshold",
                      f"All cases score below {threshold}. Lower the case threshold in "
                      "config/rules.yaml to review weaker signals.")
        return
    hidden_note = f" {hidden} weaker case(s) are below the score {threshold} and hidden." \
        if hidden else ""
    st.caption(f"{len(table)} cases, highest risk first. Select a row to investigate."
               f"{hidden_note}")
    event = st.dataframe(
        table, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "case_id": st.column_config.TextColumn("Case"),
            "Pattern": st.column_config.TextColumn(
                "Pattern", help="The detected typology. '+n' means more patterns link "
                "the same accounts."),
            "accounts": st.column_config.NumberColumn("Accounts"),
            "total_amount": st.column_config.NumberColumn(
                "Amount", format="%.2f", help="Total value in the case's transactions (USD)."),
            "score": st.column_config.ProgressColumn(
                "Risk", min_value=0, max_value=100, format="%d",
                help="0-100. Weighted pattern hits plus transaction centrality; "
                "see each account's breakdown on the Investigate screen."),
            "Band": st.column_config.TextColumn("Band"),
            "Status": st.column_config.TextColumn("Status"),
        },
    )

    rows = event.selection.rows if event and event.selection else []
    if rows:
        st.session_state["rs_case_id"] = table.iloc[rows[0]]["case_id"]
        c.goto("investigate")
