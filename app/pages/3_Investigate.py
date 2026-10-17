"""RingSight — Investigate (Screen 4): case workspace.

Phase 0 shows a read-only case summary, the account risk table and the
"why flagged" explanations. The interactive pyvis graph, evidence table,
timeline and agentic SAR drafting arrive in Phase 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.components import data_access as da
from app.components.badges import risk_badge, status_badge
from app.components.styles import render_sidebar, set_page
from core.db import session_scope
from core.models import AlertRow, CaseAccount, CaseRow
from core.utils import fmt_amount

set_page("Investigate")
render_sidebar("Investigate")

dataset = da.current_dataset()
case_id = st.session_state.get("rs_case_id")

if not case_id:
    st.info("No case selected. Choose a case on the **Cases** page and click "
            "*Investigate →*.")
    st.stop()

run_id = f"RUN_{dataset}"
with session_scope() as session:
    case = session.query(CaseRow).filter(CaseRow.case_id == case_id,
                                         CaseRow.run_id == run_id).first()
    case_accounts = (session.query(CaseAccount)
                     .filter(CaseAccount.case_id == case_id).all())
    accounts_list = json.loads(case.accounts_json) if case else []
    alerts = (session.query(AlertRow)
              .filter(AlertRow.run_id == run_id).all()) if case else []
    account_rows = [
        {"account_id": ca.account_id, "risk_score": ca.risk_score,
         "explanation": json.loads(ca.explanation_json)}
        for ca in case_accounts
    ]
    case_alerts = [a for a in alerts
                   if set(json.loads(a.accounts_json)) & set(accounts_list)]
    alert_rows = [{"alert_id": a.alert_id, "pattern": a.pattern, "reason": a.reason}
                  for a in case_alerts]

if case is None:
    st.warning(f"Case {case_id} not found for dataset `{dataset}`.")
    st.stop()

st.markdown(
    f"<h2 class='rs-title'>{case.case_id} · {case.title}</h2>", unsafe_allow_html=True)
st.markdown(
    f"Score {risk_badge(case.score)} &nbsp; Status {status_badge(case.status)} &nbsp; "
    f"Total {fmt_amount(case.total_amount)} &nbsp; · &nbsp; {case.n_txns} txns",
    unsafe_allow_html=True,
)
st.caption("Interactive graph, evidence table and agentic SAR drafting arrive in Phase 1.")

left, right = st.columns([1.3, 1])

with left:
    st.subheader("Account risk")
    if account_rows:
        df = pd.DataFrame([
            {"Account": r["account_id"], "Risk": r["risk_score"],
             "Why": " · ".join(r["explanation"])}
            for r in sorted(account_rows, key=lambda r: -r["risk_score"])
        ])
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"Risk": st.column_config.ProgressColumn(
                         "Risk", min_value=0, max_value=100, format="%d")})

with right:
    st.subheader("Why flagged")
    for a in alert_rows:
        st.markdown(f"**{a['pattern']}** ({a['alert_id']})")
        st.caption(a["reason"])
