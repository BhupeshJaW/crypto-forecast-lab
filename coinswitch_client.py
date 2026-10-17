"""READ-ONLY CoinSwitch PRO spot client for market data.

Written against the official docs (https://api-trading.coinswitch.co, checked 2026-10-17):
  - signing: Ed25519 over  METHOD + url-decoded path-with-query + epoch_ms ; headers X-AUTH-APIKEY / X-AUTH-SIGNATURE / X-AUTH-EPOCH
  - base URL https://coinswitch.co ; Spot v2 ; INR pairs live on exchange "coinswitchx", USDT pairs on "c2c1"/"c2c2"
  - these endpoints need a signed request even for market data, so a key pair is required
SAFETY: this module can only send GET requests to the allow-list below. There is NO order, cancel, transfer or account
endpoint, and tests fail if one is added. The docs describe no read-only key scope, so treat the key as able to trade:
keep it out of git, chat and logs. Error messages never contain keys, signatures or URLs.
"""
import os, time, random, urllib.parse
import pandas as pd, requests
from logger import get_logger
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass
log = get_logger()

BASE_URL = "https://coinswitch.co"
INR_EXCHANGE = "coinswitchx"
PATH_COINS = "/trade/api/v2/coins"
PATH_FEE = "/trade/api/v2/tradingFee"
PATH_CANDLES = "/trade/api/v2/candles"
PATH_TICKER = "/trade/api/v2/24hr/ticker"
ALLOWED_GET_PATHS = frozenset({PATH_COINS, PATH_FEE, PATH_CANDLES, PATH_TICKER})
TIMEOUT = 15
CANDLE_CHUNK = 1000        # candles per request when paging history (the docs publish no per-request cap: assumption)
QUOTE_STALE_SECONDS = 600


class CoinSwitchError(Exception):
    """kind: config | auth | rate_limited | network | server | bad_request | unexpected_response"""
    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind, self.status = kind, status


def enabled():
    return bool(os.getenv("COINSWITCH_API_KEY") and os.getenv("COINSWITCH_SECRET_KEY"))

def exchange_default():
    return (os.getenv("COINSWITCH_EXCHANGE") or INR_EXCHANGE).strip()

def _now_ms():
    return int(time.time() * 1000)

def _sleep(seconds):
    time.sleep(seconds)


def _sign(method, path, params=None):
    """Exactly the documented reference client. Returns (headers, url_decoded_path_with_query)."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    method = method.upper()
    if params:
        path = path + ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    decoded = urllib.parse.unquote_plus(path)
    epoch = str(_now_ms())
    try:
        key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(os.environ["COINSWITCH_SECRET_KEY"]))
        api_key = os.environ["COINSWITCH_API_KEY"]
    except (KeyError, ValueError):
        raise CoinSwitchError("config", "COINSWITCH_API_KEY / COINSWITCH_SECRET_KEY missing or not valid hex") from None
    signature = key.sign((method + decoded + epoch).encode("utf-8")).hex()
    return {"Content-Type": "application/json", "X-AUTH-APIKEY": api_key,
            "X-AUTH-SIGNATURE": signature, "X-AUTH-EPOCH": epoch}, decoded


def _get(path, params=None):
    """The only network call in this module. GET only, allow-listed paths only, one retry for network/5xx errors."""
    if path not in ALLOWED_GET_PATHS:
        raise ValueError(f"path not allowed: {path}")
    if not enabled():
        raise CoinSwitchError("config", "CoinSwitch keys are not configured")
    last = None
    for attempt in range(2):
        headers, decoded = _sign("GET", path, params)       # fresh epoch on every attempt
        try:
            r = requests.get(BASE_URL + decoded, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = CoinSwitchError("network", f"request failed ({type(e).__name__})")
        else:
            if r.status_code == 429:
                raise CoinSwitchError("rate_limited", "HTTP 429: rate limit exceeded, back off", 429)
            if r.status_code in (401, 403):
                raise CoinSwitchError("auth", "HTTP %d: invalid access (check API key, secret and PC clock)" % r.status_code, r.status_code)
            if r.status_code >= 500:
                last = CoinSwitchError("server", f"HTTP {r.status_code}: CoinSwitch server error", r.status_code)
            elif r.status_code >= 400:
                try: msg = str(r.json().get("message", ""))[:120]
                except Exception: msg = ""
                raise CoinSwitchError("bad_request", f"HTTP {r.status_code}: {msg}".strip(), r.status_code)
            else:
                try: js = r.json()
                except ValueError:
                    raise CoinSwitchError("unexpected_response", "response is not JSON") from None
                if not isinstance(js, dict) or "data" not in js:
                    raise CoinSwitchError("unexpected_response", "response has no 'data' field")
                return js["data"]
        if attempt == 0:
            _sleep(1.0 + random.random() * 0.5)
    raise last


def _num(row, key, positive=False):
    try:
        v = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")) or (positive and v <= 0):
        return None
    return v


def active_coins(exchange=None):
    ex = exchange or exchange_default()
    data = _get(PATH_COINS, {"exchange": ex})
    if not isinstance(data, dict) or not isinstance(data.get(ex), list):
        raise CoinSwitchError("unexpected_response", "coins response has an unexpected shape")
    return [str(s) for s in data[ex]]

_LISTED = {}
def is_listed(symbol, exchange=None, ttl=6 * 3600):
    """True only if the exchange's own symbol list contains `symbol`. Cached; raises on API errors (never guesses)."""
    ex = exchange or exchange_default()
    hit = _LISTED.get(ex)
    if not hit or time.time() - hit[0] > ttl:
        _LISTED[ex] = hit = (time.time(), set(active_coins(ex)))
    return symbol in hit[1]


