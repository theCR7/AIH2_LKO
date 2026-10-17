"""RingSight — Audit & Metrics (Screen 5): detection quality vs planted ground truth."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import data_access as da
from app.components.styles import TOKENS, render_sidebar, set_page
from app.components.ui import friendly_errors
from core import metrics
from core.config import load_rules
from core.db import session_scope, verify_audit_chain
from core.models import AuditLog, Transaction

set_page("Audit & Metrics")
render_sidebar("Audit & Metrics")
st.markdown("<h2 class='rs-title'>Audit & Metrics</h2>", unsafe_allow_html=True)

dataset = da.current_dataset()
version = da.refresh_token(dataset)

st.subheader("Detection quality vs ground truth")

with friendly_errors("checking for ground-truth labels", stop=True):
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

with friendly_errors("loading the audit log"):
    with session_scope() as session:
        rows = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
        audit = [
            {"id": r.id, "time": r.ts, "actor": r.actor, "action": r.action,
             "case": r.case_id, "before_json": r.before_json, "after_json": r.after_json,
             "row_hash": r.row_hash}
            for r in rows
        ]
    ok, n_rows = verify_audit_chain()

    chain_msg = (f"✅ Tamper-evident hash chain verified over {n_rows} row(s)." if ok
                 else f"⛔ Hash chain BROKEN over {n_rows} row(s) — history may be altered.")
    (st.success if ok else st.error)(chain_msg + "  (`python -m core.db --verify-audit`)")

    if not audit:
        st.caption("No audit entries yet. Approve/reject and draft actions are recorded "
                   "here with before/after state and a chained sha256 hash.")
    else:
        table = pd.DataFrame(
            [{"id": r["id"], "time": r["time"], "actor": r["actor"],
              "action": r["action"], "case": r["case"]} for r in audit])
        st.dataframe(table, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇ Export audit log (CSV)",
            data=table.to_csv(index=False).encode("utf-8"),
            file_name="ringsight_audit_log.csv", mime="text/csv")

        st.caption("Expand a row to inspect the before/after state it recorded.")
        for r in audit[:25]:
            label = f"#{r['id']} · {r['action']} · {r['case'] or '—'} · {r['actor']}"
            with st.expander(label):
                before = json.loads(r["before_json"] or "{}")
                after = json.loads(r["after_json"] or "{}")
                c_before, c_after = st.columns(2)
                with c_before:
                    st.caption("Before")
                    st.json(before if before else {"(none)": ""})
                with c_after:
                    st.caption("After")
                    st.json(after if after else {"(none)": ""})
                st.caption(f"row_hash `{r['row_hash'][:16]}…`")
