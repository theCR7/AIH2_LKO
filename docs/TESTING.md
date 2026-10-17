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

_Stretch options not pursued: FastAPI and SQL Server (P10c/d). The IBM/Kaggle loader (P10b) is covered in sections 6–7 below._


---

## 6. IBM AML (P10b) — real labelled data from Kaggle

**What was built.** `core/ingest/ibm_loader.py` downloads IBM's public AML benchmark, cleans it, samples by laundering label, remaps accounts to `ACC_####`, and persists it as the single active dataset (`ibm_hismall`). The Upload screen has a **Load IBM AML sample** action; Metrics shows transaction-level precision/recall/F1 for it. Sampling knobs are in `config/rules.yaml` (`ingest.ibm`).

| Item | Result |
|---|---|
| Dataset | `ealtman2019/ibm-transactions-for-anti-money-laundering-aml`, file `HI-Small_Trans.csv` (475,664,283 bytes) |
| Auth | The `KGAT_…` token works as a **Bearer** token against Kaggle's REST API — no `kaggle` CLI or username/key needed. Stored only in the git-ignored `.env`. |
| Funnel | 5,078,345 rows → 1,668,941 USD→USD rows → sample of **30,000 txns / 29,459 accounts** (all **1,912** USD laundering rows + 16,852 neighbour rows + 11,236 background rows) |
| Speed | load + sample + persist **7.7 s**; detection **4–6 s** (8.7 s before the fixes below) |
| Detection | 136 alerts (fan-in 29, fan-out 25, pass-through 82; **no cycles, no shared-identifier** — IBM has no device/IP data), 108 cases |
| Quality (txn-level) | **precision 0.544 · recall 0.149 · F1 0.233** (284 TP / 238 FP / 1,628 missed) |
| Live SAR (Groq `gpt-oss-120b`, top case C-001) | **grounding 100.0**, 14/14 statements cited, evidence coverage 1.0, 0 retries, no fallback, 20.1 s |
| Determinism | scripted run and in-app run produced identical alert/case counts; sampling is seeded (unit-tested) |

**Why recall is low (measured, not guessed).** The file has 5,177 laundering rows but only **1,912 (37%) are USD→USD**; the single-currency filter (needed so amounts are comparable and honestly labelled USD) drops the other 63% (Euro 1,372, Saudi Riyal 374, Swiss Franc 193, Yuan 184, …) and breaks rings that cross currencies. Of 2,707 laundering accounts in the sample only 314 have ≥2 laundering transactions. The rules are also tuned to the synthetic typologies. **Treat IBM as proof of scale and explainability, not an accuracy claim.**

### Faults found by running real data (all fixed, all with regression tests)

| # | Fault | Fix |
|---|---|---|
| F3 | **Mega-case**: transitive grouping through hub accounts made the top case 3,553 accounts / 1.8 billion USD | `cases.max_case_accounts` (50): larger groups split into one case per alert (`core/scoring/cases.py`) |
| F4 | **Mass payer flagged as layering**: one account paying 3,411 receivers in 48 h was the #1 case | `fan_out.max_receivers` / `fan_in.max_senders` = 100 (`config/rules.yaml`, `fan_patterns.py`). Txn precision **0.081 → 0.544**, F1 **0.113 → 0.233**, largest case 3,553 → **45** accounts |
| F5 | **Score saturation**: an account in 4 pass-through alerts stacked to 100; the top ten cases all tied | each pattern counts once per account, repeats noted ("+3 more") (`core/scoring/risk.py`); no IBM case saturates, 32 distinct scores. Seed-42 unchanged |
| F6 | **Download stall** at ~130 of 475 MB killed the transfer and the first design would have restarted from zero | resumable download: keeps `.part`, `Range` resume, verifies length, retries (offline tests with a fake `urlopen`) |
| F7 | **Account regex `ACC_\d{4}`** silently skipped grounding for ids ≥ ACC_10000 (IBM sample has 29k accounts) | `\d{4,}` in validator and QA; the live IBM SAR cites `ACC_25957` correctly |
| F8 | **Exact weighted betweenness** is O(V·E) — impractical at ~29k nodes (not benchmarked; replaced pre-emptively) | exact up to 2,000 accounts (seed-42 results unchanged), seeded sample of 256 pivots above that (`rules.yaml`) |
| F9 | Metrics told IBM users "needs the synthetic sample" (it only checked per-ring labels) | shows transaction-level P/R/F1 when only `is_laundering` exists |
| F10 | Process slip: `git add -A` committed the in-progress `data/HI-Small_Trans.part` (~125 MB) | removed from the (unpushed) commit before any push; `data/*.part` now ignored |

Thresholds F3/F4 were chosen after seeing IBM output — principled (an institution is not structuring) but not cross-validated; seed-42 behaviour and recall 1.0 are unchanged.

---

## 7. Hackathon readiness — verdict

**GO for the showcase**, with the demo path below. **57 pytest pass, ruff clean.**

**Demo-ready**
- Golden path on seed-42 data: Upload → Detect (C-001/C-002 **High**) → Investigate → live or cached SAR at 100% grounding → sign-off → PDF/TXT → Metrics + verified audit chain. Recall 1.0, deterministic, ~1.3 s detection.
- Offline mode (`LLM_MODE=mock`) and live Groq both verified; fallback chain verified.
- **Demo cache is warm** for C-001 and C-002 on `gpt-oss-120b`: replay measured at **0.0 s, every agent call a cache hit, grounding 100%**. C-001's first live narrative failed validation and the repair loop needed two rounds to fix it — the guardrail catching a real model's mistakes, a good thing to show.
- Real-data credibility: the same pipeline runs on 30,000 real labelled transactions in seconds and produces a fully grounded SAR.

