# Pre-build Review Notes — RingSight kickoff pack

Reviewed all 17 files end to end. The pack is solid: clear scope, sensible stack, good rules for Claude Code, realistic team plan. The changes below fix inconsistencies and a few technical traps that would have cost hours on the day.

## Blocking issues fixed

| # | Issue | Where | Fix applied |
|---|---|---|---|
| 1 | **Cycle enumeration explodes.** Measured: random 500-account / 5k-edge graph → ~181k cycles ≤ 6 hops, ~9.5 s before any filtering. Breaks the < 10 s target. | Master prompt item 7 | ARCHITECTURE §7a: filter edges, collapse to DiGraph, cap candidates, re-check on real txns. `cycles.min_amount`, `max_candidates` in rules.yaml |
| 2 | **Whole graph = one case.** "Connected-component case grouping" on the transaction graph merges everything via background noise. | PRD F3.3, master prompt | Components computed on the *alert graph* only (§7a) |
| 3 | **Payroll and merchants trigger fan-out / fan-in** → dozens of false cases, demo "7 cases" breaks. | Generator + detectors | `account_type` labels + `exclude_account_types` in rules.yaml; generator adds decoys so precision stays honest |
| 4 | **Validator can't catch the wireframe's own example** ("known shell company" has no amount/date/ID to check). | ARCHITECTURE §6 | Added speculation lexicon rule + totals rule; new tests in P4 |
| 5 | **pyvis loads vis.js from CDN** → graph blank when offline, contradicting "works with internet off". | P5 | `cdn_resources="in_line"`, `generate_html()`, physics off after stabilise |
| 6 | **Cache misses in demo.** Key included model name, so a fallback response is never reused; volatile values in prompts break hashing. | ARCHITECTURE §7, CLAUDE.md | Key = purpose + prompt_version + schema + prompts; temperature 0; hard rules 11–12 on determinism |
| 7 | **Ground truth can't compute per-pattern P/R/F1** — only `is_laundering` existed. | Schema | Added `gt_pattern`, `gt_ring_id`; ring-level match threshold defined |

## Consistency fixes

- **ID formats** differed between CLAUDE.md (`ACC_0001`, `C-001`) and wireframes/demo (`ACC_18`, `C-01`). Standardised everywhere; added alert (`AL-0001`), draft, device ID formats. Risk explanations previously used `C-002` for a cycle, colliding with case IDs.
- **Canonical narrative formats** (`48,200.00 USD`, `2026-09-03`) so validator regexes are reliable.
- `LLM_MAX_RETRIES` meant two different things (HTTP retries vs repair rounds) — clarified.
- `.gitignore` ignored all `*.html` → would have ignored the wireframes; now allows `docs/**/*.html`. Added `data/samples/.gitkeep` so the SQLite folder exists on fresh clone.
- `config/rules.yaml` added as a starter so thresholds are agreed *before* Claude Code invents them.

## Claims softened (judges will probe these)

- "Every sentence can be proven" → "every amount, date and account is checked against evidence". Grounding Score is consistency checking, not proof of truth. Added a prepared answer to the judge-question table.
- 4-hour manual baseline is now labelled an assumption. Find one public source before the demo or keep calling it an assumption.
- BR4 says "immutable audit log": SQLite isn't immutable, so a sha256 hash chain makes it tamper-evident instead.

## Added for the M.Tech path (cheap now, valuable later)

- `ConfidenceSignals` schema and `decision_log` table: evidence coverage, first-try validator pass rate, retries, fallback used, data-quality flags, LLM self-confidence as one weak signal.
- Outcome states `drafted` / `needs_review` / `escalated`. These are the hooks the confidence-aware planning roadmap needs; no extra UI on hackathon day.

## Still to decide as a team (not changed)

- Exact free-tier model IDs: re-check in AI Studio / Groq console the day before.
- IBM AML stretch (P10b): the HI-Small file is large and the first N rows may contain few laundering rows. Sample by `is_laundering` rather than head-N if you pick it.
- Run `pip freeze > requirements.lock` after the day-before install so all three laptops match.
- Corporate VDI: the checklist's personal-laptop advice stands.
