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

## Architecture at a glance

`core/` is pure Python (never imports Streamlit); `app/` is the Streamlit UI and reads
data only through `core`. All thresholds live in `config/rules.yaml`; every LLM call
goes through the single gateway `core/agents/llm.py` (cache → fallback → deterministic
mock), and the Validator is the source of truth for grounding.

```mermaid
flowchart LR
    subgraph app["app/ (Streamlit UI)"]
        H[Home · KPIs] --> C[Cases]
        C --> I[Investigate: graph · evidence · timeline]
        I --> SAR[SAR Draft tab]
        I --> ASK[Ask-the-case Q&A]
        AU[Audit & Metrics]
    end
    subgraph core["core/ (no Streamlit)"]
        GEN[ingest.generator] --> DET[detection runner]
        DET --> SCORE[scoring: risk + cases]
        SCORE --> EV[agents.evidence · EvidencePack]
        EV --> TY[agents.typology]
        TY --> NA[agents.narrative]
        NA --> VAL[agents.validator]
        VAL -->|retry up to N| NA
        EV --> QA[agents.qa]
        EV --> ORCH[agents.orchestrator]
        ORCH --> PDF[reporting.pdf]
    end
    LLM[(agents.llm gateway\ncache → fallback → mock)]
    DB[(SQLite via DATABASE_URL\nportable to SQL Server)]
    TY --- LLM
    NA --- LLM
    QA --- LLM
    core --- DB
    SAR --> ORCH
    ASK --> QA
```

Pipeline: generate/upload → detect (deterministic, explainable) → rank cases →
Evidence Builder → Typology → Narrative ⇄ Validator (grounding score) → review,
approve, PDF. The orchestrator persists versioned drafts, a tamper-evident audit log
and a decision log.

## How to run

Phase 0 (foundation + data + detection) and Phase 1 (LLM agents + evidence-grounded
SAR drafting) are both implemented, plus Phase 9/10 hardening: one-click **Demo mode**,
graceful errors everywhere, cached graph building and an **Ask-the-case** grounded Q&A
tab. Generate synthetic data → detect fraud rings → rank cases → investigate on an
interactive graph → draft a SAR where every sentence is validated against evidence →
ask grounded questions → review, approve and export a PDF.

### 1. Set up a virtual environment and install dependencies
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```
Python 3.11 or 3.12 is recommended (3.14 also works).

Copy `.env.example` to `.env`. For an **offline, deterministic demo** set
`LLM_MODE=mock` (no API keys needed — the SAR agents produce grounded template
output). For **live** drafting set `LLM_MODE=live` and add `GEMINI_API_KEY` /
`GROQ_API_KEY`; the gateway falls back Gemini → Groq → mock and never crashes the app.

### 2. Run the app
```bash
streamlit run app/Home.py
```
**Fastest path — sidebar `🎬 Demo mode`:** one click resets the data (keeping the LLM
cache), generates the seed-42 dataset, runs detection and pre-warms the SAR drafts for
the top 2 cases, then shows a determinism fingerprint. Run it twice — identical case and
evidence IDs every time; in **live** mode the second run replays from cache (100% hits),
because the prompt-hash cache survives the reset. In **mock** mode there is no cache by
design, so the ratio shows 0%.

Or, on the **Home** page click **▶ Generate demo data & run detection**. Then browse:
- **Data** — generate (tunable size/planted counts) or upload a CSV with column mapping.
- **Cases** — filterable, ranked case list; select a case → *Investigate →*.
- **Investigate** — interactive pyvis graph (cached), *why flagged*, evidence & timeline,
  the **SAR Draft** tab (Evidence → Typology → Narrative → Validator; evidence chips per
  sentence, failed sentences highlighted by Grounding Score; edit + re-validate, audited
  Approve / Reject, **Download SAR PDF**; the sidebar *Inject hallucination* toggle shows
  the validator catching a false sentence), and the **Ask the case** tab — a grounded Q&A
  that answers only from the case's EvidencePack, cites `E-ids`, and refuses out-of-scope
  questions.
- **Audit & Metrics** — precision / recall / F1 per pattern vs planted ground truth, and
  the tamper-evident audit log with a verified hash-chain badge, expandable before/after
  state per entry and CSV export.

### Offline & Windows

Set `LLM_MODE=mock` for a fully offline, deterministic run — no API keys, no network,
the whole golden path (including the pyvis graph, with vis.js inlined) works with the
internet off. The SQLite file and its `data/` folder are created automatically on first
load regardless of the working directory, so a fresh clone runs on Windows out of the box.

### SAR drafting (CLI)
```bash
python -c "from core.agents.orchestrator import run_sar_pipeline; r=run_sar_pipeline('C-001'); print(r.draft_id, r.validation.grounding_score)"
```

### 3. Command-line equivalents
```bash
python -m core.db --reset           # drop + recreate all tables
python -m core.ingest.generator     # generate seed-42 data → DB + data/samples/demo_seed42.csv
python -m core.detection.runner     # run all detectors, score, build cases
python -m core.db --verify-audit    # verify the audit-log hash chain
```

### 4. Tests & lint
```bash
pytest -q          # detectors (recall 1.0, determinism, <10 s), validator grounding, LLM
                   # gateway, PDF, Demo-mode determinism + cache preservation, Ask-the-case Q&A
ruff check .       # clean
```

### Project layout
- **backend** — `core/` (config, db, models, schemas, ingest, detection, scoring, metrics,
  `agents/` LLM pipeline incl. `qa.py` Ask-the-case, `reporting/` PDF, `demo.py` Demo mode)
- **frontend** — `app/` (Home + pages + components; imports data only via `core`)
- **database** — `core/db.py` + `core/models.py`, SQLite file in `data/` (portable to SQL Server/Postgres via `DATABASE_URL`)
- **rules** — all thresholds/weights live in `config/rules.yaml` (single source of truth)
- **prompts** — SAR agent prompts in `config/prompts/` (typology, narrative)
