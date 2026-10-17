# CLAUDE.md — Project memory for Claude Code

## Project
RingSight: AML fraud-ring detection + evidence-grounded SAR drafting copilot. One-day hackathon MVP, 3-person team. Read `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/WIREFRAMES.md` before any major change.

## Stack (do not change without asking)
Python 3.11, Streamlit multipage, NetworkX, pyvis, Plotly, pandas, Pydantic v2, SQLAlchemy 2.0 (SQLite default via `DATABASE_URL`), LiteLLM (Gemini → Groq → mock), ReportLab, PyYAML, python-dotenv, pytest, ruff.
Do NOT add: LangChain, LangGraph, FastAPI, React, Docker, vector DBs — unless explicitly asked.

## Hard rules
1. `core/` must never import `streamlit`. UI lives only in `app/`.
2. All thresholds/weights come from `config/rules.yaml`; no magic numbers in detectors.
3. All LLM calls go through `core/agents/llm.py` (cache, fallback, retries, mock). Never call providers directly.
4. LLM outputs must be parsed into Pydantic models from `core/schemas.py`.
5. Send the LLM only the compact `EvidencePack` (≤ 40 items). Never send raw CSVs/dataframes.
6. Every factual narrative sentence must carry `evidence_ids`; the validator is the source of truth.
7. App must not crash if LLM fails — fall back and show a warning.
8. DB code uses portable SQLAlchemy types only (must also run on SQL Server).
9. Secrets only from `.env`; never hard-code keys; `.env` is git-ignored.
10. Synthetic data only.
11. Detection must be deterministic for a given seed + rules.yaml: sort accounts/txns/alerts/evidence before assigning IDs so the LLM cache and demo IDs stay stable.
12. Never put volatile values (now(), run IDs, random UUIDs) into LLM prompts — they break the prompt-hash cache.
13. pyvis graphs: `cdn_resources="in_line"` and `net.generate_html()` (no files written, works offline).
14. Narrative text uses canonical formats only: amounts `48,200.00 USD`, dates `2026-09-03`, account IDs `ACC_0018`. The validator parses only these formats.

## Conventions
- Type hints everywhere, small pure functions, docstrings on public functions.
- IDs (use exactly these everywhere, including docs/demo): accounts `ACC_0001`, txns `T000001`, alerts `AL-0001`, cases `C-001`, evidence `E1..En` (per case), drafts `D-001-v1`, devices `DEV_001`, IPs from 10.x / 192.0.2.x test ranges.
- Amounts as float, currency field separate; timestamps timezone-naive UTC.
- Streamlit state keys prefixed `rs_`. Use `st.cache_data` for heavy reads.
- Tests in `tests/`, run `pytest -q` and `ruff check .` after each task.

## Workflow expectations
- For any multi-file task: present a short plan first, then implement.
- After implementing: run tests, run `ruff check . --fix`, report what changed and how to verify in the UI.
- Keep `README.md` "How to run" section updated.
- If a requirement is ambiguous, choose the simplest option consistent with PRD and state the assumption.

## Commands
- Run app: `streamlit run app/Home.py`
- Tests: `pytest -q`
- Lint: `ruff check . --fix`
- Reset DB: `python -m core.db --reset`
