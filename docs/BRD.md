# Business Requirements Document (BRD) — RingSight

| Field | Value |
|---|---|
| Product | RingSight — AI Fraud-Ring Investigation & SAR Copilot |
| Sector | Banking / Financial Services — AML & Financial Crime Compliance |
| Version | 1.0 (Hackathon MVP) |
| Team | 3 members |

## 1. Problem statement
AML compliance analysts receive alerts from rule-based transaction monitoring. To decide whether to file a Suspicious Activity Report (SAR), they must manually:
1. Stitch together transfers across many accounts and banks.
2. Spot hidden structures — circular flows, structuring/smurfing, mule fan-outs, shared IPs/devices.
3. Write a regulator-facing narrative explaining *who, what, when, where, why, how*.

This takes hours to days per case, suffers from high false-positive rates, and generic GenAI is unsafe here because it can **invent facts** in a legal document.

## 2. Business objectives
| # | Objective | Measure (MVP demo) |
|---|---|---|
| BO1 | Cut investigation + SAR drafting time | Manual baseline ~hours → RingSight < 5 min per case |
| BO2 | Detect complex multi-account patterns rules miss | Recall on planted rings ≥ 90% on synthetic data |
| BO3 | Zero unsupported claims in narratives | 100% of narrative sentences cite valid evidence IDs (Grounding Score) |
| BO4 | Keep human accountability | Every SAR requires analyst approve/edit/reject; full audit trail |

## 3. Stakeholders
| Stakeholder | Interest |
|---|---|
| AML Analyst / Investigator | Faster triage, clear visual evidence, ready draft |
| BSA/AML Officer | Quality, consistency, audit-ready filings |
| Compliance Head / CRO | Lower cost per case, regulatory risk reduction |
| Regulator / Auditor | Explainable, traceable decisions |
| IT / Model Risk | Configurable, explainable, no black box |

## 4. Scope
**In scope (MVP):** CSV upload or synthetic generation; graph-based pattern detection; explainable risk scoring; case grouping; interactive network graph; agentic, evidence-cited SAR drafting with validation; analyst review & audit log; PDF export; detection-quality metrics.

**Out of scope (MVP):** real-time streaming, live core-banking integration, actual regulator e-filing, model training/fine-tuning, real customer data, authentication/RBAC.

## 5. Business rules
- BR1: The system **never** files a SAR; it only drafts. A named human decides.
- BR2: Every factual sentence in a draft must reference ≥ 1 evidence ID.
- BR3: Detection thresholds (structuring limit, time windows, cycle length) are **configurable**, not hard-coded.
- BR4: All analyst actions are timestamped in an immutable audit log.
- BR5: Only synthetic data is processed by free-tier LLMs.

## 6. Value & differentiation
| Existing market | Gap | RingSight answer |
|---|---|---|
| Rule-based TM systems | Single-transaction rules, high false positives, miss rings | Graph-level pattern detection |
| Enterprise graph platforms | Expensive, analyst still writes narrative | Auto-drafted narrative |
| Generic GenAI copilots | Hallucination risk, no traceability | **Evidence-grounded drafting + validator agent + Grounding Score** |

## 7. Assumptions & constraints
- One-day build, 3 people, AI coding assistants, free LLM tiers.
- Synthetic data only (own generator + optional IBM AML dataset).

## 8. Success criteria for the hackathon (mapped to judging)
| Criterion (weight) | How we demonstrate it |
|---|---|
| Problem relevance (20) | Real, regulated pain point; enforcement and cost context |
| Business impact & time saving (25) | Live timer: upload → approved SAR PDF in < 5 min |
| Adoption potential (20) | Human-in-loop, audit log, configurable rules, works on any CSV schema mapping |
| Usability (15) | 4 clean screens, one-click flows |
| Scalability & impact radius (10) | Same engine applies to fraud, trade-based laundering, insurance, crypto; swap SQLite→SQL Server, batch→stream |
| Team collaboration (10) | Clear module ownership, shown in closing slide |

## 9. Future roadmap (M.Tech)
- Train a Graph Neural Network on IBM AML data and benchmark vs. rule baseline.
- LangGraph multi-agent orchestration with memory; Agent-as-a-Judge evaluation.
- Streaming detection (Kafka) and SQL Server/Postgres scale-out.
