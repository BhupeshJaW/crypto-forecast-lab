"""FastAPI layer. Start:  uvicorn api:app --host 127.0.0.1 --port 8000     Docs: http://127.0.0.1:8000/docs
Read-only: this API cannot place orders, change settings, or return any secret.
Set API_TOKEN in .env to require 'Authorization: Bearer <token>' (do this before exposing it beyond your machine)."""
import hmac, os, time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import services
from logger import get_logger
log = get_logger()

class Health(BaseModel):
    status: str
    worker_last_success: Optional[str] = None
    worker_age_hours: Optional[float] = None
    max_age_hours: float
    tracked_coins: int
    alert_channels: List[str]
    coinswitch_configured: bool

class AlertConfig(BaseModel):
    channels: List[str]
    drawdown_alert_pct: float
    signal_alerts: str
    editable_via_api: bool

class ErrorOut(BaseModel):
    detail: str

app = FastAPI(title="Crypto Predictor API", version="0.1.0",
              description="Read-only forecasts, BUY/SELL/HOLD/NO TRADE signals and paper-trading stats. "
                          "Learning project, not financial advice. Prices are Binance USDT references, not CoinSwitch quotes.")
app.add_middleware(CORSMiddleware, allow_origins=[o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o],
                   allow_methods=["GET"], allow_headers=["Authorization"])

# ---- simple in-memory rate limit (per client IP). Use a reverse proxy / Redis if you run several workers. ----
_HITS = defaultdict(deque)
LIMIT, WINDOW = int(os.getenv("API_RATE_LIMIT_PER_MIN", "120")), 60

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "?"
    q, now = _HITS[ip], time.time()
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= LIMIT:
        return JSONResponse({"detail": "Too many requests"}, status_code=429)
    q.append(now)
    return await call_next(request)

def _token_matches(supplied: str, token: str) -> bool:
    """Constant-time comparison on bytes. hmac.compare_digest raises TypeError for non-ASCII str, which a crafted
    header could use to turn a 401 into a 500. Starlette decodes headers as latin-1, so latin-1 gives the raw bytes."""
    return hmac.compare_digest(supplied.encode("latin-1", "replace"), token.encode("utf-8"))

def require_auth(authorization: Optional[str] = Header(default=None)):
    token = os.getenv("API_TOKEN")
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer ") or not _token_matches(authorization[7:], token):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

def _coin(symbol: str) -> str:
    symbol = symbol.upper()
    try:
        return services.check_symbol(symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {symbol}")

def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except HTTPException:
        raise
    except Exception as e:                       # never leak internals or secrets in error text
        log.exception(f"api error in {fn.__name__}: {type(e).__name__}")
        raise HTTPException(status_code=502 if "fetch" in fn.__name__ or fn.__name__ == "candles" else 500,
                            detail=f"{fn.__name__} failed ({type(e).__name__})")

@app.get("/health", response_model=Health, tags=["system"])
def health():
    """Unauthenticated liveness + worker freshness (no secrets)."""
    return services.health()

@app.get("/api/forecasts", tags=["forecasts"], dependencies=[Depends(require_auth)])
def forecasts() -> List[Dict[str, Any]]:
    """Latest next-hour forecast for every tracked coin, with age and price source."""
    return _safe(services.latest_forecasts)

@app.get("/api/signals", tags=["signals"], dependencies=[Depends(require_auth)])
def signals() -> List[Dict[str, Any]]:
    """Latest BUY / SELL / HOLD / NO_TRADE signal per coin, with blockers, costs, stop, target and expiry."""
    return _safe(services.latest_signals)

@app.get("/api/coins/{symbol}", tags=["coins"], dependencies=[Depends(require_auth)])
def coin(symbol: str) -> Dict[str, Any]:
    """Forecast + signal + model grade + live forecast accuracy for one coin."""
    return _safe(services.coin_analysis, _coin(symbol))

@app.get("/api/coins/{symbol}/candles", tags=["coins"], dependencies=[Depends(require_auth)])
def coin_candles(symbol: str, limit: int = Query(300, ge=50, le=1000)) -> Dict[str, Any]:
    """Closed hourly candles with SMA, Bollinger, RSI, MACD. Includes source, age and a not-live note."""
    return _safe(services.candles, _coin(symbol), limit)

@app.get("/api/models", tags=["models"], dependencies=[Depends(require_auth)])
def models() -> List[Dict[str, Any]]:
    """Model grade from unseen-data scoring plus live forecast accuracy and sample sizes."""
    return _safe(services.model_performance)

@app.get("/api/backtest", tags=["backtest"], dependencies=[Depends(require_auth)])
def backtest() -> Dict[str, Any]:
    """Last saved backtest table; rows with fewer than 30 trades are flagged inconclusive."""
    return _safe(services.backtest_report)

@app.get("/api/paper/portfolio", tags=["paper"], dependencies=[Depends(require_auth)])
def paper_portfolio() -> Dict[str, Any]:
    return _safe(services.paper_portfolio)

@app.get("/api/paper/trades", tags=["paper"], dependencies=[Depends(require_auth)])
def paper_trades(limit: int = Query(200, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return _safe(services.paper_trades, limit)

@app.get("/api/paper/equity", tags=["paper"], dependencies=[Depends(require_auth)])
def paper_equity(limit: int = Query(2000, ge=10, le=10000)) -> List[Dict[str, Any]]:
    return _safe(services.paper_equity, limit)

@app.get("/api/alerts/config", response_model=AlertConfig, tags=["alerts"], dependencies=[Depends(require_auth)])
def alert_config():
    """Which channels are active. Read-only; secrets are never returned."""
    return services.alert_config()

@app.get("/api/alerts/recent", tags=["alerts"], dependencies=[Depends(require_auth)])
def alerts_recent(limit: int = Query(50, ge=1, le=200)) -> List[str]:
    """Recent alert, error and failed-fetch lines from the log (secrets are never logged)."""
    return _safe(services.recent_alerts, limit)
