"""Audit & Metrics screen (secondary): detection quality and the audit log."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import data_access as da
from app.components.theme import icon, tokens
from app.components.ui import friendly_errors
from core import metrics
from core.config import load_rules
from core.db import session_scope, verify_audit_chain
from core.models import AuditLog, Transaction


def render() -> None:
    dataset = da.current_dataset()
    version = da.refresh_token(dataset)
    t = tokens()

    st.subheader("Detection quality")
    st.caption("How the rule-based detectors scored against the labels that come with the "
               "data (precision, recall and F1).")

    with friendly_errors("checking for ground-truth labels", stop=True):
        with session_scope() as session:
            base = session.query(Transaction).filter(Transaction.dataset_id == dataset)
            has_gt = base.filter(Transaction.gt_ring_id.isnot(None)).count() > 0
            has_txn_labels = base.filter(Transaction.is_laundering.isnot(None)).count() > 0

    if not has_gt and has_txn_labels:
        # Real labelled data (e.g. the IBM AML sample): per-transaction labels only.
        st.caption("This dataset labels individual transactions as laundering or not, "
                   "so quality is measured per transaction. Per-pattern scores need "
                   "the synthetic sample.")
        with friendly_errors("computing metrics"):
            alerts = da.load_alerts(dataset, version)
            txn = metrics.txn_level_metrics(dataset, alerts)
        m1, m2, m3 = st.columns(3)
        m1.metric("Precision", f"{txn.precision:.3f}",
                  help="Of the transactions the rules flagged, the share that are labelled "
                       "laundering.")
        m2.metric("Recall", f"{txn.recall:.3f}",
                  help="Of the transactions labelled laundering, the share the rules flagged.")
        m3.metric("F1", f"{txn.f1:.3f}",
                  help="Harmonic mean of precision and recall.")
        st.caption(f"{txn.tp:,} true positives · {txn.fp:,} false positives · "
                   f"{txn.fn:,} missed. The rules are deterministic and explainable, "
                   "not trained on this data.")
    elif not has_gt:
        st.info("Quality metrics need labelled data: use the synthetic or IBM AML sample "
                "(uploaded CSVs carry no labels).")
    else:
        with friendly_errors("computing metrics"):
            alerts = da.load_alerts(dataset, version)
            rules = load_rules()
            ring = metrics.ring_level_metrics(dataset, alerts, rules)
            overall = metrics.overall_ring_recall(dataset, alerts, rules)
            txn = metrics.txn_level_metrics(dataset, alerts)
        col1, col2 = st.columns([3, 2], gap="large")
        with col1:
            df = pd.DataFrame([{"Pattern": m.pattern, "Precision": m.precision,
                                "Recall": m.recall, "F1": m.f1, "TP": m.tp,
                                "FP": m.fp, "FN": m.fn} for m in ring])
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Overall ring recall {overall:.0%} · transaction-level "
                       f"P {txn.precision} / R {txn.recall} / F1 {txn.f1}.")
        with col2:
            if ring:
                long = df.melt(id_vars="Pattern", value_vars=["Precision", "Recall", "F1"],
                               var_name="metric", value_name="score")
                fig = px.bar(long, x="Pattern", y="score", color="metric", barmode="group",
                             color_discrete_sequence=[t["accent"], t["risk_low"],
                                                      t["risk_medium"]])
                fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8),
                                  yaxis_range=[0, 1.05], xaxis_title="", yaxis_title="",
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font_color=t["text"], legend_title_text="")
                st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Audit log")
    with friendly_errors("loading the audit log"):
        with session_scope() as session:
            rows = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
            audit = [{"id": r.id, "time": r.ts, "actor": r.actor, "action": r.action,
                      "case": r.case_id, "before": r.before_json, "after": r.after_json,
                      "hash": r.row_hash} for r in rows]
        ok, n_rows = verify_audit_chain()

    if ok:
        st.success(f"{icon('verified')} Tamper-evident hash chain verified over "
                   f"{n_rows} row(s).")
    else:
        st.error(f"Hash chain broken over {n_rows} row(s) — history may be altered.")

    if not audit:
        st.caption("No actions recorded yet. Drafting, dismissing and approving all write "
                   "a chained, timestamped entry here.")
        return

    table = pd.DataFrame([{"id": r["id"], "time": r["time"], "actor": r["actor"],
                           "action": r["action"], "case": r["case"]} for r in audit])
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button(f"{icon('download')} Export audit log (CSV)",
                       data=table.to_csv(index=False).encode("utf-8"),
                       file_name="ringsight_audit_log.csv", mime="text/csv")

    st.caption("Expand an entry to see the recorded before/after state.")
    for r in audit[:25]:
        with st.expander(f"#{r['id']} · {r['action']} · {r['case'] or '—'} · {r['actor']}"):
            b, a = st.columns(2)
            with b:
                st.caption("Before")
                st.json(json.loads(r["before"] or "{}") or {"(none)": ""})
            with a:
                st.caption("After")
                st.json(json.loads(r["after"] or "{}") or {"(none)": ""})
