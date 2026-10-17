# Product Requirements Document (PRD) — RingSight MVP

## 1. Users & primary journey
**Persona:** Priya, AML Analyst. Gets 40 alerts/day, spends most of her time writing SAR narratives.

**Golden path (must work flawlessly in demo):**
1. Generate synthetic dataset (or upload CSV) → 2. Run detection → 3. See ranked cases → 4. Open a case: interactive graph + evidence table + "why flagged" → 5. Click **Draft SAR** → agents draft, validator checks → 6. Analyst edits/approves → 7. Download PDF; audit log updated.

## 2. Functional requirements

### F1 — Data ingestion
| ID | Requirement | Priority |
|---|---|---|
| F1.1 | Synthetic generator: ~500 accounts, ~5,000 transactions, 30 days, seeded; plants labelled patterns: 3 cycles, 2 fan-in smurfing, 1 fan-out/layering, 1 shared-identifier cluster, 1 rapid pass-through. Background includes payroll (fan-out) and merchant (fan-in) accounts tagged by `account_type`, plus 2–3 unlabelled near-miss decoys so precision is realistic | Must |
| F1.2 | CSV upload with column-mapping step (sender, receiver, amount, timestamp, currency, channel, ip/device optional) | Must |
| F1.3 | Validation: missing columns, bad dates, negative amounts → friendly errors | Must |
| F1.4 | IBM AML HI-Small subset loader (first N rows) | Could |

### F2 — Detection engine (deterministic, explainable)
| ID | Pattern | Default rule (configurable in `config/rules.yaml`) | Priority |
|---|---|---|---|
| F2.1 | Circular flow | Directed cycle length 3–6, all hops within 7 days, amount retained ≥ 80% per hop | Must |
| F2.2 | Smurfing / structuring (fan-in) | ≥ 5 distinct senders → 1 receiver, each < 10,000, within 48 h | Must |
| F2.3 | Fan-out / layering | 1 sender → ≥ 5 receivers within 48 h, total ≥ 50,000 | Must |
| F2.4 | Shared identifiers | ≥ 3 accounts sharing IP or device ID | Must |
| F2.5 | Rapid pass-through | Inflow then ≥ 90% outflow within 24 h | Should |
| F2.6 | Each detection emits an **Alert** with pattern, accounts, txn IDs, and a human-readable reason | Must |

### F3 — Risk scoring & cases
| ID | Requirement | Priority |
|---|---|---|
| F3.1 | Account risk 0–100 = weighted pattern hits + normalised PageRank/betweenness; weights in config | Must |
| F3.2 | Every score has an **explanation list** (e.g. "+30 member of 4-hop cycle C-002") | Must |
| F3.3 | Alerts merged into **Cases** by connected component; case score = max member score; ranked list | Must |
| F3.4 | Case statuses: New → In Review → Approved / Rejected | Must |

### F4 — Investigation workspace
| ID | Requirement | Priority |
|---|---|---|
| F4.1 | Interactive pyvis graph: node size = risk, colour = band, edges labelled with amount/date, suspicious edges red | Must |
| F4.2 | Evidence table with IDs `E1..En` (txn rows, shared identifiers, metrics) | Must |
| F4.3 | Money-flow timeline (Plotly) for the case | Should |
| F4.4 | "Why flagged" panel listing triggered rules | Must |

### F5 — Agentic SAR drafting (core differentiator)
| ID | Requirement | Priority |
|---|---|---|
| F5.1 | **Evidence Builder** (deterministic): creates compact evidence pack JSON with IDs | Must |
| F5.2 | **Typology Agent** (LLM): classifies typology (e.g. layering via circular transfers) with confidence + cited evidence | Must |
| F5.3 | **Narrative Agent** (LLM): drafts SAR in 5 sections (Summary, Subjects, Activity, Red Flags, Conclusion); output is structured JSON where **every sentence carries `evidence_ids`** | Must |
| F5.4 | **Validator Agent**: deterministic checks (IDs exist, amounts/dates/accounts in sentence match evidence, totals match metric items, speculation lexicon) + optional LLM judge; failures returned to Narrative Agent, max 2 retries | Must |
| F5.5 | **Grounding Score** = % sentences passing validation; shown as a badge; unsupported sentences highlighted | Must |
| F5.6 | Agent trace panel shows each step, latency, model used, retries | Should |
| F5.7 | Offline **mock mode** (template-based) when no API key / rate limited | Must |
| F5.8 | All LLM responses cached by prompt hash | Must |
| F5.9 | If grounding < 100% after max retries, draft status = `needs_review` and failing sentences stay highlighted; never silently drop them | Must |
| F5.10 | Log `ConfidenceSignals` + outcome to `decision_log` for every draft (M.Tech research hook; no UI needed beyond Agent Trace) | Should |

### F6 — Review, audit & export
| ID | Requirement | Priority |
|---|---|---|
| F6.1 | Editable narrative; Approve / Reject with mandatory reason | Must |
| F6.2 | Audit log: who, what, when, before/after | Must |
| F6.3 | PDF export (ReportLab): header, case summary, graph snapshot (PNG), narrative with evidence footnotes, appendix evidence table, "DRAFT – Human review required" watermark until approved | Must |
| F6.4 | Time-saved counter (baseline mins configurable vs actual) | Should |

### F7 — Dashboard & metrics
| ID | Requirement | Priority |
|---|---|---|
| F7.1 | KPIs: transactions analysed, cases, high-risk accounts, total suspicious amount, avg grounding score, est. hours saved | Must |
| F7.2 | Detection quality vs planted ground truth: precision, recall, F1 per pattern | Must |
| F7.3 | Ask-the-case chat (Q&A over evidence pack only) | Could |

## 3. Non-functional requirements
| Area | Requirement |
|---|---|
| Performance | Detection on 5k txns < 10 s; SAR draft < 60 s (cached replay < 2 s) |
| Explainability | No black-box scores; every flag has a reason |
| Reliability | App never crashes on LLM failure → falls back to Groq → mock mode |
| Security | Keys only in `.env` (git-ignored); synthetic data only |
| Portability | SQLite default, SQL Server via env; runs on Windows/macOS/Linux |
| Quality | pytest unit tests for detectors and validator; ruff clean |

## 4. Acceptance criteria (demo gate)
- [ ] Fresh clone → `pip install` → `streamlit run app/Home.py` works in < 5 min.
- [ ] Generator + detection finds all planted rings (recall ≥ 90%).
- [ ] At least one case drafts a SAR with Grounding Score 100% after validation.
- [ ] Deliberately injected false sentence is caught and highlighted red.
- [ ] PDF downloads and opens; audit log shows approve action.
- [ ] Works with internet off (mock mode + cache), **including the pyvis graph** (vis.js inlined).
- [ ] Same seed 42 run twice produces identical case IDs, evidence IDs and cached SAR (determinism).
- [ ] Detection on 5k txns < 10 s on the slowest team laptop.
- [ ] Audit log hash chain verifies (`python -m core.db --verify-audit`).

## 5. Out of scope
Authentication, multi-tenant, real e-filing, streaming, model training.
