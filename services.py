"""Framework-free backend logic. api.py is a thin FastAPI layer over these functions,
so everything here can be unit-tested without a web server. Nothing here returns secrets."""
import json, math, os, time
from datetime import datetime, timezone
import numpy as np, pandas as pd
import config, db, alerts

MIN_TRADES_FOR_VERDICT = 30

def clean(o):
    """Make values JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(o, dict):  return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)): return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)): return o.isoformat()
    return o

def _age_hours(iso):
    if not iso: return None
    ts = pd.Timestamp(iso)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600

def check_symbol(symbol):
    if symbol not in config.SYMBOLS:
        raise KeyError(symbol)
    return symbol

# ---------- market / forecasts ----------
def latest_forecasts():
    P = db.read("predictions")
    out = []
    for s in config.SYMBOLS:
        r = P[P["symbol"] == s].sort_values("created_at")
        if r.empty:
            out.append({"symbol": s, "available": False}); continue
        n = r.iloc[-1]
        out.append({"symbol": s, "available": True, "created_at": n["created_at"], "target_time": n["target_time"],
                    "reference_price": n["base_price"], "price_source": "binance_usdt_last_closed_candle",
                    "predicted_price": n["predicted_price"], "predicted_return_pct": n["predicted_return"] * 100,
                    "model": n["model_name"], "model_version": n["model_version"],
                    "forecast_age_hours": _age_hours(n["created_at"]), "resolved": bool(n["resolved"])})
    return clean(out)

def latest_signals(include_payload=True):
    S = db.read("signals")
    out = []
    for s in config.SYMBOLS:
        r = S[S["symbol"] == s].sort_values("id")
        if r.empty:
            out.append({"symbol": s, "signal": None, "note": "no signal generated yet"}); continue
        out.append(json.loads(r.iloc[-1]["payload"]))
    return clean(out)

def accuracy(symbol):
    P = db.read("predictions")
    r = P[(P["symbol"] == symbol) & (P["resolved"] == 1)]
    calls = r["direction_correct"].dropna()
    n = int(len(calls))
    acc = float(calls.mean()) if n else None
    se = 0.5 / math.sqrt(n) if n else None
    return {"checked_predictions": n, "direction_right_rate": acc,
            "beats_coin_flip": bool(acc is not None and acc > 0.5 + 1.64 * se) if n >= MIN_TRADES_FOR_VERDICT else None,
            "verdict": "too early to tell" if n < MIN_TRADES_FOR_VERDICT else
                       ("better than a coin flip" if acc > 0.5 + 1.64 * se else "not clearly better than a coin flip"),
            "mean_abs_error_pct": float(r["pct_error"].mean()) if len(r) else None}

def model_performance():
    R = db.read("model_runs")
    out = []
    for s in config.SYMBOLS:
        r = R[R["symbol"] == s].sort_values("id")
        if r.empty:
            out.append({"symbol": s, "available": False}); continue
        l = r.iloc[-1]
        import model
        n = int(l["holdout_n"]) if "holdout_n" in l and pd.notna(l["holdout_n"]) else None
        out.append({"symbol": s, "available": True, "model": l["candidate"], "version": l["version"], "trained_at": l["run_at"],
                    "unseen_hours_scored": n, "mae": l["cv_mae"], "naive_mae": l["baseline_mae"],
                    "skill_vs_naive_pct": (1 - l["cv_mae"] / l["baseline_mae"]) * 100,
                    "direction_accuracy": l["cv_dir_acc"],
                    "grade": model.confidence(l["cv_mae"], l["baseline_mae"], l["cv_dir_acc"], n),
                    "score_basis": "untouched holdout" if n else "legacy cross-validation (re-score pending retrain)",
                    "live_accuracy": accuracy(s), "history_runs": int(len(r))})
    return clean(out)

# ---------- indicators / candles ----------
def indicators(df):
    d = df.copy(); c = d["close"]
    d["sma20"], d["sma50"] = c.rolling(20).mean(), c.rolling(50).mean()
    sd = c.rolling(20).std(); d["bb_mid"] = d["sma20"]; d["bb_up"] = d["sma20"] + 2 * sd; d["bb_lo"] = d["sma20"] - 2 * sd
    delta = c.diff(); up = delta.clip(lower=0).rolling(14).mean(); dn = (-delta.clip(upper=0)).rolling(14).mean()
    d["rsi14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    d["macd"], d["macd_signal"] = macd, macd.ewm(span=9).mean(); d["macd_hist"] = d["macd"] - d["macd_signal"]
    d["volatility24"] = c.pct_change().rolling(24).std()
    d["momentum12"] = c.pct_change(12)
    return d

def regime(d):
    """bullish / bearish / sideways from price vs SMA50 and SMA20 slope. A description, not a forecast."""
    last = d.iloc[-1]
    if not np.isfinite(last["sma50"]): return "unknown"
    slope = last["sma20"] / d["sma20"].iloc[-6] - 1 if len(d) > 6 and np.isfinite(d["sma20"].iloc[-6]) else 0
    dist = last["close"] / last["sma50"] - 1
    if dist > 0.01 and slope > 0: return "bullish"
    if dist < -0.01 and slope < 0: return "bearish"
    return "sideways"

_CACHE = {}          # symbol -> (fetched_at, dataframe, candles_requested)
WARMUP_CANDLES = 100  # extra history so SMA50 / MACD / RSI are filled from the first displayed candle
def candles(symbol, limit=300, ttl=120):
    """Cached fetch of just what the chart needs (not the model's 4000). Always reports source + age so the UI
    can never pass off stale data as live."""
    check_symbol(symbol)
    need = limit + WARMUP_CANDLES
    hit = _CACHE.get(symbol)
    if not hit or time.time() - hit[0] > ttl or hit[2] < need:
        from data import fetch_prices
        _CACHE[symbol] = hit = (time.time(), fetch_prices(symbol, need), need)
    return candles_payload(symbol, hit[1], limit, fetched_at=hit[0])

def candles_payload(symbol, df, limit=300, fetched_at=None):
    from data import data_age_hours
    d = indicators(df).tail(limit)
    rows = [{"time": int(pd.Timestamp(r.ts).timestamp()), **{k: getattr(r, k) for k in
             ("open", "high", "low", "close", "volume", "sma20", "sma50", "bb_up", "bb_lo", "rsi14", "macd", "macd_signal", "macd_hist")
             if hasattr(r, k)}} for r in d.itertuples()]
    return clean({"symbol": symbol, "interval": config.INTERVAL, "source": df.attrs.get("source", "binance"),
                  "note": "Closed hourly candles from Binance (USDT). Not live and not CoinSwitch INR prices.",
                  "last_candle_time": pd.Timestamp(df["ts"].iloc[-1]).isoformat(), "data_age_hours": data_age_hours(df),
                  "fetched_at": datetime.fromtimestamp(fetched_at or time.time(), timezone.utc).isoformat(),
                  "regime": regime(indicators(df)), "candles": rows})

def coin_analysis(symbol):
    check_symbol(symbol)
    f = next(x for x in latest_forecasts() if x["symbol"] == symbol)
    s = next(x for x in latest_signals() if x["symbol"] == symbol)
    m = next(x for x in model_performance() if x["symbol"] == symbol)
    return {"symbol": symbol, "forecast": f, "signal": s, "model": m,
            "disclaimer": "Learning project. Not financial advice. Forecasts can be wrong and models may have no edge."}

# ---------- paper trading ----------
def paper_portfolio():
    E, T = db.read("paper_equity"), db.read("paper_trades")
    raw = db.kv_get("portfolio"); pf = json.loads(raw) if raw else {}
    out = {"start_balance": config.PAPER_START_BALANCE, "currency": "USDT (paper)", "open_positions": pf.get("positions", {}),
           "trades": int(len(T))}
    if len(E):
        e = E["equity"]; out.update({"equity": e.iloc[-1], "cash": E["cash"].iloc[-1], "buy_hold_equity": E["bh_equity"].iloc[-1],
                                     "max_drawdown_pct": float((e / e.cummax() - 1).min() * 100),
                                     "current_drawdown_pct": float((e.iloc[-1] / e.max() - 1) * 100), "last_update": E["ts"].iloc[-1]})
    out["realized_pnl"] = float(T["pnl"].sum()) if len(T) else 0.0
    out["fees_paid"] = float(T["fees"].sum()) if len(T) else 0.0
    out["win_rate_pct"] = float((T["pnl"] > 0).mean() * 100) if len(T) else None
    out["statistically_conclusive"] = bool(len(T) >= MIN_TRADES_FOR_VERDICT)
    out["note"] = ("" if len(T) >= MIN_TRADES_FOR_VERDICT else
                   f"Only {len(T)} closed trades; results are inconclusive below {MIN_TRADES_FOR_VERDICT}.")
    return clean(out)

def paper_trades(limit=200):
    T = db.read("paper_trades").sort_values("id", ascending=False).head(limit)
    return clean(T.to_dict("records"))

def paper_equity(limit=2000):
    return clean(db.read("paper_equity").sort_values("ts").tail(limit).to_dict("records"))

def backtest_report():
    p = os.path.join(os.path.dirname(config.DB_PATH) or ".", "backtest_summary.csv")
    if not os.path.exists(p):
        return {"available": False, "note": "Run `python backtest.py` first."}
    df = pd.read_csv(p)
    rows = clean(df.to_dict("records"))
    for r in rows:
        r["inconclusive"] = bool((r.get("trades") or 0) < MIN_TRADES_FOR_VERDICT)
    return {"available": True, "rows": rows, "note": "Rows with fewer than 30 trades are statistically inconclusive.",
            "generated_at": datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).isoformat()}

# ---------- system ----------
def alert_config():
    """Channel status only. Secrets are never returned."""
    return {"channels": alerts.channels(), "drawdown_alert_pct": config.ALERT_DRAWDOWN * 100,
            "signal_alerts": "BUY and SELL-exit signals, once per signal", "editable_via_api": False}

def recent_alerts(limit=50):
    p = config.LOG_PATH
    if not os.path.exists(p): return []
    with open(p, errors="replace") as f:
        lines = [l.rstrip() for l in f if "[alert]" in l or "ERROR" in l or "fetch failed" in l]
    return lines[-limit:]

def health():
    last = db.kv_get("last_success"); age = _age_hours(last)
    ok = age is not None and age <= config.HEALTH_MAX_AGE_HOURS
    return {"status": "ok" if ok else "degraded", "worker_last_success": last, "worker_age_hours": age,
            "max_age_hours": config.HEALTH_MAX_AGE_HOURS, "tracked_coins": len(config.SYMBOLS),
            "alert_channels": alerts.channels(), "coinswitch_configured": bool(os.getenv("COINSWITCH_API_KEY"))}
