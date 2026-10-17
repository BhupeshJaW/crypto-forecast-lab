"""Checks that a RUNNING API returns every field the frontend types (frontend/src/types/api.ts) expect.
Usage:  API_TOKEN=... CHECK_BASE=http://127.0.0.1:8000 python tools/check_api_contract.py
Read-only GET requests; changes nothing. Note: it also asserts that a missing/wrong token is rejected, so run it with API_TOKEN set on the server."""
import json, sys, urllib.request, urllib.error
import os
BASE = os.getenv("CHECK_BASE", "http://127.0.0.1:8000")
TOKEN = os.getenv("API_TOKEN", "")
def get(path, token=None):
    token = TOKEN if token is None else token
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, None
bad = []
def need(name, obj, keys):
    miss = [k for k in keys if k not in obj]
    print(f"  {'OK ' if not miss else 'BAD'} {name}" + (f" missing {miss}" if miss else ""))
    if miss: bad.append((name, miss))
SIG = ["symbol","signal","sell_type","reference_price","price_source","price_note","horizon_hours","predicted_return_pct",
       "typical_error_band_pct","estimated_round_trip_cost_pct","net_edge_after_costs_pct","model_grade","holdout_hours",
       "grade_note","data_age_hours","created_at","expires_at","reasons","blockers"]
FC = ["symbol","available","created_at","target_time","reference_price","price_source","predicted_price","predicted_return_pct","model","model_version","forecast_age_hours","resolved"]
MD = ["symbol","available","model","version","trained_at","unseen_hours_scored","mae","naive_mae","skill_vs_naive_pct","direction_accuracy","grade","score_basis","live_accuracy","history_runs"]
LA = ["checked_predictions","direction_right_rate","beats_coin_flip","verdict","mean_abs_error_pct"]
CANDLE = ["time","open","high","low","close","volume","sma20","sma50","bb_up","bb_lo","rsi14","macd","macd_signal","macd_hist"]
CR = ["symbol","interval","source","note","last_candle_time","data_age_hours","fetched_at","regime","candles"]
PF = ["start_balance","currency","open_positions","trades","equity","cash","buy_hold_equity","max_drawdown_pct","current_drawdown_pct","last_update","realized_pnl","fees_paid","win_rate_pct","statistically_conclusive","note"]
st, h = get("/health", ""); print("/health", st); need("Health", h, ["status","worker_last_success","worker_age_hours","max_age_hours","tracked_coins","alert_channels","coinswitch_configured"])
print("no token ->", get("/api/signals", "")[0], "| wrong token ->", get("/api/signals", "x")[0])
st, f = get("/api/forecasts"); print("/api/forecasts", st); [need("Forecast "+x["symbol"], x, FC) for x in f]
st, s = get("/api/signals"); print("/api/signals", st); [need("Signal "+x["symbol"]+" "+str(x["signal"]), x, SIG) for x in s]
st, m = get("/api/models"); print("/api/models", st); [(need("Model "+x["symbol"], x, MD), need("  LiveAccuracy", x["live_accuracy"], LA)) for x in m]
st, c = get("/api/coins/BTCUSDT"); print("/api/coins/BTCUSDT", st); need("CoinAnalysis", c, ["symbol","forecast","signal","model","disclaimer"])
print("/api/coins/DOGEUSDT ->", get("/api/coins/DOGEUSDT")[0])
st, b = get("/api/backtest"); print("/api/backtest", st, "available =", b["available"])
st, p = get("/api/paper/portfolio"); print("/api/paper/portfolio", st); need("PaperPortfolio", p, PF); print("   currency =", p["currency"], "| trades =", p["trades"], "| note =", p["note"])
for path in ("/api/paper/trades", "/api/paper/equity", "/api/alerts/config", "/api/alerts/recent"):
    st, x = get(path); print(path, st, "->", type(x).__name__, len(x) if hasattr(x, "__len__") else "")
st, e = get("/api/paper/equity"); 
if e: need("EquityPoint", e[0], ["ts","cash","equity","bh_equity","open_positions"])
st, a = get("/api/alerts/config"); need("AlertConfig", a, ["channels","drawdown_alert_pct","signal_alerts","editable_via_api"])
st, r = get("/api/alerts/recent"); print("   recent alert line sample:", (r[-1][:110] if r else None))
st, k = get("/api/coins/BTCUSDT/candles?limit=300"); print("/candles", st)
if st == 200: need("Candles", k, CR); need("  Candle", k["candles"][-1], CANDLE)
print("\nCONTRACT PROBLEMS:", bad or "none")
sys.exit(1 if bad else 0)
