# RingSight — Testing, Hardening & Calibration Report

_Last run: 2026-10-17 · Python 3.14.3 (venv) · LLM: Groq live (`gpt-oss-120b` primary, `gpt-oss-20b` fallback) with offline mock path._

**Verdict: demo-ready.** All components pass regression, the live and offline LLM paths work, one real fault was found and fixed, scoring was recalibrated for a clearer demo, and the suite is green (**37 pytest pass, ruff clean**).

---

## 1. Regression results (every component)

| Component | Method | Result |
|---|---|---|
| config (rules/settings) | typed load of `rules.yaml` + `.env` | PASS |
| db (12 tables, reset, hash chain) | reset_db + `verify_audit_chain` | PASS |
| generator determinism | same seed → identical txn/ring IDs | PASS (5,039 txns, 8 rings) |
| generator account types | payroll + merchant tagged | PASS |
| csv_loader | valid load; friendly errors (missing map, bad date, negative amount) | PASS |
| detectors (cycle/fan-in/fan-out/shared/pass-through) | run over seed 42 | PASS — ring recall **1.0** every pattern |
| detectors exclusions | payroll/merchant never flagged | PASS (`[]`) |
| detectors precision | decoys/noise keep precision < 1.0 | PASS (honest) |
| runner performance | detection on ~5k txns | PASS — **1.3 s** (< 10 s) |
| scoring + cases | determinism of case IDs/scores | PASS |
| metrics | ring + txn P/R/F1 | PASS |
| evidence builder | ≤ 40 items, stable `E1..En` | PASS (15 items) |
| validator | flags wrong amount + unknown account, speculation lexicon, empty & unknown citations | PASS (4/4) |
| typology / narrative | grounded output | PASS |
| orchestrator | persists draft + audit + decision log | PASS |
| pdf export | `%PDF`, > 5 KB | PASS (~48 KB) |
| audit hash chain | verify | PASS |
| casegraph | hops 0/1, 150-node cap, entity type | PASS |
| demo.run_demo | determinism fingerprint stable across runs | PASS |
| qa (Ask-the-case, core only) | in-scope cites E-ids; out-of-scope refuses | PASS |
| LLM gateway — mock | deterministic, no network | PASS |
| LLM gateway — live Groq | one real call parses + caches | PASS (100% grounded, ~21 s) |
| LLM gateway — cache replay | 2nd identical call | PASS (both agents cache-hit, ~30 ms) |
| LLM gateway — fallback | primary forced to fail | PASS → `gpt-oss-20b`, `fallback_used=True` |
| UI golden path (light + dark) | sample → Detect → Investigate → Draft SAR → Report → approve → Metrics | PASS, no tracebacks |

Scripted regression harness: 29/30 automated checks PASS; the one miss was a test-script artifact (two faults placed on one CSV row — the loader correctly reports the first and skips), not a product defect.

---

## 2. Faults found & fixed (this change)

**F1 — `UNIQUE constraint failed: transactions.txn_id` on upload-after-sample (and generate-another-seed), plus cross-dataset contamination.**
Both the generator and the CSV loader mint transaction ids `T000001…` (a global primary key), but each persist only cleared *its own* `dataset_id`. Loading an upload after the sample (or generating a second seed) collided on the PK and crashed; worse, a prior run's `identifiers`/`accounts` survived and would leak into detection (e.g. the sample's shared-device cluster firing on an uploaded dataset).
_Fix:_ both `core/ingest/generator.py:_persist` and `core/ingest/csv_loader.py:_persist_upload` now call `clear_data(keep_llm_cache=True)` so the DB holds exactly one active dataset (LLM cache preserved for replay). Regression test added: `tests/test_generator.py::test_upload_replaces_prior_dataset_without_collision`.

**F2 — Detect queue showed every case while its caption claimed weak ones were hidden.**
The redesigned Detect screen ignored `cases.min_case_score`. _Fix:_ `app/screens/detect.py` now applies the threshold, shows an honest "_N weaker case(s) … hidden_" note, and an empty-state when nothing clears it.

---

## 3. Calibration (scoring & thresholds — single source: `config/rules.yaml`)

**Problem.** Top account scored 62.1 → no case reached the "high" band (≥ 70), so the risk story was flat. With the old `min_case_score=40`, only the two circular-flow cases cleared the bar; every planted fan-in / fan-out / shared-ID / pass-through ring scored 15–37 and was (correctly, but unhelpfully) below the line.

**Decision.** Recalibrated in `config/rules.yaml` (recall and determinism unaffected):
- `cycle` 35 → **45** — circular layering is the strongest single typology; its hub accounts (also pass-throughs) now reach "high".
- `passthrough` 20 → **25**, `shared_identifier` 15 → **25** — a rapid pass-through and a shared device/IP are meaningful signals, not trivia.
- `fan_in`/`fan_out` 30 → **32** — minor.
- `cases.min_case_score` 40 → **25** — surfaces every planted typology (and the honest decoy false-positives) as triageable cases while trivial, single-noise accounts (score 0) stay off the queue.

**Result (seed 42):** 7 high-risk accounts (≥ 70); the two cycle cases are **High** (77 / 75); all 11 cases list; ring-level recall stays **1.0**; full suite green. Bands unchanged (high 70 / medium 40).

---

## 4. Residual risks & follow-ups (not blocking)

- **Narrative style-phrase ban** ("In conclusion", "Furthermore", …) is in the prompt (`config/prompts/narrative.md`) but not enforced by the deterministic validator (which checks citations/amounts/dates/accounts/speculation). Add a style check to the validator if required.
- **DOCX export** not implemented — Report offers PDF + TXT (both offline). DOCX would need `python-docx`.
- **Live first-draft latency ~20 s** on Groq free tier (~30 rpm, ~8–12k tpm); cached replay is ~30 ms. For a demo, pre-warm the top cases (sidebar flow) or run `LLM_MODE=mock` for a guaranteed-offline, instant run.
- **One active dataset** by design — uploading or regenerating replaces the current dataset (no multi-dataset coexistence); this is what the collision fix enforces.
- **Theme switch**: this Streamlit 1.66 build's menu has no Settings → Theme; dark ships by setting `base="dark"` in `.streamlit/config.toml` (both themes verified).
- **Python 3.14** in the venv vs documented 3.11 — everything runs clean.

---

## 5. Final-ready checklist vs PRD §4 acceptance criteria

| Criterion | Status |
|---|---|
| Fresh clone → install → run < 5 min | ✅ (recreate venv + `.env`) |
| Generator + detection finds all planted rings (recall ≥ 90%) | ✅ 100% |
| ≥ 1 case drafts a SAR at 100% grounding | ✅ |
| Injected false sentence caught & highlighted | ✅ |
| PDF downloads; audit shows approve | ✅ |
| Works offline (mock + cache, pyvis inline) | ✅ |
| Same seed twice → identical case/evidence IDs + cached SAR | ✅ (determinism fingerprint) |
| Detection on 5k txns < 10 s | ✅ ~1.3 s |
| Audit hash chain verifies (`python -m core.db --verify-audit`) | ✅ |

_Not pursued here: the P10 stretch options (IBM/Kaggle loader, FastAPI, SQL Server) — the Kaggle dataset integration is a separate, approval-gated step._
