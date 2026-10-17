import sys, pandas as pd
csv, out, lo, hi = sys.argv[1:5]
parts = [c[(c["Date"] >= lo) & (c["Date"] <= hi)] for c in pd.read_csv(csv, chunksize=1_000_000)]
S = pd.concat(parts, ignore_index=True)
S["ts"] = pd.to_datetime(S["Date"] + " " + S["Time"]); S = S.sort_values("ts", kind="mergesort").reset_index(drop=True)
S.to_pickle(out); print("cached", len(S), int(S["Is_laundering"].sum()), flush=True)
