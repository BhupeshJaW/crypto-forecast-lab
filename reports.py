import pandas as pd
from datetime import datetime, timezone, timedelta
import config, db

def _plain(r):
    import explain
    emoji, head, _ = explain.verdict(r)
    naive = ((r["actual_price"] - r["base_price"]).abs() / r["actual_price"]).mean() * 100
    calls = r["direction_correct"].dropna()
    right = f"up/down right {int(calls.sum())} of {len(calls)}" if len(calls) else "no up/down calls"
    return f"{emoji} {head}. {right}; typical miss {r['pct_error'].mean():.2f}% (guessing 'no change' misses {naive:.2f}%)"

def daily_summary():
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    L = [f"Daily summary {now:%Y-%m-%d}", "", "Forecast quality, last 24 hours:"]
    P = db.read("predictions")
    P = P[(P["resolved"] == 1)]
    P = P[pd.to_datetime(P["target_time"]) >= since] if len(P) else P
    for s in config.SYMBOLS:
        r = P[P["symbol"] == s] if len(P) else P
        coin = s.replace("USDT", "")
        L.append(f"- {coin}: " + (_plain(r) if len(r) else "nothing checked yet"))
    E, T = db.read("paper_equity"), db.read("paper_trades")
    L += ["", "Pretend-money account:"]
    if len(E):
        E["ts"] = pd.to_datetime(E["ts"])
        old = E[E["ts"] <= E["ts"].iloc[-1] - timedelta(hours=24)]
        chg = (E["equity"].iloc[-1] / (old["equity"].iloc[-1] if len(old) else E["equity"].iloc[0]) - 1) * 100
        L.append(f"- Now {E['equity'].iloc[-1]:,.2f} USDT ({chg:+.2f}% in 24h). Buy-and-hold would be {E['bh_equity'].iloc[-1]:,.2f}.")
    if len(T):
        t = T[pd.to_datetime(T["exit_time"]) >= since]
        L.append(f"- Trades closed in 24h: {len(t)}, profit/loss {t['pnl'].sum():+.2f} USDT, fees {t['fees'].sum():.2f} USDT.")
    return "\n".join(L)
