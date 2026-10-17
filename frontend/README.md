# Frontend dashboard

React 18 + TypeScript + Vite + Tailwind 3 + TradingView Lightweight Charts 5.
Read-only client for the FastAPI backend. It cannot place orders: only GET requests exist in `src/services`.

Pages (hash routes): Overview `#/`, Coin analysis `#/coin/BTCUSDT`, Paper portfolio `#/portfolio`, Models and backtests `#/analytics`, Alerts `#/alerts`, Status `#/status`.

## Run (two terminals)

    # 1. backend, from the folder that holds api.py
    pip install -r requirements.txt
    uvicorn api:app --host 127.0.0.1 --port 8000

    # 2. frontend, from this folder
    npm install
    npm run dev          # http://127.0.0.1:5173  (Vite proxies /api and /health to the backend)

Other scripts: `npm test`, `npm run typecheck`, `npm run build`.

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `frontend/.env.local` | Empty in development (same origin via proxy). For a build served elsewhere, the backend URL; also add that origin to `CORS_ORIGINS` in the backend `.env`. |
| `DEV_API_PROXY_TARGET` | `frontend/.env.local` | Dev proxy target, default `http://127.0.0.1:8000`. |

**Never put the API token in any `VITE_*` variable**: those are embedded in the public bundle.
If the backend has `API_TOKEN` set, click **Token** in the header and paste it. It is held in memory
(optionally in sessionStorage for the tab), sent only as `Authorization: Bearer`, and never stored permanently.

## Layout

    src/types/      response types written from the real backend payloads
    src/services/   http client (timeouts, error mapping, no-token /health), auth token store, endpoint wrappers
    src/lib/        formatting (null/NaN safe), freshness, polling back-off, price-source labels
    src/hooks/      useApi (polling, pause when tab hidden, keeps last good data on error), useAuth
    src/components/ Layout, Panel, ErrorState, EmptyState, Skeleton, SourceBadge, FreshnessBadge, TokenGate
    src/charts/     CandleChart (candles, SMA, Bollinger, volume, RSI, MACD, entry/stop/target lines), EquityChart (equity, buy & hold, drawdown)
    src/pages/      Overview, Coin, Portfolio, Analytics, Alerts, Status

## What the pages show, and what they deliberately do not

- Only 1 h candles exist in the backend, so "range" selects how many to load; there are no other timeframes.
- The paper account is USDT, not INR; INR taxes (TDS) are not modelled. The Portfolio page says so.
- No price is ever labelled CoinSwitch INR: the backend has no verified CoinSwitch data yet.
- Signals show entry zone, stop, target, reward:risk, cost-adjusted edge, error band, reasons, blockers, and expiry. Expired signals are flagged.
- Backtest rows with fewer than 30 trades are marked inconclusive; the no-fees scenario is marked unrealistic.
- RMSE is not shown because the backend does not report it. 24 h change is derived from 1 h candles in the browser.
- Alert log lines carry no time zone, so they are shown as written and not converted.

## Checks

    npm ci && npm run typecheck && npm test && npm run build
