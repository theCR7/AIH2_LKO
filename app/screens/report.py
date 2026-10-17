"""Report screen: the SAR draft, citation checking, sign-off and export."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.components import components as c
from app.components import data_access as da
from app.components.theme import icon, tokens
from app.components.ui import friendly_errors
from core.audit import record_audit
from core.config import load_settings
from core.db import session_scope
from core.models import CaseRow, SarDraft
from core.schemas import NarrativeSentence, SARNarrative
from core.utils import fmt_amount

SECTIONS = [("summary", "Summary of activity"), ("subjects", "Subject information"),
            ("activity", "What happened"), ("red_flags", "Red flags"),
            ("conclusion", "Conclusion")]


def render() -> None:
    case_id = st.session_state.get("rs_case_id")
    if not case_id:
        c.empty_state("info", "No case selected", "Pick a case on the Detect screen.")
        return
    result = st.session_state.get(f"rs_sar_{case_id}")
    if result is None:
        c.empty_state("description", "No draft yet",
                      "Open the case on Investigate and choose Draft SAR.")
        if st.button("Go to Investigate"):
            c.goto("investigate")
        return

    by_id = {it.id: it for it in result.pack.items}
    issues_by_key = {(i.section, i.index): i.problem for i in result.validation.issues}
    t = tokens()

    # Header + status line (deterministic parts vs generative are labelled).
    with session_scope() as session:
        row = session.get(CaseRow, case_id)
        case_status = row.status if row else "Drafted"
    approved = case_status == "Approved"
    st.markdown(
        f"<div class='rs-sentence' style='font-size:20px;font-weight:600'>"
        f"Suspicious Activity Report · {case_id}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='rs-pill rs-pill-muted'>"
        f"{'Approved' if approved else 'Draft, review required'}</span> &nbsp;"
        f"<span style='color:var(--rs-muted)'>Typology: "
        f"<strong style='color:var(--rs-text)'>{result.typology.typology}</strong>"
        f" · drafted in <span class='rs-mono'>{result.elapsed_ms / 1000:.1f}s</span></span>",
        unsafe_allow_html=True)
    st.caption("")

    # Coverage line.
    total = sum(len(getattr(result.narrative, s)) for s, _ in SECTIONS)
    need_review = len(result.validation.issues)
    cited_ok = total - need_review
    if need_review:
        st.warning(f"{cited_ok} of {total} statements cited and consistent. "
                   f"{need_review} need review (highlighted below).")
    else:
        st.success(f"All {total} statements cite evidence consistent with the records.")

    left, right = st.columns([3, 2], gap="large")

    with left:
        edit = st.toggle("Edit draft", value=False, key=f"edit_{case_id}")
        if edit:
            _edit_mode(case_id, result)
        else:
            _render_narrative(result, by_id, issues_by_key, t)

    with right:
        _sources_and_checklist(result, by_id)

    st.divider()
    _signoff_and_export(case_id, result, case_status, total, need_review)


def _render_narrative(result, by_id, issues_by_key, t) -> None:
    for key, label in SECTIONS:
        sentences = getattr(result.narrative, key)
        if not sentences:
            continue
        st.markdown(f"**{label}**")
        for idx, sent in enumerate(sentences):
            problem = issues_by_key.get((key, idx))
            chips = "".join(
                f"<span class='rs-chip{' rs-chip-bad' if problem else ''}' "
                f"title=\"{by_id[e].summary if e in by_id else 'unknown source'}\">"
                f"{e}</span>" for e in sent.evidence_ids) or (
                "<span class='rs-chip rs-chip-bad'>no source</span>")
            if problem:
                st.markdown(
                    f"<div class='rs-unsupported'><span class='rs-sentence'>{sent.text}"
                    f"</span> {chips}<br><span style='font-size:12px;color:var(--rs-text)'>"
                    f"{icon('info')} {problem} — edit or remove before approving.</span></div>",
                    unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='rs-sentence'>{sent.text} {chips}</div>",
                            unsafe_allow_html=True)
        st.caption("")


def _edit_mode(case_id: str, result) -> None:
    from core.agents.validator import validate_narrative
    st.caption("One sentence per line, format: `text || E1, E3`")
    edited: dict[str, str] = {}
    for key, label in SECTIONS:
        lines = [f"{s.text} || {', '.join(s.evidence_ids)}"
                 for s in getattr(result.narrative, key)]
        edited[key] = st.text_area(label, "\n".join(lines), key=f"ta_{case_id}_{key}")
    if st.button("Re-validate", key=f"reval_{case_id}"):
        new = {}
        for key, _ in SECTIONS:
            sents = []
            for line in edited[key].splitlines():
                if not line.strip():
                    continue
                text, _, ids = line.partition("||")
                eids = [e.strip() for e in ids.split(",") if e.strip()]
                sents.append(NarrativeSentence(text=text.strip(), evidence_ids=eids))
            new[key] = sents
        result.narrative = SARNarrative(**new)
        result.validation = validate_narrative(result.narrative, result.pack)
        result.extra["edited"] = True
        st.session_state[f"rs_sar_{case_id}"] = result
        st.rerun()


def _sources_and_checklist(result, by_id) -> None:
    st.caption("Completeness")
    pack = result.pack
    narr = result.narrative
    checks = [
        ("Subjects identified", bool(narr.subjects)),
        ("Amounts stated", pack.totals.get("total_amount", 0) > 0),
        ("Date range stated", pack.totals.get("date_range", "n/a") != "n/a"),
        ("Pattern described", bool(narr.activity)),
        ("Red flags listed", bool(narr.red_flags)),
    ]
    for label, ok in checks:
        mark = icon("task_alt") if ok else icon("radio_button_unchecked")
        st.markdown(f"{mark} {label}")

    st.caption("")
    st.caption("Sources")
    cited = sorted({e for key, _ in SECTIONS for s in getattr(narr, key)
                    for e in s.evidence_ids})
    for e in cited:
        if e in by_id:
            st.markdown(f"{c.citation_chip(e)} <span class='rs-sentence' "
                        f"style='font-size:13px'>{by_id[e].summary}</span>",
                        unsafe_allow_html=True)


def _signoff_and_export(case_id, result, case_status, total, need_review) -> None:
    settings = load_settings()
    approved = case_status == "Approved"

    st.subheader("Sign-off")
    name = st.text_input("Analyst name", value=settings.analyst_name, key=f"name_{case_id}")
    reviewed = st.checkbox("I have reviewed every cited source", key=f"rev_{case_id}")
    ack = True
    if need_review:
        ack = st.checkbox(f"I acknowledge {need_review} unsupported statement(s)",
                          key=f"ack_{case_id}")

    missing = []
    if not name.strip():
        missing.append("analyst name")
    if not reviewed:
        missing.append("the review confirmation")
    if need_review and not ack:
        missing.append("acknowledging unsupported statements")
    can_approve = not missing and not approved

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(f"{icon('task_alt')} Approve & export", type="primary",
                     disabled=not can_approve, use_container_width=True,
                     help=("Already approved." if approved else
                           ("Provide " + ", ".join(missing) + " to enable."
                            if missing else "Approve and record the sign-off."))):
            _approve(case_id, result, name)
            st.rerun()

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    fname = f"SAR_{case_id}_{stamp}"
    with friendly_errors("preparing the export"):
        from core.reporting.pdf import build_sar_pdf
        pdf = build_sar_pdf(case_id, result, approved=approved)
        with col2:
            st.download_button(f"{icon('download')} PDF", data=pdf,
                               file_name=f"{fname}.pdf", mime="application/pdf",
                               use_container_width=True)
        with col3:
            st.download_button(f"{icon('download')} Text", data=_as_text(result, case_id),
                               file_name=f"{fname}.txt", mime="text/plain",
                               use_container_width=True)

    # Audit footer.
    edited = "yes" if result.extra.get("edited") else "no"
    approver = result.extra.get("approved_by", "—")
    approved_at = result.extra.get("approved_at", "—")
    model = next((s.model for s in result.trace if s.step == "Narrative Agent"), "—")
    st.caption("")
    st.markdown(
        f"<div class='rs-mono' style='font-size:12px;color:var(--rs-muted)'>"
        f"Generated {datetime.now():%Y-%m-%d %H:%M} · model {model} · "
        f"{total} statements, {total - need_review} cited · edited {edited} · "
        f"approved by {approver} {('at ' + approved_at) if approved_at != '—' else ''}</div>",
        unsafe_allow_html=True)


def _approve(case_id, result, name: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with session_scope() as session:
        row = session.get(CaseRow, case_id)
        before = {"status": row.status if row else None}
        if row:
            row.status = "Approved"
        draft = session.get(SarDraft, result.draft_id)
        if draft:
            draft.status = "approved"
        record_audit(session, actor=name, action="case_approved", case_id=case_id,
                     before=before,
                     after={"status": "Approved", "draft_id": result.draft_id,
                            "grounding": result.validation.grounding_score})
    result.extra["approved_by"] = name
    result.extra["approved_at"] = now
    st.session_state[f"rs_sar_{case_id}"] = result
    c.add_log("Approved SAR", "Rule-based", f"{case_id} by {name}")
    da.bump_version()


def _as_text(result, case_id: str) -> str:
    lines = [f"SUSPICIOUS ACTIVITY REPORT — {case_id}",
             f"Typology: {result.typology.typology}",
             f"Total: {fmt_amount(result.pack.totals.get('total_amount', 0))} · "
             f"{result.pack.totals.get('date_range', 'n/a')}", ""]
    for key, label in SECTIONS:
        sents = getattr(result.narrative, key)
        if not sents:
            continue
        lines.append(label.upper())
        for s in sents:
            cites = " ".join(f"[{e}]" for e in s.evidence_ids)
            lines.append(f"  {s.text} {cites}")
        lines.append("")
    return "\n".join(lines)
