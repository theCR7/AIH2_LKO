# Iteration Prompts (run in order after the Master Prompt)

**Rules of the road**
- One prompt = one commit (`git commit -m "P3: narrative agent"`).
- Run `/clear` between phases to keep context clean; CLAUDE.md is reloaded automatically.
- If output drifts, say: *"Re-read CLAUDE.md hard rules and fix violations."*
- Owner column matches `docs/TEAM_PLAN.md`.

| # | Phase | Owner | Est. |
|---|---|---|---|
| P1 | LLM gateway | B | 30 min |
| P2 | Evidence builder + Typology agent | B | 40 min |
| P3 | Narrative agent | B | 40 min |
| P4 | Validator + orchestrator loop | B | 50 min |
| P5 | Investigate page (graph, evidence, why-flagged) | C | 60 min |
| P6 | SAR draft tab + review + audit | C | 50 min |
| P7 | PDF export | A | 40 min |
| P8 | Metrics & audit page, time-saved | A | 30 min |
| P9 | Hardening & demo mode | All | 40 min |
| P10 | Stretch (pick one) | Any | 30–60 min |

---

### P1 — LLM gateway
```
Implement core/agents/llm.py per docs/ARCHITECTURE.md §7.
- Function: call_llm(system: str, user: str, schema: type[BaseModel] | None, purpose: str) -> LLMResult (fields: parsed, raw_text, model_used, latency_ms, cache_hit, fallback_used).
- Chain PRIMARY_MODEL -> FALLBACK_MODEL -> mock (from .env), via litellm.completion.
- Ask for JSON output; parse with Pydantic; on parse failure, one repair call with the error message.
- tenacity exponential backoff with jitter for 429/5xx, max 3 attempts per model.
- SQLite/SQLAlchemy cache table llm_cache keyed by sha256(model+system+user).
- LLM_MODE=mock returns deterministic output from a registered mock function per `purpose`.
- Expose get_llm_status() for the sidebar pill.
Add tests with mocked litellm (no network). Run pytest + ruff.
```

### P2 — Evidence builder + Typology agent
```
Implement core/agents/evidence.py: build_evidence_pack(case_id) -> EvidencePack.
- Include subjects, patterns, totals, and up to 40 EvidenceItems ranked by relevance (pattern txns first, then shared identifiers, then risk metrics). Stable IDs E1..En; persist to `evidence` table.
- Each item.summary is a short factual one-liner with exact IDs, amounts, dates.
Then implement core/agents/typology.py using config/prompts/typology.md (create it): classify into a typology list (layering via circular transfers, structuring/smurfing, mule fan-out, account takeover/shared device, rapid pass-through, mixed). Output TypologyResult, must cite evidence_ids. Provide a mock function. Unit-test evidence pack size and ID stability.
```

### P3 — Narrative agent
```
Implement core/agents/narrative.py with prompt config/prompts/narrative.md.
- Input: EvidencePack + TypologyResult (+ optional validator feedback list).
- Output: SARNarrative (5 sections). Rules in the prompt: use ONLY facts from evidence items; every factual sentence must list evidence_ids; use exact amounts/dates/IDs as written; neutral regulatory tone; cover who/what/when/where/why/how; no speculation about identity or intent beyond the evidence; max ~20 sentences total.
- If feedback is given, rewrite only the failing sentences and keep the rest.
- Mock function builds a template narrative directly from the evidence pack (must also pass validation).
```

### P4 — Validator + orchestrator
```
Implement core/agents/validator.py exactly per ARCHITECTURE §6 (deterministic checks with regex for amounts, account IDs, dates; ±1% amount tolerance). Optional LLM judge behind rules.yaml flag `use_llm_judge` (default false).
Implement core/agents/orchestrator.py: run_sar_pipeline(case_id) -> (SARNarrative, ValidationResult, trace: list[TraceStep]).
Steps: evidence -> typology -> narrative -> validate -> (retry narrative with issues, max LLM_MAX_RETRIES) -> persist sar_drafts (versioned) -> audit_log entry "draft_created".
Tests: (1) mock pipeline yields grounding_score 100; (2) injected sentence citing a REAL evidence id but a wrong amount ("ACC_9999 sent 1,000,000.00 USD [E3]") is flagged for unknown account AND amount mismatch; (3) "ACC_0018 is a known shell company [E1]" is flagged by the speculation lexicon; (4) a sentence with no evidence_ids is flagged.
Also: write ConfidenceSignals + outcome to decision_log; if not 100% after retries set status needs_review.
```