**Weak / risky — say these before a judge does**
- **IBM accuracy is modest** (precision 0.54, recall 0.15) for the reasons in section 6. Do not present it as detection accuracy.
- **First live draft takes ~20 s**, and **Groq's free tier caps `gpt-oss-120b` at 8,000 tokens/minute** while one draft sends ~8k. Measured: pre-warming two drafts back to back hit the cap (HTTP 429); the gateway fell back to `gpt-oss-20b` as designed and both drafts still validated at 100%, but the 20B text is what got cached. Pace live drafts about 65 s apart, or pre-warm and rely on the cache.
- **IBM needs the 475 MB file in `data/`** (one-time, resumable, needs internet). Download before the demo.
- **The Demo-mode pre-warm button was dropped in the UI redesign**; the logic still exists in `core/demo.py` (see step 1 below).
- Pass-through prose can say "forwarded 171%": the rule has a ≥90% floor but no ceiling, so an outflow larger than the inflow qualifies. Consistent with the evidence, odd as prose.
- Case title names the busiest account, which can differ from the sender in the "Why flagged" sentence (C-001 on IBM: ACC_25316 vs ACC_0619). Per-alert splitting can yield near-duplicate pass-through cases around one hub.
- Streamlit logs `use_container_width` deprecation notices (removal date has passed); harmless today, will need `width="stretch"` on upgrade. After editing `core/` code, restart the server (Streamlit caches imported modules).
- **Rotate the Groq and Kaggle keys** — both were pasted in chat.

**Recommended demo path**
1. *Before the demo* (needs internet once): `.venv/Scripts/python.exe -c "from core.demo import run_demo; print(run_demo().fingerprint)"` regenerates seed 42, runs detection and pre-warms the top-2 SAR drafts so they replay instantly. `run_demo` does not pace its calls, so on the free tier the second draft may fall back to the 20B model (still 100% grounded); for 120b text, delete the `gpt-oss-20b` rows from `llm_cache` and draft C-001 and C-002 about 65 s apart. Confirm `data/HI-Small_Trans.csv` exists.
2. *Main story (about 5 min):* Upload → **Use sample dataset** → Detect → open C-001 → Draft SAR → click a citation chip → edit one sentence → sign-off → export.
3. *Real-data segment (60–90 s, optional):* Upload → **Load IBM AML sample** (~15 s) → 108-case queue → open the top case → Draft SAR → Metrics shows the honest P/R/F1.
4. *If the network or Groq fails:* set `LLM_MODE=mock` in `.env` and restart — instant and offline (IBM needs the cached file).

---

## 8. SAML-D loader and currency handling

**Built.** `core/ingest/saml_loader.py` (download, two-pass streaming sample, remap, persist, saved sample), a shared resumable downloader (`core/ingest/kaggle.py`, now also used by the IBM loader), a **Load SAML-D sample** card on Upload, and **recall by laundering type** on Metrics. Sampling knobs are in `config/rules.yaml` (`ingest.saml`).

| Item | Result (real file, 996,168,850 bytes) |
|---|---|
| Funnel | 9,504,852 rows, 8,414,112 UK-pound rows (88.5%); 9,873 laundering, **6,171 kept (62.5%)** |
| Sample | 40,000 txns, 44,003 accounts; 6,171 laundering (15.4%), 20,297 neighbour rows, 13,532 background rows |
| Speed | first load **26.8 s** (scans the file twice), then instant from the saved sample; detection **4.4 s** |
| Detection | 322 alerts (fan-in 54, fan-out 197, pass-through 71), 301 cases |
| Quality, rules as shipped | precision **0.073**, recall **0.021**, F1 0.033 (130 TP / 1,640 FP / 6,041 missed) |
| Recall by type | Smurfing 0.1%, Cash_Withdrawal 0%, Structuring 0.3%, Deposit-Send 9.9%, Layered_Fan_In 0.2%, Layered_Fan_Out 0.6% |
| Live SAR, top case (Groq `gpt-oss-120b`) | every amount in **GBP**; **17 of 17 statements cited**; 12.4 s |

The rules score poorly here for the reasons in `docs/SAML_D_EXPERIMENT.md`: month-long typologies against 48-hour windows, and amounts that do not separate laundering from normal traffic. This section proves the data path works, not that the rules fit it.

**Currency was hard-coded as USD.** `fmt_amount` defaulted to "USD" and the validator only recognised "USD", so a UK-pound dataset would have produced SARs that call pounds dollars. Fixed at the source: the loaded dataset's own currency (`core.utils.active_currency`, read from `transactions.currency`, cache reset whenever data is reloaded) is now used by every amount in the case queue, reasons, evidence, narrative, PDF and graph labels. The validator now recognises 17 ISO codes, flags a sentence that states a different currency than its cited evidence, and does not mistake words after a number ("5 ACH") for amounts. 11 new offline tests (73 total) cover selection, remapping, the saved sample, zip handling, the currency plumbing, per-type recall and the validator. Thresholds in `rules.yaml` (for example 10,000 and 50,000) are plain numbers and are read in the dataset's currency.

**Caveats.** The sample over-represents laundering (15.4%), so precision is flattered; the Metrics note says so. Only UK-pound rows are kept, so 37.5% of the laundering rows are excluded (not counted as missed). The generic CSV upload still defaults to USD unless a currency column is mapped. The LLM prompts still show a USD example; the validator catches a wrong currency rather than the prompt preventing it (prompt text was left unchanged to keep the warm SAR cache valid).
