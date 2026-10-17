"""Time-split tuning on the cached SAML-D sample: tune on the first half, report on the unseen second half."""
import sys, json, time
from collections import defaultdict
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
import pandas as pd
from core.config import load_rules
from core.detection.graph_builder import TxnRecord, build_graph
from core.detection.runner import run_all_detectors

S = pd.read_pickle(str(Path(__file__).with_name("saml_sample.pkl")))
SND, RCV, AMT = "Sender_account", "Receiver_account", "Amount"
cut = S["ts"].quantile(0.5)
halves = {"dev(first half)": S[S["ts"] < cut], "test(unseen 2nd half)": S[S["ts"] >= cut]}

def prep(df):
    keys = sorted(set(df[SND]) | set(df[RCV])); aid = {k: f"ACC_{i:04d}" for i, k in enumerate(keys, 1)}
    txns, lab, typ = [], {}, {}
    for i, r in enumerate(df.to_dict("records"), 1):
        t = f"T{i:06d}"; txns.append(TxnRecord(t, aid[r[SND]], aid[r[RCV]], float(r[AMT]), r["ts"].to_pydatetime()))
        lab[t] = int(r["Is_laundering"]); typ[t] = r["Laundering_type"]
    return build_graph(txns, {a: "individual" for a in aid.values()}), lab, typ
PREP = {k: prep(v) for k, v in halves.items()}

def run(over, half):
    bundle, lab, typ = PREP[half]
    rules = load_rules().model_copy(deep=True)
    for path, val in over.items():
        obj = rules; *par, leaf = path.split(".")
        for p in par: obj = getattr(obj, p)
        setattr(obj, leaf, val)
    t0 = time.time(); alerts = run_all_detectors(bundle, rules); dt = time.time() - t0
    pos = {t for t, l in lab.items() if l}; flag = {t for a in alerts for t in a.txn_ids}
    tp, fp, fn = len(pos & flag), len(flag - pos), len(pos - flag)
    return dict(P=round(tp / max(tp + fp, 1), 3), R=round(tp / max(tp + fn, 1), 3), tp=tp, fp=fp, alerts=len(alerts), s=round(dt, 1),
                pos=len(pos), rows=len(lab))

CONFIGS = {
    "A baseline (48h windows)": {},
    "B windows 7d": {"fan_in.window_hours": 168, "fan_out.window_hours": 168},
    "C windows 30d": {"fan_in.window_hours": 720, "fan_out.window_hours": 720},
    "D windows 90d": {"fan_in.window_hours": 2160, "fan_out.window_hours": 2160},
    "E windows 180d": {"fan_in.window_hours": 4320, "fan_out.window_hours": 4320},
    "F 90d + min 3 parties": {"fan_in.window_hours": 2160, "fan_out.window_hours": 2160, "fan_in.min_senders": 3, "fan_out.min_receivers": 3},
    "G 90d + min 3 + fan_out>=10k": {"fan_in.window_hours": 2160, "fan_out.window_hours": 2160, "fan_in.min_senders": 3, "fan_out.min_receivers": 3, "fan_out.min_total": 10000},
    "H 180d + min 3 + fan_out>=10k": {"fan_in.window_hours": 4320, "fan_out.window_hours": 4320, "fan_in.min_senders": 3, "fan_out.min_receivers": 3, "fan_out.min_total": 10000},
}
print("halves:", {k: (len(v), int(v["Is_laundering"].sum())) for k, v in halves.items()}, "cut", cut, flush=True)
rows = []
for name, over in CONFIGS.items():
    d, t = run(over, "dev(first half)"), run(over, "test(unseen 2nd half)")
    rows.append((name, d, t)); print(f"{name:34s} DEV P={d['P']:.3f} R={d['R']:.3f} (tp{d['tp']} fp{d['fp']})   TEST P={t['P']:.3f} R={t['R']:.3f} (tp{t['tp']} fp{t['fp']}) {t['s']}s", flush=True)
print("TUNE DONE")
