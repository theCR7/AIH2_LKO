# Master Start Prompt (paste into Claude Code at repo root)

> Tip: start Claude Code in **plan mode** first (Shift+Tab) so it shows the plan before writing files. Approve, then let it build. Commit when done.

---

```
You are the lead engineer for "RingSight", an AML fraud-ring detection and evidence-grounded SAR drafting copilot, built in a one-day hackathon.

First, read these files completely: CLAUDE.md, docs/PRD.md, docs/ARCHITECTURE.md (especially §7a detection notes), docs/WIREFRAMES.md. Open docs/wireframes/ringsight_mockup.html for the intended look. Treat them as the source of truth. Follow every hard rule in CLAUDE.md.

GOAL OF THIS SESSION (Phase 0 – Foundation + Data + Detection, no LLM yet):
Build a runnable skeleton that can generate synthetic data, store it, run all detectors, score risk, build cases, and show them in Streamlit.

Deliver exactly this:
1. Project scaffold matching the folder structure in docs/ARCHITECTURE.md §3 (create empty modules with docstrings where a later phase will fill them).
2. core/config.py – loads .env and config/rules.yaml (a starter rules.yaml already exists — use it, add keys only if missing; load into a Pydantic settings model so typos fail fast).
3. core/db.py + core/models.py – SQLAlchemy 2.0 engine from DATABASE_URL, all tables in ARCHITECTURE §4 with portable types, init_db() and a `python -m core.db --reset` CLI.
4. core/schemas.py – all Pydantic models from ARCHITECTURE §5.
5. core/ingest/generator.py – seeded synthetic generator per PRD F1.1 using Faker: realistic background noise (salaries, merchant payments, P2P) plus planted patterns with ground-truth labels (is_laundering=1, gt_pattern, gt_ring_id). Tag payroll/merchant accounts via account_type and add 2–3 unlabelled near-miss decoys. Planted patterns must be detectable by the default rules. Save to DB and to data/samples/demo_seed42.csv.
6. core/ingest/csv_loader.py – load CSV with a column-mapping dict and validation errors returned as a list (no exceptions to UI).
7. core/detection/* – graph_builder (MultiDiGraph with txn attributes), cycles (follow ARCHITECTURE §7a: filter edges first, collapse to DiGraph, nx.simple_cycles with length_bound, cap candidates, then re-check time window and value retention on real txns), fan_patterns (fan-in smurfing, fan-out), shared_ids, passthrough, runner (runs all, persists detection_run + alerts, returns summary). Each alert has a human-readable reason.
8. core/scoring/risk.py + cases.py – explainable account risk (explanation list of "+N reason"), connected-component case grouping on the alert graph (not the full txn graph), case score = max member score, case title auto-generated.
9. core/metrics.py – precision/recall/F1 per pattern vs ground truth.
10. Streamlit: app/Home.py (KPI cards + "Generate demo data & run detection" one-click button + top cases table), pages/1_Data.py (generate + upload with column mapping + preview + run detection), pages/2_Cases.py (filterable ranked table, select → store rs_case_id in session_state). Apply design tokens from WIREFRAMES.md via a small CSS helper in app/components/styles.py. Sidebar per WIREFRAMES.
11. tests/test_generator.py and tests/test_detectors.py – assert every planted ring is detected with default rules (ring-level recall = 1.0 on seed 42), payroll/merchant accounts are not flagged, two runs give identical case IDs, and runtime < 10 s.
12. README.md "How to run" section.

CONSTRAINTS
- No LLM code in this phase except an empty core/agents/llm.py stub.
- Keep functions small and typed. No magic numbers outside rules.yaml.
- Must run on Windows and Linux.

PROCESS
- Show me a concise plan (files + key functions) before writing code.
- After building: run `pytest -q` and `ruff check . --fix`, fix failures, then tell me:
  (a) what was built, (b) exact commands to run, (c) any assumptions, (d) what to check in the UI.
```
