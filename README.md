# RingSight — AI Fraud-Ring Investigation & Evidence-Grounded SAR Copilot

> Hackathon kickoff pack. Drop this whole folder into the root of your GitHub repo **before** you start Claude Code.

## What's in this pack

| File | Purpose | Who reads it |
|---|---|---|
| `00_PREREQUISITES_CHECKLIST.md` | Everything to install/create **the day before** | Whole team |
| `CLAUDE.md` | Permanent project memory for Claude Code (rules, stack, conventions) | Claude Code (auto-loaded) |
| `docs/BRD.md` | Business Requirements — the *why* (use for judges & M.Tech intro) | Team, judges |
| `docs/PRD.md` | Product Requirements — features, acceptance criteria | Team, Claude Code |
| `docs/ARCHITECTURE.md` | Stack, folder structure, DB schema, agent flow, JSON contracts | Claude Code |
| `docs/WIREFRAMES.md` | Screen-by-screen layouts + design tokens | Claude Code, UI owner |
| `docs/wireframes/ringsight_mockup.html` | Clickable HTML mockup of all 5 screens (wireframe/hi-fi toggle) | Everyone |
| `config/rules.yaml` | Starter thresholds & weights (single source of truth for detectors) | Claude Code |
| `docs/REVIEW_NOTES.md` | Pre-build review: issues found and what was changed | Team lead |
| `prompts/00_MASTER_PROMPT.md` | The first big prompt that scaffolds the project | Paste into Claude Code |
| `prompts/ITERATIONS.md` | 10 smaller follow-up prompts, in order | Paste one by one |
| `docs/TEAM_PLAN.md` | Hour-by-hour split for 3 members | Team |
| `docs/DEMO_SCRIPT.md` | 10-minute, 3-speaker demo script | Team |
| `.env.example`, `requirements.txt` | Config + dependencies | Everyone |

## One-line pitch
**"RingSight finds hidden money-laundering rings in transaction data in seconds, and drafts a regulator-ready Suspicious Activity Report where every single sentence is traceable to evidence — so analysts sign off in minutes instead of days."**

## Order of work
1. Complete `00_PREREQUISITES_CHECKLIST.md` (day before).
2. Read `docs/REVIEW_NOTES.md`, then commit this pack to `main`.
3. Open Claude Code in repo root → paste `prompts/00_MASTER_PROMPT.md`.
4. Run `prompts/ITERATIONS.md` P1 → P10, committing after each.
5. Rehearse `docs/DEMO_SCRIPT.md` twice.

---

## How to run (Phase 0 — Foundation + Data + Detection)

Phase 0 is a runnable skeleton: it generates synthetic data, stores it, runs
every detector, scores risk, builds cases and shows them in Streamlit. **No LLM
is used in this phase** (SAR drafting arrives in Phase 1).

### 1. Set up a virtual environment and install dependencies
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```
Python 3.11 or 3.12 is recommended (3.14 also works). `.env` is optional in
Phase 0 — defaults come from `.env.example` (SQLite at `data/ringsight.db`).

### 2. Run the app
```bash
streamlit run app/Home.py
```
On the **Home** page click **▶ Generate demo data & run detection** — one click
generates the seed-42 dataset, runs all detectors and builds cases. Then browse:
- **Data** — generate (tunable size/planted counts) or upload a CSV with column mapping.
- **Cases** — filterable, ranked case list; select a case → *Investigate →*.
- **Investigate** — case summary, account-risk table and *why flagged* (graph + SAR: Phase 1).
- **Audit & Metrics** — precision / recall / F1 per pattern vs planted ground truth.

### 3. Command-line equivalents
```bash
python -m core.db --reset           # drop + recreate all tables
python -m core.ingest.generator     # generate seed-42 data → DB + data/samples/demo_seed42.csv
python -m core.detection.runner     # run all detectors, score, build cases
python -m core.db --verify-audit    # verify the audit-log hash chain
```

### 4. Tests & lint
```bash
pytest -q          # 13 tests: recall = 1.0 on seed 42, exclusions, determinism, < 10 s
ruff check .       # clean
```

### Project layout
- **backend** — `core/` (config, db, models, schemas, ingest, detection, scoring, metrics)
- **frontend** — `app/` (Home + pages + components; never imports from DB directly except via `core`)
- **database** — `core/db.py` + `core/models.py`, SQLite file in `data/` (portable to SQL Server/Postgres via `DATABASE_URL`)
- **rules** — all thresholds/weights live in `config/rules.yaml` (single source of truth)