### P5 — Investigate page
```
Build app/pages/3_Investigate.py per WIREFRAMES Screen 4 (top half + Evidence/Timeline tabs).
- app/components/graph.py: render case subgraph with pyvis (node size by risk, color by band, suspicious edges red with amount label, hover tooltip with account details) using Network(cdn_resources="in_line") and net.generate_html() (no temp files, works offline), embed via st.components.v1.html, height 550. Turn physics off after stabilization so the graph doesn't keep drifting during the demo. Also a matplotlib static PNG export function for the PDF.
- Why-flagged panel from risk explanations; account risk table.
- Evidence tab: table of E-items; Timeline tab: Plotly scatter/step of money flow over time.
- If no case selected, show a selectbox of cases.
```

### P6 — SAR draft tab, review, audit
```
Add tabs "SAR Draft", "Agent Trace" to Investigate page.
- "Draft SAR" button runs orchestrator with st.status showing each step live; display elapsed seconds and baseline from rules.yaml.
- Show Grounding Score badge and typology; each sentence rendered with evidence chips [E3]; failed sentences red background with issue tooltip.
- Edit mode (text areas per section) -> "Re-validate" runs validator only (keep evidence_ids per sentence; allow editing ids).
- Approve / Reject (reject requires reason) -> update case status, sar_drafts status, audit_log with before/after.
- Agent Trace tab: table of TraceStep (step, model, latency, cache hit, retries, notes).
- Add a hidden demo toggle in sidebar "Inject hallucination" that appends a false sentence before validation, to show the validator catching it. The injected sentence must cite a real evidence id (e.g. [E3]) so the demo proves the validator checks content, not just citation presence.
```

### P7 — PDF export
```
Implement core/reporting/pdf.py with ReportLab per WIREFRAMES "SAR PDF layout": header, DRAFT watermark unless approved, summary box, graph PNG, 5 narrative sections with evidence footnote markers, Appendix A evidence table, Appendix B validation + approver + timestamp. Return bytes; add st.download_button on SAR Draft tab. Add a test that the PDF is generated and > 5 KB.
```

### P8 — Metrics & audit page + dashboard polish
```
Build app/pages/4_Audit_and_Metrics.py: precision/recall/F1 per pattern table + Plotly bar; audit log table with expandable before/after JSON and CSV export.
Home KPIs: add Avg grounding score and Est. hours saved = cases_drafted × (baseline_minutes − actual_minutes)/60.
```

### P9 — Hardening & demo mode
```
Do a full review against docs/PRD.md acceptance criteria (§4) and fix gaps.
- Add sidebar "Demo mode" button: reset DB, generate seed 42, run detection, pre-warm the LLM cache for the top 2 cases. Verify a second Demo-mode run gives identical case/evidence IDs and 100% cache hits.
- Run on Windows too (paths, sqlite file location); ensure data/ exists at startup.
- Graceful errors everywhere (st.error with friendly text, no stack traces in UI).
- Test with LLM_MODE=mock and internet off.
- Performance: cache graph building with st.cache_data/resource.
- Update README with screenshots placeholders, architecture mermaid, and run steps.
Report remaining risks.
```

### P10 — Stretch (choose ONE)
```
(a) "Ask the case" chat tab: answers questions using only the EvidencePack, citing E-ids, refuses out-of-scope questions.
(b) IBM AML HI-Small loader (first 50k rows, column mapping preset) and show metrics vs its labels.
(c) Thin FastAPI layer exposing /detect and /cases/{id}/sar using core/ (proves API-readiness for scalability slide).
(d) SQL Server run: verify all tables create & app works with mssql+pyodbc DATABASE_URL; document steps.
```

---

## Quick fix prompts (keep handy)
- *"The app crashed with this traceback: <paste>. Find root cause, fix, add a regression test."*
- *"Detector X misses planted pattern Y on seed 42. Debug with a minimal script, adjust logic (not thresholds) unless rules are wrong, keep recall test green."*
- *"LLM returned invalid JSON. Harden the prompt and repair step; show me the final prompt."*
- *"Make the Investigate page look more polished per WIREFRAMES tokens without changing behaviour."*
