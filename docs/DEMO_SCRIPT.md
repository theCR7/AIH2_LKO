# 10-Minute Demo Script — 3 Speakers

**Setup before going on stage:** app open on Home, Demo mode already run, LLM cache warm, browser zoom 110%, backup video ready in another tab, timer visible.

| Time | Speaker | Slide / Screen | Script (talking points — say it naturally) |
|---|---|---|---|
| **0:00–0:45** | **A** | Slide 1: Title | "Good afternoon. We're Team ___, and this is **RingSight**: an AI copilot that finds hidden money-laundering rings and drafts a regulator-ready report where every amount, date and account is checked against evidence." |
| **0:45–2:15** | **A** | Slide 2: Problem | "When a bank's monitoring system raises an alert, an analyst has to stitch together transfers across many accounts, spot patterns like circular flows and structuring, and then write a Suspicious Activity Report by hand. That takes hours per case, and false positives are high. Generic AI can write fast, but in a legal filing **one invented fact is a compliance risk**. So the real problem isn't writing speed, it's *trustworthy* speed." |
| **2:15–2:30** | **A** | Handover | "Let me hand over to ___ to show it live." |
| **2:30–3:15** | **C** | App: Data → Home | "We start with 5,000 synthetic transactions across 500 accounts, with hidden laundering patterns planted inside. One click runs five graph detectors. In a few seconds we have 7 ranked cases." *(point to KPIs)* |
| **3:15–4:30** | **C** | Investigate: Case C-001 | "Here's the top case. This graph shows money leaving ACC_0018, passing through three accounts, and coming back in 3 days, keeping 92% of its value. That's classic layering. On the right, **Why flagged** explains the score line by line. Nothing is a black box." *(drag a node; open Evidence tab)* "Every fact is an evidence item: E1, E2, and so on." |
| **4:30–5:45** | **C** | SAR Draft tab | "Now I click **Draft SAR**." *(status steps animate)* "Four agents work in sequence: Evidence Builder, Typology, Narrative, Validator. **38 seconds.** Look: every sentence carries its evidence chips, and the Grounding Score is 100%." |
| **5:45–6:45** | **C** | Inject hallucination | "Judges always ask, what if the AI makes something up? Let's force it." *(toggle Inject hallucination → re-validate)* "This sentence claims a million-dollar transfer that never happened. The validator catches it, marks it red, and the score drops. **It can't slip into a filing.**" |
| **6:45–7:15** | **C** | Approve → PDF | "The analyst edits, approves with their name, and downloads the PDF. It's stamped, evidence-footnoted and logged in the audit trail. Over to ___ for how it works." |
| **7:15–8:45** | **B** | Slide 3: Architecture + Agent Trace | "Under the hood: detection is **deterministic graph analytics**: cycle detection, fan-in and fan-out, shared device and IP clusters, centrality, all configurable in a rules file. AI is used only where language matters, and it's fenced in: it receives a compact evidence pack, must return structured JSON with citations, and a validator checks every amount, date and account. Free models via a gateway with fallback and caching, and it even runs offline. On planted patterns we get *[X]% recall*; you can see precision and recall on the metrics page." |
| **8:45–9:30** | **A** | Slide 4: Impact & scale | "Impact: a case that we assume takes about 4 hours to draft manually (configurable baseline) is ready for review in under a minute, with a full audit trail. Analysts stay in control, which is what regulators expect. It scales by configuration: SQLite to SQL Server, batch to streaming, and new typologies are plug-ins. Next, we'll train a graph neural network on IBM's public AML dataset and benchmark it against these rules." |
| **9:30–10:00** | **A** | Slide 5: Team & close | "A built data and detection, B built the agents and validator, C built the experience. **RingSight: find the ring, back every claim.** Thank you, happy to take questions." |

## Slides (keep to 5)
1. Title + one-line pitch + team names
2. Problem: 3 icons (manual stitching, slow narratives, hallucination risk) + one statistic you can cite
3. Architecture diagram (mermaid from ARCHITECTURE.md) + "AI fenced by evidence" callout
4. Impact table (manual vs RingSight: time, consistency, traceability) + scale roadmap
5. Team roles + thank you

## Likely judge questions — owner & answer
| Question | Owner | Answer gist |
|---|---|---|
| Why not just use an existing AML product? | A | They detect; drafting is still manual or ungrounded. Our differentiator is evidence-grounded drafting + validator. |
| How accurate is detection? | B | Show metrics page; rules are transparent; GNN benchmark is the next step. |
| Real data / privacy? | A | Synthetic only today; production would use enterprise LLM endpoints inside the bank's tenant. |
| What if the LLM is down? | B | Fallback chain → mock mode; demo cached. |
| Does 100% grounding mean the narrative is true? | B | It means every number, date, account and citation matches evidence and no banned speculative claims; meaning-level checking is the optional LLM judge, and a human still signs off. |
| Cost? | B | Free-tier models; tiny token footprint because only the evidence pack is sent. |
| How would a bank adopt it? | C | CSV/column mapping today, API layer next; human approval and audit log built in. |

## Fill-in before demo
- [ ] Replace *[X]%* with actual recall from the metrics page.
- [ ] Replace "38 seconds" with your measured time.
- [ ] Confirm case IDs and account IDs match seed 42 output.
