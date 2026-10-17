import os, numpy as np, pandas as pd
from datetime import datetime, timezone
import json
import config, db, model, coinswitch_client, paper, signals
from data import fetch_prices, data_age_hours
from logger import get_logger
log = get_logger()

def resolve_past(symbol, df):
    prices = {t.isoformat(): c for t, c in zip(df["ts"], df["close"])}
    for _, r in db.unresolved(symbol).iterrows():
        actual = prices.get(r["target_time"])
        if actual is None:
            continue
        err = abs(actual - r["predicted_price"])
        call = np.sign(r["predicted_price"] - r["base_price"])
        ok = None if call == 0 else int(call == np.sign(actual - r["base_price"]))   # no call = not counted
        db.resolve(int(r["id"]), actual, err, err / actual * 100, ok)
        log.info(f"[{symbol}] resolved {r['target_time']}: pred={r['predicted_price']:.2f} actual={actual:.2f} dir_ok={ok}")

def retrain_due(symbol):
    if not os.path.exists(model.model_path(symbol)):
        return True
    if model.bundle_fv(symbol) != config.FEATURE_VERSION:      # features changed -> old model is unusable
        return True
    runs = db.read("model_runs")
    runs = runs[runs["symbol"] == symbol]
    if runs.empty:
        return True
    last = pd.to_datetime(runs["run_at"]).max()
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600 >= config.RETRAIN_EVERY_HOURS

def log_coinswitch(symbol):
    """Log the real CoinSwitch INR quote (last, bid, ask) for comparison. Skips, with a clear log line, anything that is
    not configured, not listed on the exchange, or returns no quote. Read-only."""
    if not coinswitch_client.enabled() or symbol not in config.COINSWITCH_PAIRS:
        return
    pair = config.COINSWITCH_PAIRS[symbol]
    try:
        if not coinswitch_client.is_listed(pair):
            log.warning(f"[{symbol}] {pair} is not in CoinSwitch's list for this exchange; skipping its quote")
            return
        t = coinswitch_client.ticker(pair)
        if t is None:
            log.warning(f"[{symbol}] CoinSwitch returned no ticker for {pair}")
            return
        raw = json.dumps({k: t[k] for k in ("last", "bid", "ask", "spread", "at_ms", "pct_change_24h")})
        db.add_tick((datetime.now(timezone.utc).isoformat(), symbol, pair, t["last"], raw, t["bid"], t["ask"], t["exchange"]))
        log.info(f"[{symbol}] CoinSwitch {pair} last={t['last']} bid={t['bid']} ask={t['ask']}")
    except coinswitch_client.CoinSwitchError as e:
        log.warning(f"[{symbol}] CoinSwitch quote failed ({e.kind}): {e}")
    except Exception as e:
        log.warning(f"[{symbol}] CoinSwitch quote failed ({type(e).__name__})")

def held_symbols():
    try:
        return set(json.loads(db.kv_get("portfolio") or "{}").get("positions", {}))
    except Exception:
        return set()

def emit_signal(symbol, base, ret, info, df):
    """Build + store the structured signal. Alerts only for BUY/SELL and only the first time (no duplicates)."""
    now = datetime.now(timezone.utc)
    sig = signals.build_signal(symbol, base, ret, info, data_age_hours(df, pd.Timestamp(now)),
                               held=symbol in held_symbols(), now=now, source=df.attrs.get("source", "binance"))
    tt = (df["ts"].iloc[-1] + pd.Timedelta(hours=1)).isoformat()
    is_new = db.add_signal(symbol, tt, now.isoformat(), sig["signal"], signals.to_json(sig))
    log.info(f"[{symbol}] signal={sig['signal']} {sig['sell_type'] or ''} {'; '.join(sig['blockers'] or sig['reasons'])}")
    if is_new and sig["signal"] in ("BUY", "SELL") and sig["sell_type"] != "bearish_not_held":
        alerts.notify(signals.alert_text(sig))
    return sig

def run_symbol(symbol, df, ref):
    ref = None if symbol == config.REFERENCE_SYMBOL else ref
    resolve_past(symbol, df)
    src = df.attrs.get("source", "binance")
    if src != "binance":
        raise RuntimeError(f"{symbol}: only fallback price data available ({src}, no volume); skipping forecast")
    age = data_age_hours(df)
    if age > config.MAX_DATA_AGE_HOURS:
        raise RuntimeError(f"{symbol}: data is stale ({age:.1f}h since last candle closed); skipping forecast")
    if retrain_due(symbol):
        model.train(symbol, df, ref)
    tt, base, pred, ret, ver, name, info = model.predict_next(symbol, df, ref)
    db.add_prediction((symbol, datetime.now(timezone.utc).isoformat(), tt, base, pred, ret, ver, name))
    log.info(f"[{symbol}] predict {tt}: {pred:.4f} (base {base:.4f}, {ret*100:+.3f}%) model={name}/{ver} confidence={info['conf']}")
    emit_signal(symbol, base, ret, info, df)
    log_coinswitch(symbol)
    return ret, info["conf"] != "low"

def run_cycle():
    log.info("=== cycle start ===")
    dfs = {}
    for s in dict.fromkeys([config.REFERENCE_SYMBOL] + config.SYMBOLS):
        try:
            dfs[s] = fetch_prices(s)
            log.info(f"[{s}] fetched {len(dfs[s])} candles, latest {dfs[s]['ts'].iloc[-1]}")
        except Exception as e:
            log.error(f"[{s}] fetch failed: {e}")
    ref = dfs.get(config.REFERENCE_SYMBOL)
    preds, gate = {}, {}
    for s in config.SYMBOLS:
        if s in dfs:
            try:
                preds[s], gate[s] = run_symbol(s, dfs[s], ref)
            except Exception as e:
                log.exception(f"[{s}] cycle failed: {e}")
    try:
        paper.live_update(dfs, preds, gate if config.TRADE_ONLY_WITH_EDGE else None)
    except Exception as e:
        log.exception(f"paper trading failed: {e}")
    log.info("=== cycle end ===")
    return len(preds)

if __name__ == "__main__":
    run_cycle()
