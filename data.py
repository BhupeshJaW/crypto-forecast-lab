import os, requests, pandas as pd
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass
import config
from logger import get_logger
log = get_logger()

COLS = ["ts", "open", "high", "low", "close", "volume", "close_ts", "qvol", "trades", "taker_buy", "tq", "_"]

def _why(e):
    """Short, safe failure reason for logs: exception type and HTTP status only (never the URL or response body)."""
    code = getattr(getattr(e, "response", None), "status_code", None)
    return type(e).__name__ + (f", HTTP {code}" if code else "")

def _binance(symbol, n=None):
    """Pages backwards (Binance returns max 1000 candles per request) until n (default config.CANDLES) are collected."""
    n = n or config.CANDLES
    base = os.getenv("BINANCE_BASE", "https://api.binance.com")
    rows, end = [], None
    while len(rows) < n:
        want = min(1000, n - len(rows))
        params = {"symbol": symbol, "interval": config.INTERVAL, "limit": want}
        if end is not None:
            params["endTime"] = end
        r = requests.get(base + "/api/v3/klines", params=params, timeout=20)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows = batch + rows
        end = batch[0][0] - 1
        if len(batch) < want:
            break
    df = pd.DataFrame(rows, columns=COLS).drop_duplicates("ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    keep = ["ts", "open", "high", "low", "close", "volume", "trades", "taker_buy"]
    return df[keep].astype({k: float for k in keep[1:]})

def _coingecko(symbol):   # close-only fallback
    r = requests.get(f"https://api.coingecko.com/api/v3/coins/{config.COINGECKO_IDS[symbol]}/market_chart",
        params={"vs_currency": "usd", "days": 90}, timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["prices"], columns=["ts", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.floor("h")
    return df.drop_duplicates("ts").reset_index(drop=True)

def fetch_prices(symbol, n=None):
    """Closed hourly candles only (drops the in-progress one). n = how many candles to request (default config.CANDLES;
    the dashboard API asks for far fewer than the model needs).
    The result carries df.attrs["source"] = "binance" or "coingecko". The CoinGecko fallback has no volume,
    so the models must NOT predict from it (pipeline.run_symbol refuses)."""
    src = "binance"
    try:
        df = _binance(symbol, n)
    except Exception as e:
        log.warning(f"[{symbol}] binance fetch failed ({_why(e)}); using coingecko fallback (close-only, no volume)")
        src, df = "coingecko", _coingecko(symbol)
    out = df.sort_values("ts").iloc[:-1].reset_index(drop=True)
    out.attrs["source"] = src
    return out

def data_age_hours(df, now=None):
    """Hours since the newest candle CLOSED (a 1h candle stamped 10:00 closes at 11:00)."""
    now = now or pd.Timestamp.now(tz="UTC")
    closed_at = pd.Timestamp(df["ts"].iloc[-1]) + pd.Timedelta(hours=1)
    return (now - closed_at).total_seconds() / 3600
