"""RingSight — Audit & Metrics (Screen 5): detection quality vs planted ground truth."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import data_access as da
from app.components.styles import TOKENS, render_sidebar, set_page
from core import metrics
from core.config import load_rules
from core.db import session_scope
from core.models import AuditLog, Transaction

set_page("Audit & Metrics")
render_sidebar("Audit & Metrics")
st.markdown("<h2 class='rs-title'>Audit & Metrics</h2>", unsafe_allow_html=True)

dataset = da.current_dataset()
version = da.refresh_token(dataset)

st.subheader("Detection quality vs ground truth")

with session_scope() as session:
    has_gt = (session.query(Transaction)
              .filter(Transaction.dataset_id == dataset,
                      Transaction.gt_ring_id.isnot(None)).count() > 0)

if not has_gt:
    st.info("Ground-truth metrics are only available for generated datasets "
            "(uploaded CSVs have no labels).")
else:
    alerts = da.load_alerts(dataset, version)
    rules = load_rules()
    ring = metrics.ring_level_metrics(dataset, alerts, rules)
    overall = metrics.overall_ring_recall(dataset, alerts, rules)
    txn = metrics.txn_level_metrics(dataset, alerts)

    c1, c2 = st.columns([2, 1])
    with c1:
        df = pd.DataFrame([{
            "Pattern": m.pattern, "Precision": m.precision, "Recall": m.recall,
            "F1": m.f1, "TP": m.tp, "FP": m.fp, "FN": m.fn,
        } for m in ring])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Overall ring-level recall: **{overall:.0%}** · "
                   f"Transaction-level: P={txn.precision} R={txn.recall} F1={txn.f1}")
    with c2:
        if ring:
            long = df.melt(id_vars="Pattern", value_vars=["Precision", "Recall", "F1"],
                           var_name="metric", value_name="score")
            fig = px.bar(long, x="Pattern", y="score", color="metric", barmode="group",
                         color_discrete_sequence=[TOKENS["primary"], TOKENS["accent"],
                                                  TOKENS["risk_low"]])
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                              yaxis_range=[0, 1.05], xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Audit log")
with session_scope() as session:
    rows = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(100).all()
    audit = [{"time": r.ts, "actor": r.actor, "action": r.action, "case": r.case_id}
             for r in rows]
if audit:
    st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)
else:
    st.caption("No audit entries yet. Approve/reject actions (Phase 1) are recorded here "
               "with a tamper-evident hash chain (`python -m core.db --verify-audit`).")
