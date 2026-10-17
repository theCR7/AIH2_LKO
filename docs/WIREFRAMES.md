# Wireframes & Design System — RingSight

> Clickable HTML mockup: open `docs/wireframes/ringsight_mockup.html` in a browser (toggle *Wireframe / Hi-fi* top-right). Data shown there is illustrative, not seed-42 output.

## Design tokens
| Token | Value | Use |
|---|---|---|
| Primary | `#1E3A8A` (navy) | Header, primary buttons |
| Accent | `#0EA5E9` (sky) | Links, highlights |
| Risk High | `#DC2626` | score ≥ 70, suspicious edges |
| Risk Medium | `#F59E0B` | 40–69 |
| Risk Low | `#16A34A` | < 40 |
| Grounded | `#16A34A` badge | validated sentence |
| Ungrounded | `#FEE2E2` bg + `#DC2626` text | failed sentence |
| Surface | `#F8FAFC` | page background |
| Font | Inter / system sans | all text |
| Layout | `st.set_page_config(layout="wide")`, KPI cards with rounded borders |

Sidebar on every page: logo text **RingSight**, page nav, LLM status pill (`Gemini ✓ / Groq ✓ / Mock`), dataset name, "Reset demo" button.

---

## Screen 1 — Home / Dashboard (`app/Home.py`)
```
┌────────────────────────────────────────────────────────────────────────┐
│ RingSight  · AI Fraud-Ring Investigation & SAR Copilot     [LLM: Gemini✓]│
├────────────────────────────────────────────────────────────────────────┤
│ [Txns analysed] [Open cases] [High-risk accts] [Suspicious $] [Avg     │
│    5,000           7             23            1.84M        grounding  │
│                                                              98%]      │
│ [Est. analyst hours saved: 31.5 h]                                     │
├───────────────────────────────┬────────────────────────────────────────┤
│ Cases by pattern (bar)        │ Top 5 cases (table, click → Investigate)│
│                               │ ID   Pattern       Score  Status        │
│                               │ C-001 Cycle(4)       92    New           │
├───────────────────────────────┴────────────────────────────────────────┤
│ [ ▶ Generate demo data & run detection ]   (one-click demo button)     │
└────────────────────────────────────────────────────────────────────────┘
```

## Screen 2 — Data (`pages/1_Data.py`)
```
┌ Tabs: [Generate synthetic] [Upload CSV] [IBM AML sample] ───────────────┐
│ Generate: accounts [500] txns [5000] days [30] seed [42]                 │
│           planted: cycles[3] smurf[2] fan-out[1] shared-ID[1] passthru[1]│
│           [Generate]                                                     │
│ Upload:   [drop CSV]  → Column mapping: sender▾ receiver▾ amount▾ ts▾ …   │
│           Validation results ✓/✗                                         │
│ Preview table (first 50 rows)                                            │
│ [ Run detection ]  → progress bar per detector → "7 cases created"       │
└──────────────────────────────────────────────────────────────────────────┘
```

## Screen 3 — Cases (`pages/2_Cases.py`)
```
┌ Filters: pattern▾  min score [──●──]  status▾  search[ ]─────────────────┐
│ Case  Title                          Pattern(s)     Accts  Amount  Score │
│ C-001 4-hop circular flow via ACC_0018 Cycle           4    412k    92 ■  │
│ C-002 Structuring into ACC_0077      Fan-in          9    86k     81 ■  │
│ …                                                         [Investigate→]│
└──────────────────────────────────────────────────────────────────────────┘
```

## Screen 4 — Investigate (`pages/3_Investigate.py`) — the demo hero
```
┌ Case C-001 · Score 92 · Status: In Review          [Draft SAR ▶] ────────┐
├───────────────────────────────────────────┬──────────────────────────────┤
│                                           │ WHY FLAGGED                   │
│      INTERACTIVE GRAPH (pyvis, 60%)       │ • 4-hop cycle in 3 days (+35) │
│   (red edges = suspicious, size = risk)   │ • 92% value retained (+20)    │
│                                           │ • shared device DEV_009 (+15)     │
│                                           │ Account risk table            │
├───────────────────────────────────────────┴──────────────────────────────┤
│ Tabs: [Evidence E1..En] [Timeline] [SAR Draft] [Agent Trace] [Ask Case]  │
│                                                                          │
│ SAR Draft tab:                                                           │
│  Grounding Score: [ 100% ✓ ]   Typology: Layering via circular transfers │
│  ── Summary ──                                                           │
│  "Between 2026-09-03 and 2026-09-05, funds of 48,200.00 USD moved …" [E3][E4] ✓          │
│  "The subject is a known shell company…"  ✗ unsupported (red bg)       │
│  … sections …                                                            │
│  [Edit text]  [Re-validate]  [Approve ✓] [Reject ✗ reason: ___]          │
│  [Download PDF]     ⏱ Time to draft: 38 s  (baseline 4 h)               │
└──────────────────────────────────────────────────────────────────────────┘
Agent Trace tab:
  1 Evidence Builder   24 items     0.2 s
  2 Typology Agent     gemini-flash 3.1 s  conf 0.91
  3 Narrative Agent    gemini-flash 9.4 s
  4 Validator          2 issues → retry
  5 Narrative Agent    retry 1      7.8 s
  6 Validator          0 issues ✓  Grounding 100%
```

## Screen 5 — Audit & Metrics (`pages/4_Audit_and_Metrics.py`)
```
┌ Detection quality vs ground truth ───────────────────────────────────────┐
│ Pattern     Precision  Recall  F1      (bar chart)                        │
│ Cycle        1.00      1.00   1.00                                        │
│ Fan-in       0.90      1.00   0.95                                        │
├ Audit log ────────────────────────────────────────────────────────────────┤
│ Time  Actor  Action  Case  Before→After (expandable)    [Export CSV]      │
└──────────────────────────────────────────────────────────────────────────┘
```

## SAR PDF layout
1. Header: RingSight logo text, Case ID, date, status watermark (DRAFT until approved)
2. Case summary box (score, typology, total amount, date range, subjects)
3. Network graph PNG (matplotlib static render of the same subgraph)
4. Narrative — 5 sections, evidence IDs as superscript footnotes
5. Appendix A: evidence table; Appendix B: validation result & approver
