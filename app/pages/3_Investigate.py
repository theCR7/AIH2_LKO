"""RingSight — Investigate (Screen 4): the demo hero.

Interactive graph + why-flagged + account risk, then Evidence / Timeline /
SAR Draft / Agent Trace tabs. The SAR Draft tab runs the agent pipeline, shows
the Grounding Score with per-sentence evidence chips, supports edit + re-validate,
approve/reject (audited) and PDF download.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from app.components import data_access as da
from app.components.badges import risk_badge, status_badge
from app.components.graph import render_case_graph_html
from app.components.styles import TOKENS, render_sidebar, set_page
from core.agents.llm import get_llm_status
from core.agents.orchestrator import run_sar_pipeline
from core.agents.validator import validate_narrative
from core.audit import record_audit
from core.casegraph import load_case_subgraph
from core.config import load_rules, load_settings
from core.db import session_scope
from core.models import CaseAccount, CaseRow, SarDraft
from core.schemas import NarrativeSentence, SARNarrative
from core.utils import fmt_amount

set_page("Investigate")
render_sidebar("Investigate")

dataset = da.current_dataset()
case_id = st.session_state.get("rs_case_id")
SECTIONS = ["summary", "subjects", "activity", "red_flags", "conclusion"]

if not case_id:
    st.info("No case selected. Choose a case on the **Cases** page and click *Investigate →*.")
    st.stop()

with session_scope() as session:
    case = session.get(CaseRow, case_id)
    if case is None:
        st.warning(f"Case {case_id} not found for dataset `{dataset}`.")
        st.stop()
    case_title, case_score, case_status = case.title, case.score, case.status
    case_total, case_ntxns = case.total_amount, case.n_txns
    case_patterns = json.loads(case.patterns_json)
    account_rows = [
        {"account_id": ca.account_id, "risk_score": ca.risk_score,
         "explanation": json.loads(ca.explanation_json)}
        for ca in session.query(CaseAccount).filter(CaseAccount.case_id == case_id).all()
    ]

# --- Header ------------------------------------------------------------------
head_l, head_r = st.columns([3, 1])
with head_l:
    st.markdown(f"<h2 class='rs-title'>{case_id} · {case_title}</h2>", unsafe_allow_html=True)
    st.markdown(
        f"Score {risk_badge(case_score)} &nbsp; Status {status_badge(case_status)} &nbsp; "
        f"Total {fmt_amount(case_total)} &nbsp;·&nbsp; {case_ntxns} txns &nbsp;·&nbsp; "
        f"{', '.join(case_patterns)}",
        unsafe_allow_html=True,
    )

# --- Top half: graph + why-flagged ------------------------------------------
g_col, why_col = st.columns([3, 2])
with g_col:
    st.caption("Interactive network — node size = risk, colour = band, red = suspicious flow")
    try:
        components.html(render_case_graph_html(case_id), height=560, scrolling=False)
    except Exception as exc:  # pragma: no cover - never crash the UI
        st.error(f"Could not render graph: {exc}")

with why_col:
    st.subheader("Why flagged")
    for r in sorted(account_rows, key=lambda r: -r["risk_score"])[:6]:
        st.markdown(f"**{r['account_id']}** {risk_badge(r['risk_score'])}",
                    unsafe_allow_html=True)
        st.caption(" · ".join(r["explanation"]))

# --- Tabs --------------------------------------------------------------------
tab_ev, tab_tl, tab_sar, tab_trace = st.tabs(
    ["Evidence", "Timeline", "SAR Draft", "Agent Trace"])

with tab_ev:
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

with tab_tl:
    sub = load_case_subgraph(case_id)
    if sub.edges:
        tdf = pd.DataFrame(sub.edges)
        tdf["flow"] = tdf["source"] + " → " + tdf["target"]
        fig = px.scatter(tdf, x="date", y="amount", color="suspicious", hover_name="flow",
                         color_discrete_map={True: TOKENS["risk_high"],
                                             False: "#94A3B8"},
                         labels={"amount": "Amount (USD)", "date": "Date"})
        fig.update_traces(marker=dict(size=12))
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No transactions to plot for this case.")

# --- SAR Draft tab -----------------------------------------------------------
sar_key = f"rs_sar_{case_id}"
inject = st.sidebar.checkbox("🧪 Inject hallucination (demo)", value=False,
                             help="Appends a false sentence citing a real evidence id "
                                  "so you can watch the validator catch it.")


def _do_draft() -> None:
    """Run the SAR pipeline (with optional injected hallucination) and store it."""
    with st.status("Drafting SAR…", expanded=True) as status:
        status.write("Building evidence pack…")
        result = run_sar_pipeline(case_id)
        status.write(f"Typology: {result.typology.typology}")
        status.write(f"Narrative drafted ({result.validation.grounding_score}% grounded)")
        if inject:
            status.write("Injecting a hallucinated sentence for the demo…")
            real_id = result.pack.items[0].id
            result.narrative.summary.append(NarrativeSentence(
                text="ACC_9999 transferred 1,000,000.00 USD as part of the scheme.",
                evidence_ids=[real_id]))
            result.validation = validate_narrative(result.narrative, result.pack)
        status.update(label=f"Draft ready ({result.validation.grounding_score}% grounded)",
                      state="complete")
    st.session_state[sar_key] = result


def _review(cid: str, result, case_status_label: str, draft_status: str, reason: str) -> None:
    """Persist an approve/reject: case + draft status + audited before/after."""
    with session_scope() as session:
        case_row = session.get(CaseRow, cid)
        before = {"case_status": case_row.status if case_row else None}
        if case_row:
            case_row.status = case_status_label
        draft = session.get(SarDraft, result.draft_id)
        if draft:
            draft.status = draft_status
        record_audit(session, actor=load_settings().analyst_name,
                     action=f"case_{draft_status}", case_id=cid,
                     before=before,
                     after={"case_status": case_status_label, "draft_id": result.draft_id,
                            "reason": reason, "grounding": result.validation.grounding_score})
    da.bump_version()


with tab_sar:
    rules = load_rules()
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("✍ Draft SAR", type="primary", use_container_width=True):
            _do_draft()

    result = st.session_state.get(sar_key)
    if result is None:
        st.caption("Click **Draft SAR** to run the Evidence → Typology → Narrative → "
                   "Validator pipeline.")
    else:
        issues_by_key = {(i.section, i.index): i.problem for i in result.validation.issues}
        gscore = result.validation.grounding_score
        badge_color = TOKENS["grounded"] if gscore >= 100 else TOKENS["risk_medium"]
        st.markdown(
            f"Grounding Score "
            f"<span class='rs-badge' style='background:{badge_color}'>{gscore:.0f}%</span>"
            f" &nbsp; Typology: **{result.typology.typology}** "
            f"(conf {result.typology.confidence:.2f}) &nbsp; "
            f"⏱ {result.elapsed_ms/1000:.1f}s (baseline "
            f"{rules.sar.baseline_manual_minutes_per_case} min)",
            unsafe_allow_html=True)
        if result.fallback_used:
            st.warning("LLM fallback/mock was used for this draft.")
        if gscore < 100:
            st.error(f"{len(result.validation.issues)} sentence(s) failed validation — "
                     "shown highlighted below. Status: needs_review.")

        edit_mode = st.toggle("✏ Edit draft", value=False, key=f"edit_{case_id}")

        if not edit_mode:
            for section in SECTIONS:
                sentences = getattr(result.narrative, section)
                if not sentences:
                    continue
                st.markdown(f"**{section.replace('_', ' ').title()}**")
                for idx, sent in enumerate(sentences):
                    chips = " ".join(
                        f"<span class='rs-badge' style='background:{TOKENS['accent']};"
                        f"font-size:0.7rem'>{e}</span>" for e in sent.evidence_ids)
                    problem = issues_by_key.get((section, idx))
                    if problem:
                        st.markdown(
                            f"<div style='background:{TOKENS['ungrounded_bg']};"
                            f"color:{TOKENS['ungrounded_fg']};padding:6px 10px;"
                            f"border-radius:8px;margin:3px 0'>✗ {sent.text} {chips}"
                            f"<br><small>{problem}</small></div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='padding:4px 0'>✓ {sent.text} {chips}</div>",
                                    unsafe_allow_html=True)
        else:
            st.caption("One sentence per line, format: `text || E1, E3`")
            edited: dict[str, str] = {}
            for section in SECTIONS:
                lines = [f"{s.text} || {', '.join(s.evidence_ids)}"
                         for s in getattr(result.narrative, section)]
                edited[section] = st.text_area(section.replace("_", " ").title(),
                                               "\n".join(lines), key=f"ta_{case_id}_{section}")
            if st.button("Re-validate", key=f"reval_{case_id}"):
                new = {}
                for section in SECTIONS:
                    sents = []
                    for line in edited[section].splitlines():
                        if not line.strip():
                            continue
                        text, _, ids = line.partition("||")
                        eids = [e.strip() for e in ids.split(",") if e.strip()]
                        sents.append(NarrativeSentence(text=text.strip(), evidence_ids=eids))
                    new[section] = sents
                result.narrative = SARNarrative(**new)
                result.validation = validate_narrative(result.narrative, result.pack)
                st.session_state[sar_key] = result
                st.rerun()

        # --- Review actions --------------------------------------------------
        st.divider()
        a1, a2, a3 = st.columns([1, 1, 2])
        with a1:
            if st.button("✓ Approve", use_container_width=True):
                _review(case_id, result, "Approved", "approved", "")
                st.success(f"{case_id} approved.")
        with a2:
            reject = st.button("✗ Reject", use_container_width=True)
        with a3:
            reason = st.text_input("Reject reason (required to reject)", key=f"rej_{case_id}")
        if reject:
            if not reason.strip():
                st.error("A reason is required to reject.")
            else:
                _review(case_id, result, "Rejected", "rejected", reason.strip())
                st.warning(f"{case_id} rejected.")

        # --- PDF download ----------------------------------------------------
        try:
            from core.reporting.pdf import build_sar_pdf
            pdf_bytes = build_sar_pdf(case_id, result, approved=(case_status == "Approved"))
            st.download_button("⬇ Download SAR PDF", data=pdf_bytes,
                               file_name=f"SAR_{case_id}.pdf", mime="application/pdf")
        except Exception as exc:  # pragma: no cover - never crash the UI
            st.caption(f"PDF export unavailable: {exc}")

with tab_trace:
    result = st.session_state.get(sar_key)
    if result is None:
        st.caption("Run **Draft SAR** to see the agent trace.")
    else:
        tr = pd.DataFrame([
            {"Step": t.step, "Model": t.model, "Latency (ms)": t.latency_ms,
             "Cache": "✓" if t.cache_hit else "", "Retries": t.retries, "Notes": t.notes}
            for t in result.trace
        ])
        st.dataframe(tr, use_container_width=True, hide_index=True)
        st.caption(f"LLM status: {get_llm_status().get('label')} · "
                   f"evidence coverage {result.signals.evidence_coverage:.0%} · "
                   f"retries {result.signals.retries_used}")
