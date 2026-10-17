"""Natural-prevalence check: ALL transactions in a 30-day slice (no sampling), windowed detectors only."""
import sys, time
from collections import Counter
from pathlib import Path
root = Path(sys.argv[1]); LO, HI = sys.argv[2], sys.argv[3]
sys.path.insert(0, str(root))
import pandas as pd
from core.config import load_rules
from core.detection.graph_builder import TxnRecord, build_graph
from core.detection.fan_patterns import detect_fan_in, detect_fan_out
from core.detection.passthrough import detect_passthrough

CSV = root / "data" / "saml" / "SAML-D.csv"
parts = []
for ch in pd.read_csv(CSV, chunksize=1_000_000, dtype={"Sender_account": "int64", "Receiver_account": "int64"},
                      usecols=["Time", "Date", "Sender_account", "Receiver_account", "Amount", "Is_laundering", "Laundering_type"]):
    parts.append(ch[(ch["Date"] >= LO) & (ch["Date"] <= HI)])
S = pd.concat(parts, ignore_index=True)
S["ts"] = pd.to_datetime(S["Date"] + " " + S["Time"]); S = S.sort_values("ts", kind="mergesort").reset_index(drop=True)
codes, uniq = pd.factorize(pd.concat([S["Sender_account"], S["Receiver_account"]]), sort=True)
n = len(S); snd, rcv = codes[:n], codes[n:]
acc = [f"ACC_{i + 1:04d}" for i in range(len(uniq))]
txns = [TxnRecord(f"T{i + 1:07d}", acc[snd[i]], acc[rcv[i]], float(a), t.to_pydatetime())
        for i, (a, t) in enumerate(zip(S["Amount"].tolist(), S["ts"].tolist()))]
lab = S["Is_laundering"].astype(int).tolist(); pos = {f"T{i + 1:07d}" for i, l in enumerate(lab) if l}
bundle = build_graph(txns, {a: "individual" for a in acc})
print(f"SLICE {LO}..{HI}: {n:,} txns, {len(uniq):,} accounts, laundering {len(pos):,} ({100 * len(pos) / n:.3f}%)", flush=True)

def run(over):
    rules = load_rules().model_copy(deep=True)
    for path, val in over.items():
        obj = rules; *par, leaf = path.split(".")
        for p in par: obj = getattr(obj, p)
        setattr(obj, leaf, val)
    t0 = time.time()
    alerts = detect_fan_in(bundle, rules) + detect_fan_out(bundle, rules) + detect_passthrough(bundle, rules)
    flag = {t for a in alerts for t in a.txn_ids}; tp, fp = len(pos & flag), len(flag - pos)
    return dict(alerts=len(alerts), by=dict(Counter(a.pattern for a in alerts)), flagged_txns=len(flag), tp=tp, fp=fp,
                precision=round(tp / max(tp + fp, 1), 4), recall_in_slice=round(tp / max(len(pos), 1), 3),
                alerts_per_100k_txns=round(100_000 * len(alerts) / n, 1), s=round(time.time() - t0, 1))

for name, over in {"A baseline 48h": {}, "B 7d": {"fan_in.window_hours": 168, "fan_out.window_hours": 168},
                   "C 30d": {"fan_in.window_hours": 720, "fan_out.window_hours": 720}}.items():
    print(name, run(over), flush=True)
print("SLICE DONE")
