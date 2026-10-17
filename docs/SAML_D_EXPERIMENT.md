# SAML-D experiment: what it takes to score well on rare-event AML data

Date: 2026-10-17. All figures below were measured by the scripts in `experiments/saml_d/`.
Nothing here is wired into the application yet; it is the evidence for the next step.

## The question

Laundering is always rare, so how can RingSight reach good performance metrics? We fetched
a second labelled dataset, SAML-D, and tested.

## Dataset

SAML-D (Oztas et al., IEEE ICEBE 2023; Kaggle `berkanoztas/synthetic-transaction-monitoring-dataset-aml`,
CC BY-NC-SA 4.0, cite the paper). 9,504,852 transactions, 9,873 laundering (**0.1039%**), 12 columns,
17 laundering typologies plus 11 normal ones that deliberately look similar (for example `Normal_Fan_Out`).
Laundering patterns unfold over **weeks to months** (median span at the receiver: Structuring about 190
days, Smurfing about 120 days), and amounts barely separate them (median 5.3k laundering vs 6.1k normal).

## Result 1: RingSight's rules, as shipped, on a 40,000-row sample

| | Value |
|---|---|
| Sample | 40,000 txns, laundering 9,873 (24.7%) |
| Transaction precision / recall | 0.415 / **0.035** |
| Best typologies | Cycle 27% recall, Deposit-Send 20%, Fan_Out 8% |
| Missed (about 0%) | Structuring, Cash_Withdrawal, Smurfing, Layered fan-in/out |

The detectors use 48-hour windows; these typologies are months long.

## Result 2: widening the windows looks good on a sample (time-split, tuned on the first half)

| Rules | Unseen half precision | recall |
|---|---|---|
| 48 h windows | 0.436 | 0.037 |
| 30-day windows | **0.817** | **0.304** |
| 180-day windows, min 3 parties, fan-out >= 10k | 0.443 | 0.657 |

## Result 3: the same rules on a complete, unsampled 30-day slice

879,750 transactions, 924 laundering (**0.105%**, the real prevalence).

| Rules | Alerts | Precision | Recall in slice |
|---|---|---|---|
| 48 h windows | 30,870 | **0.06%** | 11.7% |
| 30-day windows | 42,542 (about 4,800 per 100k txns) | **0.08%** | 55% |

**The 82% precision in Result 2 was a sampling artifact.** The sample keeps every laundering row but only
about 0.3% of normal traffic, which hides almost all false positives. Pass-through looked 94% precise in
the sample and raises 26,918 alerts on real traffic. Rules alone cannot reach a usable alert volume here.

## Result 4: a learned ranking layer, natural prevalence, unseen days

Gradient boosting on label-free features (amount, hour, payment type and location, and each account's own
behaviour: counterparties, volumes, repeat pairs). Trained on days 1-15 of the slice, tested on days 16-30
(438,701 transactions, 424 laundering, 0.097%).

| Metric | All features | Behaviour/graph features only |
|---|---|---|
| PR-AUC (random = 0.001) | **0.742** | 0.695 |
| Precision in the top 100 | 96% | 92% |
| Precision in the top 1,000 | 34% | 33% |
| Recall reviewing the top 0.1% (438 txns) | 73% | 70% |
| Recall reviewing the top 1% (4,387 txns) | **90%** | 88% |

Dropping payment type and location costs little, so the result does not hinge on those columns.

## What this means

1. Report **PR-AUC, precision at k and recall at an alert budget at natural prevalence**, not accuracy and
   not precision on an enriched sample.
2. Rules give explanations but not a usable ranking. A learned ranking layer gives the ranking. The
   hybrid keeps the explainable rule reason and evidence and adds a risk score from the model.
3. The rules' windows should match the data's time horizon, but that alone is not enough (Result 3).

## Caveats

- Synthetic data with learnable generator signatures; real-world performance will be lower.
- One 30-day slice and one split; no confidence intervals (424 positives in the test half).
- Account aggregates were computed within each half (label-free, but not strictly causal).
- Hyperparameters were left at defaults (no tuning), so they are not a source of leakage, but they are
  also not optimised.
- Transaction-level, not case-level. Case-level quality still needs to be measured.

## Reproduce

Needs `data/saml/SAML-D.csv` (git-ignored; about 1 GB, download with the Kaggle token in `.env`). The
ranking script needs scikit-learn and pyarrow in a separate environment, since neither is a RingSight
dependency.

```bash
python -I experiments/saml_d/saml_exp.py <project_root> 40000        # Result 1 (writes saml_sample.pkl)
python -I experiments/saml_d/saml_tune.py <project_root>             # Result 2
python -I experiments/saml_d/saml_slice.py <project_root> 2023-01-01 2023-01-30   # Result 3
python -I experiments/saml_d/cache_slice.py data/saml/SAML-D.csv experiments/saml_d/slice_jan.pkl 2023-01-01 2023-01-30
python experiments/saml_d/ml_rank.py experiments/saml_d/slice_jan.pkl   # Result 4 (scikit-learn env)
```
