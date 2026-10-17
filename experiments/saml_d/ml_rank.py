"""Feasibility test: a learned ranking layer on top of transaction behaviour, natural prevalence, time split."""
import sys, json
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

S = pd.read_pickle(sys.argv[1])
SND, RCV = "Sender_account", "Receiver_account"
cut = S["ts"].min() + (S["ts"].max() - S["ts"].min()) / 2
cats = ["Payment_type", "Payment_currency", "Received_currency", "Sender_bank_location", "Receiver_bank_location"]
codes = {c: {v: i for i, v in enumerate(sorted(S[c].unique()))} for c in cats}

def features(df, with_context):
    d = pd.DataFrame(index=df.index)
    d["amount"] = df["Amount"]; d["log_amount"] = np.log1p(df["Amount"])
    d["hour"] = df["ts"].dt.hour; d["dow"] = df["ts"].dt.dayofweek
    g = df.groupby(SND)["Amount"]; r = df.groupby(RCV)["Amount"]
    d["s_out_n"] = g.transform("size"); d["s_out_sum"] = g.transform("sum"); d["s_out_mean"] = g.transform("mean")
    d["s_out_peers"] = df.groupby(SND)[RCV].transform("nunique")
    d["r_in_n"] = r.transform("size"); d["r_in_sum"] = r.transform("sum")
    d["r_in_peers"] = df.groupby(RCV)[SND].transform("nunique")
    d["s_in_n"] = df[SND].map(df.groupby(RCV).size()).fillna(0); d["r_out_n"] = df[RCV].map(df.groupby(SND).size()).fillna(0)
    d["pair_n"] = df.groupby([SND, RCV])["Amount"].transform("size")
    d["rel_amount"] = df["Amount"] / d["s_out_mean"].clip(lower=1)
    d["s_small_share"] = (df["Amount"] < 10000).groupby(df[SND]).transform("mean")
    if with_context:
        for c in cats: d[c] = df[c].map(codes[c]).astype(int)
        d["cross_border"] = (df["Sender_bank_location"] != df["Receiver_bank_location"]).astype(int)
        d["cur_mismatch"] = (df["Payment_currency"] != df["Received_currency"]).astype(int)
    return d

tr, te = S[S["ts"] < cut], S[S["ts"] >= cut]
ytr, yte = tr["Is_laundering"].astype(int).values, te["Is_laundering"].astype(int).values
print(f"train {len(tr):,} rows ({ytr.sum()} laundering, {100*ytr.mean():.3f}%)  test {len(te):,} rows ({yte.sum()} laundering, {100*yte.mean():.3f}%)", flush=True)

out = {}
for name, ctx in {"behaviour+payment/location features": True, "behaviour/graph-only features": False}.items():
    Xtr, Xte = features(tr, ctx), features(te, ctx)
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, random_state=42,
                                       class_weight="balanced")
    m.fit(Xtr, ytr); p = m.predict_proba(Xte)[:, 1]
    order = np.argsort(-p); hit = yte[order]; n = len(yte); P = yte.sum()
    res = {"base_rate_pct": round(100 * P / n, 3), "pr_auc": round(average_precision_score(yte, p), 3), "roc_auc": round(roc_auc_score(yte, p), 3)}
    for k in (100, 500, 1000, 5000):
        res[f"precision@{k}"] = round(float(hit[:k].mean()), 3)
    for pct in (0.1, 0.5, 1, 5):
        k = int(n * pct / 100); res[f"recall@top{pct}%({k:,} txns reviewed)"] = round(float(hit[:k].sum() / P), 3)
    out[name] = res
print(json.dumps(out, indent=1)); print("ML DONE", flush=True)
