# One-Day Team Plan (3 members, ~10 hours)

## Roles
| Member | Role | Owns (folders) | Claude Code branch |
|---|---|---|---|
| **A — Lead / Data & Platform** | Scaffold, data, detection, scoring, PDF, metrics, integration & merges | `core/ingest`, `core/detection`, `core/scoring`, `core/reporting`, `core/metrics.py`, `core/db.py` | `feat/data`, then `main` |
| **B — AI / Agents** | LLM gateway, prompts, evidence, typology, narrative, validator, orchestrator | `core/agents`, `config/prompts` | `feat/agents` |
| **C — UI / UX & Demo** | Streamlit pages, graph viz, review flow, slides, demo script, video backup | `app/`, slides | `feat/ui` |

Pick the presenter order now: **A = problem & impact, C = live demo, B = AI architecture & trust.**

## Timeline
| Time | Member A | Member B | Member C |
|---|---|---|---|
| **0:00–0:30** | Kickoff: re-read PRD, confirm 3 wow moments, confirm `.env` keys work | same | same |
| **0:30–2:00** | Runs **Master Prompt** (Phase 0) on `main`; pushes skeleton | Writes `config/prompts/*.md` drafts by hand; hand-crafts 1 sample EvidencePack JSON; tests prompts in AI Studio playground | Builds slide deck shell; studies pyvis; prepares `app/components/graph.py` prototype on a toy graph |
| **2:00** | ✅ **Sync 1 (15 min):** skeleton merged, everyone pulls `main` | | |
| **2:15–4:30** | Tune generator & detectors until recall test = 1.0; seed 42 sample CSV committed | **P1 → P2 → P3** on `feat/agents` | **P5** Investigate page on `feat/ui` |
| **4:30–5:00** | 🍽 Lunch + **Sync 2:** merge agents & UI into `main` (A merges) | | |
| **5:00–6:45** | **P7** PDF export, **P8** metrics | **P4** validator + orchestrator; craft hallucination-injection demo | **P6** SAR tab, review, audit |
| **6:45** | ✅ **Sync 3 (code freeze for features):** full golden-path run on one machine | | |
| **7:00–8:00** | **P9** hardening (A drives, B & C test on their laptops, file bugs) | Pre-warm LLM cache; test fallback (kill Gemini key) and mock mode | Screenshots into slides; record **backup demo video** (3 min) |
| **8:00–8:45** | **P10** stretch only if all green; else polish | Polish prompts for tone | UI polish |
| **8:45–9:30** | 🎤 Rehearsal ×2 with timer; fix only demo-blocking bugs | | |
| **9:30** | Tag release `v1.0-demo`; final push; README check | | |

## Collaboration rules
- One driver per branch; never two Claude Code sessions editing the same file.
- Interfaces are frozen at Sync 1: `core/schemas.py` changes need A's approval.
- Commit after each prompt; push at least hourly.
- Bug triage channel (Teams/WhatsApp): "page / steps / screenshot".
- If blocked > 20 min → switch to mock mode / simplify, don't sink time.

## Risk register
| Risk | Mitigation |
|---|---|
| Free-tier rate limit during demo | LLM cache pre-warmed; Groq fallback; mock mode |
| Corporate proxy breaks installs/API | Personal laptops + phone hotspot |
| pyvis rendering glitch | Static matplotlib PNG fallback |
| Merge conflicts | Folder ownership; A merges only at syncs |
| LLM produces ungrounded text | Validator + retries + highlight; it's a *feature* in the demo |
| Live demo failure | Recorded backup video + screenshots in slides |
