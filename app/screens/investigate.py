"""Investigate screen: case subgraph (left) + case file (right)."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from app.components import components as c
from app.components import data_access as da
from app.components.graph import cached_case_graph_html
from app.components.theme import active_mode, icon, tokens
from app.components.ui import friendly_errors
from core.audit import record_audit
from core.config import load_rules, load_settings
from core.db import session_scope
from core.models import AlertRow, CaseAccount, CaseRow, Identifier
from core.utils import fmt_amount

_RULE_TEXT = {
    "cycle": lambda r: (f"3-{r.cycles.max_length} hop loop within "
                        f"{r.cycles.max_window_hours}h, keeping ≥"
                        f"{r.cycles.min_value_retention:.0%} each hop."),
    "fan_in": lambda r: (f"≥{r.fan_in.min_senders} senders, each < "
                         f"{r.fan_in.max_amount_each:,.0f}, within {r.fan_in.window_hours}h."),
    "fan_out": lambda r: (f"≥{r.fan_out.min_receivers} receivers, total ≥ "
                          f"{r.fan_out.min_total:,.0f}, within {r.fan_out.window_hours}h."),
    "shared_identifier": lambda r: (f"≥{r.shared_identifiers.min_accounts} accounts share "
                                    "one device or IP."),
    "passthrough": lambda r: (f"≥{r.passthrough.min_outflow_ratio:.0%} of an inflow "
                              f"forwarded within {r.passthrough.window_hours}h."),
}

_DISMISS_REASONS = ["Known legitimate activity", "Duplicate of another case",
                    "Insufficient evidence", "Customer verified", "Other"]


def render() -> None:
    case_id = st.session_state.get("rs_case_id")
    dataset = da.current_dataset()
    version = da.refresh_token(dataset)
    if not case_id:
        c.empty_state("info", "No case selected",
                      "Pick a case on the Detect screen to investigate it.")
        return

    with friendly_errors("loading the case", stop=True):
        with session_scope() as session:
            case = session.get(CaseRow, case_id)
            if case is None:
                st.warning(f"Case {case_id} not found.")
                return
            title, score, status = case.title, case.score, case.status
            patterns = json.loads(case.patterns_json)
            accounts = json.loads(case.accounts_json)
            total, ntxns = case.total_amount, case.n_txns
            account_rows = sorted(
                [{"id": ca.account_id, "risk": ca.risk_score,
                  "why": json.loads(ca.explanation_json)}
                 for ca in session.query(CaseAccount)
                 .filter(CaseAccount.case_id == case_id).all()],
                key=lambda r: -r["risk"])
            alerts = [a for a in session.query(AlertRow)
                      .filter(AlertRow.run_id == case.run_id).all()
                      if set(json.loads(a.accounts_json)) & set(accounts)]
            idents = session.query(Identifier).filter(
                Identifier.account_id.in_(accounts)).all()

    # Header
    st.markdown(
        f"<div class='rs-sentence' style='font-size:20px;font-weight:600'>"
        f"{case_id} · {title}</div>", unsafe_allow_html=True)
    st.markdown(
        f"{c.risk_pill(score)} &nbsp; {c.status_pill(status)} &nbsp;"
        f"<span class='rs-mono' style='color:var(--rs-muted)'>"
        f"{fmt_amount(total)} · {ntxns} transactions</span>",
        unsafe_allow_html=True)
    st.caption("")

    left, right = st.columns([3, 2], gap="large")

    # --- Left: graph ---------------------------------------------------------
    with left:
        hops = 1 if st.toggle("Show 1-hop neighbours", value=False,
                              help="Add accounts that transacted directly with this "
                                   "case. Off = case accounts only.") else 0
        with friendly_errors("rendering the network"):
            html, capped = cached_case_graph_html(case_id, version, hops, active_mode())
            if capped:
                st.caption("Showing the first 150 accounts; the neighbourhood is larger.")
            components.html(html, height=540, scrolling=False)
        t = tokens()
        st.markdown(
            f"<div style='font-size:12px;color:var(--rs-muted)'>"
            f"<span style='color:{t['risk_high']}'>●</span> high &nbsp;"
            f"<span style='color:{t['risk_medium']}'>●</span> medium &nbsp;"
            f"<span style='color:{t['risk_low']}'>●</span> low &nbsp;·&nbsp; "
            f"red edge = suspicious flow &nbsp;·&nbsp; "
            f"● person &nbsp; ■ company &nbsp; ◆ payroll</div>",
            unsafe_allow_html=True)

    # --- Right: case file ----------------------------------------------------
    with right:
        rules = load_rules()
        dominant = patterns[0] if patterns else ""
        reason = next((a.reason for a in alerts if a.pattern == dominant),
                      alerts[0].reason if alerts else "Pattern detected.")
        rule_line = _RULE_TEXT.get(dominant, lambda r: "")(rules)
        c.why_flagged_box(reason, f"Rule: {rule_line}")

        # Shared attributes linking entities.
        groups: dict[tuple[str, str], list[str]] = {}
        for i in idents:
            groups.setdefault((i.id_type, i.value), []).append(i.account_id)
        shared = {k: v for k, v in groups.items()
                  if len(v) >= rules.shared_identifiers.min_accounts}
        if shared:
            st.caption("Shared attributes")
            chips = " ".join(c.entity_chip(k[0], k[1]) for k in shared)
            st.markdown(chips, unsafe_allow_html=True)

        st.caption("Account risk")
        import pandas as pd
        st.dataframe(
            pd.DataFrame([{"Account": r["id"], "Risk": r["risk"],
                           "Why flagged": " · ".join(r["why"])} for r in account_rows]),
            use_container_width=True, hide_index=True,
            column_config={"Risk": st.column_config.ProgressColumn(
                "Risk", min_value=0, max_value=100, format="%d",
                help="Account risk 0-100 — the 'Why flagged' column lists what "
                     "contributed.")})

    # --- Evidence table (full width) ----------------------------------------
    st.caption("")
    st.subheader("Supporting transactions")
    with friendly_errors("loading evidence"):
        tdf = da.case_timeline(case_id, version)
    if tdf.empty:
        st.caption("No transactions recorded for this case.")
    else:
        focus = st.selectbox("Focus account (filters the table)",
                             ["All accounts", *accounts], index=0)
        ev = tdf if focus == "All accounts" else tdf[
            (tdf["source"] == focus) | (tdf["target"] == focus)]
        ev = ev[["txn_id", "source", "target", "amount", "date", "suspicious"]]
        st.dataframe(
            ev, use_container_width=True, hide_index=True,
            column_config={
                "txn_id": "TX ID", "source": "From", "target": "To",
                "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
                "date": "Date",
                "suspicious": st.column_config.CheckboxColumn(
                    "Flagged", help="Part of the detected pattern.")})

    # --- Actions -------------------------------------------------------------
    st.divider()
    a1, a2 = st.columns([1, 1])
    with a1:
        if st.button(f"{icon('description')} Draft SAR", type="primary",
                     use_container_width=True):
            _draft(case_id)
    with a2:
        with st.popover(f"{icon('block')} Dismiss with reason",
                        use_container_width=True):
            reason_sel = st.selectbox("Reason", _DISMISS_REASONS, key=f"dis_{case_id}")
            note = st.text_input("Note (optional)", key=f"disnote_{case_id}")
            if st.button("Confirm dismissal", key=f"disc_{case_id}"):
                _dismiss(case_id, reason_sel, note)


def _draft(case_id: str) -> None:
    from core.agents.orchestrator import run_sar_pipeline
    with st.status("Drafting report", expanded=True) as status:
        with friendly_errors("drafting the report"):
            status.write("Building evidence pack")
            result = run_sar_pipeline(case_id)
            for step in result.trace:
                kind = "LLM" if step.model not in ("deterministic", "mock") else (
                    "LLM" if step.model == "mock" else "Rule-based")
                c.add_log(step.step, kind,
                          f"{step.notes} ({step.model}, {step.latency_ms} ms)")
            status.write(f"Typology: {result.typology.typology}")
            status.write(f"Validated {result.validation.grounding_score:.0f}% grounded")
            status.update(label="Draft ready", state="complete")
    st.session_state[f"rs_sar_{case_id}"] = result
    with session_scope() as session:
        row = session.get(CaseRow, case_id)
        if row and row.status in ("New", "In Review"):
            row.status = "Drafted"
    da.bump_version()
    c.goto("report")


def _dismiss(case_id: str, reason: str, note: str) -> None:
    with friendly_errors("dismissing the case"):
        with session_scope() as session:
            row = session.get(CaseRow, case_id)
            before = {"status": row.status if row else None}
            if row:
                row.status = "Rejected"
            record_audit(session, actor=load_settings().analyst_name,
                         action="case_dismissed", case_id=case_id, before=before,
                         after={"status": "Dismissed", "reason": reason, "note": note})
        c.add_log("Dismissed case", "Rule-based", f"{case_id}: {reason}")
        da.bump_version()
    c.goto("detect")
