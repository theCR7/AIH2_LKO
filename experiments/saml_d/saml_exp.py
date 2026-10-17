"""SAML-D experiment (scratch; never touches the project DB): EDA + detection metrics.

usage: python -I saml_exp.py <project_root> <max_total> [rules_override_json]
Two streaming passes over the 1 GB CSV (no full load), seeded sampling, then RingSight's own
detectors/scoring/case-grouping on an in-memory graph, scored against the dataset's labels.
"""
import sys, time, json, copy
from collections import Counter, defaultdict
from pathlib import Path

root = Path(sys.argv[1]); MAX_TOTAL = int(sys.argv[2])
override = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
sys.path.insert(0, str(root))
import numpy as np
import pandas as pd
from core.config import load_rules
from core.detection.graph_builder import TxnRecord, build_graph
from core.detection.runner import run_all_detectors
from core.scoring.risk import score_accounts
from core.scoring.cases import build_cases

CSV = root / "data" / "saml" / "SAML-D.csv"
SEED, CHUNK = 42, 1_000_000
SND, RCV, AMT, LAB, TYP = "Sender_account", "Receiver_account", "Amount", "Is_laundering", "Laundering_type"
PT, PC, RC = "Payment_type", "Payment_currency", "Received_currency"
READ = dict(chunksize=CHUNK, dtype={SND: "int64", RCV: "int64"})

# ---------- pass 1: EDA + all positives ----------
tot = pos = mism = 0; typ_ct, pt_all, pt_pos, cur = Counter(), Counter(), Counter(), Counter(); P_parts = []
for ch in pd.read_csv(CSV, **READ):
    lab = ch[LAB].astype(int); tot += len(ch); pos += int(lab.sum())
    p = ch[lab == 1]; P_parts.append(p)
    typ_ct.update(p[TYP]); pt_pos.update(p[PT]); pt_all.update(ch[PT]); cur.update(ch[PC]); mism += int((ch[PC] != ch[RC]).sum())
P = pd.concat(P_parts, ignore_index=True)
eda = {"rows": tot, "laundering": pos, "rate_pct": round(100 * pos / tot, 4), "mismatched_currency_rows": mism,
       "payment_type_all": pt_all.most_common(8), "payment_type_laundering": pt_pos.most_common(8),
       "currency_top": cur.most_common(4), "laundering_typologies": typ_ct.most_common(20)}
print("EDA", json.dumps(eda, indent=1), flush=True)

# ---------- pass 2: normals touching positive accounts + seeded background ----------
rng = np.random.RandomState(SEED)
if len(P) > MAX_TOTAL: P = P.sample(MAX_TOTAL, random_state=SEED)
budget = max(MAX_TOTAL - len(P), 0)
bad = set(P[SND]) | set(P[RCV]); frac = min(1.0, 3.0 * budget * 0.4 / max(tot - pos, 1))   # oversample, trim later
touch_parts, bg_parts = [], []
for ch in pd.read_csv(CSV, **READ):
    n = ch[ch[LAB].astype(int) == 0]
    t = n[SND].isin(bad) | n[RCV].isin(bad)
    touch_parts.append(n[t]); rest = n[~t]
    bg_parts.append(rest[rng.rand(len(rest)) < frac])
touch, bg = pd.concat(touch_parts, ignore_index=True), pd.concat(bg_parts, ignore_index=True)
nctx = min(int(budget * 0.6), len(touch))
S = pd.concat([P, touch.sample(nctx, random_state=SEED), bg.sample(min(budget - nctx, len(bg)), random_state=SEED)], ignore_index=True)
S["ts"] = pd.to_datetime(S["Date"].astype(str) + " " + S["Time"].astype(str))
S = S.sort_values(["ts", SND, RCV, AMT], kind="mergesort").reset_index(drop=True)
S.to_pickle(str(Path(__file__).with_name("saml_sample.pkl")))
keys = sorted(set(S[SND]) | set(S[RCV])); aid = {k: f"ACC_{i:04d}" for i, k in enumerate(keys, 1)}
txns, labels, typ = [], {}, {}
for i, r in enumerate(S.to_dict("records"), 1):
    tid = f"T{i:06d}"
    txns.append(TxnRecord(txn_id=tid, sender_id=aid[r[SND]], receiver_id=aid[r[RCV]], amount=float(r[AMT]), ts=r["ts"].to_pydatetime()))
    labels[tid] = int(r[LAB]); typ[tid] = str(r[TYP])
npos = sum(labels.values())
print(f"SAMPLE {len(txns)} txns, {len(keys)} accounts, laundering {npos} ({100*npos/len(txns):.1f}%)", flush=True)

# ---------- detect + score ----------
rules = load_rules().model_copy(deep=True)
for path, val in override.items():                      # e.g. {"fan_out.min_total": 20000}
    obj = rules; *parents, leaf = path.split(".")
    for p in parents: obj = getattr(obj, p)
    setattr(obj, leaf, val)
bundle = build_graph(txns, {a: "individual" for a in aid.values()})
t0 = time.time(); alerts = run_all_detectors(bundle, rules); t_det = time.time() - t0
risk = score_accounts(bundle, alerts, rules); cases, case_alerts = build_cases(alerts, risk, rules)
pos_ids = {t for t, l in labels.items() if l}; flag = {t for a in alerts for t in a.txn_ids}
tp, fp, fn = len(pos_ids & flag), len(flag - pos_ids), len(pos_ids - flag)
prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1); f1 = 2 * prec * rec / max(prec + rec, 1e-9)
by_t = defaultdict(lambda: [0, 0])
for t in pos_ids: by_t[typ[t]][1] += 1; by_t[typ[t]][0] += t in flag
byp = defaultdict(lambda: [0, 0])
for a in alerts:
    for t in a.txn_ids: byp[a.pattern][1] += 1; byp[a.pattern][0] += t in pos_ids
amap = {a.alert_id: a for a in alerts}
def share(c):
    ts = {t for x in case_alerts[c.case_id] for t in amap[x].txn_ids}; return len(ts & pos_ids) / len(ts) if ts else 0.0
sh = [share(c) for c in cases]
res = {"override": override, "detect_s": round(t_det, 1), "alerts": len(alerts), "cases": len(cases),
       "txn_level": {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "tp": tp, "fp": fp, "fn": fn},
       "recall_by_typology": {k: f"{v[0]}/{v[1]} ({100*v[0]/v[1]:.0f}%)" for k, v in sorted(by_t.items(), key=lambda kv: -kv[1][1])},
       "precision_by_detector": {k: f"{v[0]}/{v[1]} ({100*v[0]/max(v[1],1):.0f}%)" for k, v in byp.items()},
       "queue_majority_laundering": {f"top{k}": f"{sum(s >= .5 for s in sh[:k])}/{min(k, len(sh))}" for k in (5, 10, 25, 50, 100)}}
print("RESULT", json.dumps(res, indent=1), flush=True); print("EXPERIMENT DONE", flush=True)
