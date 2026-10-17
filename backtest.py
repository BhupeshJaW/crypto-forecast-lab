"""Walk-forward backtest: replays the last N hours as if live (retrain every 24h on past data only),
then runs the paper-trading rules on the predictions. Shows what fees and thresholds do.
Usage: python backtest.py [--model ridge|extra_trees|hist_gbm|...] [--hours 600]"""
import argparse, os
import numpy as np, pandas as pd
from sklearn.base import clone
import config, model, paper
from data import fetch_prices

def walk_forward(df, ref, name, test_hours, retrain=24):
    d, feats = model.make_features(df, ref)
    ok = d.dropna(subset=feats).reset_index(drop=True)
    s = max(len(ok) - test_hours, 300)
    preds = {}
    for i in range(s, len(ok), retrain):
        tr = ok.iloc[:i].dropna(subset=["target"])          # only targets already known at time i
        m = model.fit_model(model.candidates()[name], tr[feats], tr["target"])
        chunk = ok.iloc[i:i + retrain]
        preds.update(zip(chunk["ts"], m.predict(chunk[feats])))
    return ok.set_index("ts"), preds

def simulate(candles, preds, label):
    ts_all = sorted(set.intersection(*[set(p) for p in preds.values()]))
    pf, rows, trades = paper.Portfolio(), [], []
    start = {s: candles[s].loc[ts_all[0], "close"] for s in candles}
    for ts in ts_all:
        prices = {s: float(candles[s].loc[ts, "close"]) for s in candles}
        for s in candles:
            c = candles[s].loc[ts]
            trades += pf.step(s, ts, {"close": c["close"], "low": c["low"], "high": c["high"]} if "low" in c and pd.notna(c["low"])
                              else {"close": c["close"]}, preds[s][ts], prices)
        bh = pf.start_equity * (1 - config.FEE_RATE) * np.mean([prices[s] / start[s] for s in start])
        rows.append({"ts": ts, "equity": pf.equity(prices), "bh_equity": bh})
    res = paper.summary(pd.DataFrame(rows), pd.DataFrame(trades))
    res["scenario"] = label
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ridge")
    ap.add_argument("--hours", type=int, default=600)
    a = ap.parse_args()
    dfs = {s: fetch_prices(s) for s in config.SYMBOLS}
    ref = dfs.get(config.REFERENCE_SYMBOL)
    candles, preds = {}, {}
    for s in config.SYMBOLS:
        candles[s], preds[s] = walk_forward(dfs[s], None if s == config.REFERENCE_SYMBOL else ref, a.model, a.hours)
        c = candles[s]
        idx = [t for t in preds[s] if t in c.index and pd.notna(c.loc[t, "target"])]
        acc = np.mean([np.sign(preds[s][t]) == np.sign(c.loc[t, "target"]) for t in idx])
        mae = np.mean([abs(preds[s][t] - c.loc[t, "target"]) for t in idx])
        naive = np.mean([abs(c.loc[t, "target"]) for t in idx])
        z = (acc - 0.5) / (0.5 / np.sqrt(len(idx))) if idx else 0.0
        verdict = "better than guessing" if (z > 1.64 and mae < naive) else "NOT clearly better than guessing"
        print(f"{s}: {len(idx)} unseen-data predictions | direction right {acc*100:.1f}% (coin flip = 50%) | "
              f"error vs 'price stays same': {(1 - mae/naive)*100:+.1f}% | {verdict}")
    orig = (config.ENTRY_THRESHOLD, config.FEE_RATE, config.SLIPPAGE, config.TDS_RATE)
    out = []
    for thr in (0.0, 0.001, 0.002, 0.003, 0.005):
        config.ENTRY_THRESHOLD = thr
        out.append(simulate(candles, preds, f"buy if predicted >= {thr*100:.2f}%, with fees"))
    config.ENTRY_THRESHOLD, config.FEE_RATE, config.SLIPPAGE = orig[0], 0.0, 0.0
    out.append(simulate(candles, preds, f"buy if predicted >= {orig[0]*100:.2f}%, NO fees (unrealistic)"))
    config.ENTRY_THRESHOLD, config.FEE_RATE, config.SLIPPAGE, config.TDS_RATE = orig
    df = pd.DataFrame(out).set_index("scenario").round(2)
    print(f"\nModel: {a.model}, last {a.hours} hours, start balance {config.PAPER_START_BALANCE:,.0f}")
    print(df.to_string())
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/backtest_summary.csv")
    print("\nSaved data/backtest_summary.csv (shown in the dashboard's Paper trading tab).")

if __name__ == "__main__":
    main()