def ticker(symbol, exchange=None):
    """24h ticker for one symbol, e.g. 'BTC/INR'. Returns None if the symbol is absent. bid/ask are None unless both are
    positive and not crossed, so a bad quote can never produce a fake spread."""
    ex = exchange or exchange_default()
    data = _get(PATH_TICKER, {"exchange": ex, "symbol": symbol})
    row = data.get(symbol) if isinstance(data, dict) else None
    if not isinstance(row, dict):
        return None
    last = _num(row, "lastPrice", positive=True)
    if last is None:
        raise CoinSwitchError("unexpected_response", "ticker has no valid lastPrice")
    bid, ask = _num(row, "bidPrice", True), _num(row, "askPrice", True)
    if bid is None or ask is None or ask < bid:
        bid = ask = None
    at = row.get("at")
    at = int(at) if isinstance(at, (int, float)) and at > 0 else None
    mid = (bid + ask) / 2 if bid else None
    return {"symbol": symbol, "exchange": ex, "last": last, "bid": bid, "ask": ask,
            "spread": (ask - bid) / mid if mid else None,
            "open": _num(row, "openPrice"), "high": _num(row, "highPrice"), "low": _num(row, "lowPrice"),
            "base_volume": _num(row, "baseVolume"), "quote_volume": _num(row, "quoteVolume"),
            "pct_change_24h": _num(row, "percentageChange"), "at_ms": at,
            "age_seconds": (_now_ms() - at) / 1000 if at else None, "source": "coinswitch_ticker"}


def trading_fee(exchange=None):
    """{BASE: {'maker','taker' (after discount), 'maker_base','taker_base'}} as fractions (0.001 = 0.1%).
    Fee schedules are account-specific, so never reuse these numbers for someone else's account."""
    ex = exchange or exchange_default()
    data = _get(PATH_FEE, {"exchange": ex})
    block = data.get(ex) if isinstance(data, dict) else None
    if not isinstance(block, dict):
        raise CoinSwitchError("unexpected_response", "tradingFee response has an unexpected shape")
    out = {}
    for base, f in block.items():
        vals = [_num(f, k) for k in ("maker_fee_after_discount", "taker_fee_after_discount", "maker_fee", "taker_fee")] \
            if isinstance(f, dict) else [None]
        if any(v is None or not 0 <= v < 1 for v in vals):
            continue                                        # skip malformed rows instead of trusting them
        out[str(base)] = {"maker": vals[0], "taker": vals[1], "maker_base": vals[2], "taker_base": vals[3]}
    if not out:
        raise CoinSwitchError("unexpected_response", "tradingFee response has no usable rows")
    return out


def candles(symbol, interval_minutes, start_ms, end_ms, exchange=None):
    """Closed candles in [start_ms, end_ms] as a DataFrame (ts UTC, open, high, low, close, volume, close_time).
    The still-open candle is dropped. attrs['source'] = 'coinswitch_inr' for */INR symbols, else 'coinswitch'."""
    ex = exchange or exchange_default()
    data = _get(PATH_CANDLES, {"exchange": ex, "symbol": symbol, "interval": int(interval_minutes),
                               "start_time": int(start_ms), "end_time": int(end_ms)})
    if not isinstance(data, list):
        raise CoinSwitchError("unexpected_response", "candles response is not a list")
    rows, bad, now = [], 0, _now_ms()
    for c in data:
        try:
            o, h, l, cl, v = (float(c[k]) for k in ("o", "h", "l", "c", "volume"))
            st, ct = int(c["start_time"]), int(c["close_time"])
        except (KeyError, TypeError, ValueError):
            bad += 1; continue
        if min(o, h, l, cl) <= 0 or h < l or v < 0 or ct > now:
            bad += (0 if ct > now else 1); continue         # an open candle is dropped silently; broken ones are counted
        rows.append((pd.Timestamp(st, unit="ms", tz="UTC"), o, h, l, cl, v, ct))
    if bad:
        log.warning(f"[{symbol}] CoinSwitch candles: ignored {bad} malformed rows")
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "close_time"])
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df.attrs["source"] = "coinswitch_inr" if symbol.upper().endswith("/INR") else "coinswitch"
    return df


def candles_history(symbol, hours, interval_minutes=60, exchange=None, chunk=CANDLE_CHUNK):
    """Last `hours` hours of closed candles, fetched in chunks of `chunk` candles, oldest chunk last."""
    step = interval_minutes * 60_000
    end = _now_ms()
    start_all = end - int(hours) * 3_600_000
    frames, hi = [], end
    while hi > start_all:
        lo = max(start_all, hi - chunk * step)
        part = candles(symbol, interval_minutes, lo, hi, exchange)
        if len(part):
            frames.append(part)
        hi = lo
    if not frames:
        out = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "close_time"])
    else:
        out = pd.concat(frames).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out.attrs["source"] = "coinswitch_inr" if symbol.upper().endswith("/INR") else "coinswitch"
    return out
