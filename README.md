# Crypto Predictor

An open-source research tool that forecasts the next-hour return of a few crypto coins, checks its own
forecasts against what actually happened, and trades a **simulated** (paper) portfolio on the results.
It never places real orders.

> **Disclaimer.** This is an educational and research project, not financial advice. Short-horizon crypto
> prediction is very hard; expect results close to "price stays the same". Nothing here is a recommendation
> to buy or sell, and no real-money trading is implemented on purpose.

## How it works

Every hour the worker:

1. fetches hourly candles from Binance (CoinGecko as a close-only fallback) and checks the data is fresh;
2. resolves last hour's forecast against the real price and logs the error;
3. retrains every 24 hours: six candidate models (ridge, random forest, extra trees, gradient boosting,
   histogram gradient boosting and a voting ensemble) are compared with walk-forward validation, and the live
   model only switches when it is at least `SWITCH_MARGIN` better;
4. scores the chosen model on a held-out slice of history it never trained on, and assigns a trust grade
   (high / medium / low);
5. predicts the next hour and turns it into a time-limited **BUY / SELL / HOLD / NO TRADE** signal that accounts
   for fees, slippage, volatility regime, data age and reward-to-risk;
6. feeds the signals to a paper-trading account with fees, slippage, optional TDS, stop-loss, take-profit,
   exposure caps and a daily-loss halt;
7. sends alerts (Telegram / email), writes a heartbeat, and backs up the database daily.

Features include returns, multi-hour momentum, RSI, MACD, Bollinger bands, volume, taker-buy ratio,
volatility regime, distance from moving averages and highs/lows, time of day, and BTC as a cross-coin signal.

## Components

| Part | Run with | Purpose |
|---|---|---|
| Worker | `python scheduler.py` | Hourly loop (`--once` for cron) |
| Streamlit dashboard | `streamlit run app.py` | Forecasts, model leaderboard, paper trading |
| REST API | `uvicorn api:app` | Read-only JSON API (docs at `/docs`) |
| React dashboard | `cd frontend && npm run dev` | Charts, signals, portfolio, analytics |
| Backtest | `python backtest.py` | Walk-forward replay of the last ~600 hours, with and without fees |
| Paper reset | `python reset_paper.py` | Restart the simulated account |

## Quick start

Requires Python 3.12+ (numpy 2.5) and, for the React dashboard, Node 20+.

    git clone https://github.com/<your-username>/crypto-predictor.git
    cd crypto-predictor
    python -m venv venv
    source venv/bin/activate            # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env                # optional: alerts, API token, CoinSwitch keys

    python pipeline.py                  # run one cycle to test
    python scheduler.py                 # terminal 1: hourly worker
    streamlit run app.py                # terminal 2: dashboard

React dashboard and API (details in [`frontend/README.md`](frontend/README.md)):

    uvicorn api:app --host 127.0.0.1 --port 8000
    cd frontend && npm ci && npm run dev    # http://127.0.0.1:5173

Docker: `docker compose up -d --build` starts the worker, the Streamlit dashboard and the API, all bound to
localhost. See [`DEPLOY.md`](DEPLOY.md) for running it 24/7.

## Configuration

Trading, model and safety settings live in [`config.py`](config.py) (coins, thresholds, fees, stop-loss,
retrain interval, data-safety guards). Secrets and deployment options go in `.env`
(see [`.env.example`](.env.example)): `TELEGRAM_BOT_TOKEN`, `SMTP_*`, `DASHBOARD_PASSWORD`, `API_TOKEN`,
`CORS_ORIGINS`, `HEALTHCHECKS_URL`, `BINANCE_BASE`, `COINSWITCH_*`. Never commit `.env`.

## CoinSwitch (optional)

`coinswitch_client.py` can log CoinSwitch INR quotes next to the Binance data. It only sends allow-listed
GET requests; there is no order, cancel or transfer code, and tests enforce this. Generate keys in
CoinSwitch PRO > Profile > API Trading, and use keys you do not use anywhere else. The response shape and
exchange name are not guaranteed by CoinSwitch; if quotes do not appear, check `logs/app.log`.

## API

All endpoints are `GET`. With `API_TOKEN` set, send `Authorization: Bearer <token>` (`/health` stays open).

`/health`, `/api/forecasts`, `/api/signals`, `/api/coins/{symbol}`, `/api/coins/{symbol}/candles`,
`/api/models`, `/api/backtest`, `/api/paper/portfolio`, `/api/paper/trades`, `/api/paper/equity`,
`/api/alerts/config`, `/api/alerts/recent`

## Tests

    python -m unittest discover -s tests -t . -v
    cd frontend && npm test && npm run typecheck

## Reading the results

"Skill vs naive" above zero means the model beat "price stays the same" in validation. Expect values near
zero. Direction accuracy consistently above roughly 52-53% over hundreds of resolved predictions would be
notable. The dashboards say "too early" until 30 predictions have been checked.

## Project layout

    scheduler.py, pipeline.py   hourly loop and one cycle
    data.py, model.py           candles, features, training, validation
    signals.py, paper.py        signal engine, paper-trading engine
    db.py, services.py          SQLite storage, read-side logic
    api.py                      FastAPI layer
    app.py                      Streamlit dashboard
    alerts.py, reports.py, backup.py, healthcheck.py
    coinswitch_client.py        read-only CoinSwitch client
    frontend/                   React + TypeScript dashboard
    tests/, tools/              test suite, API-contract checker
    deploy/                     systemd units

## Contributing

Issues and pull requests are welcome. Please run the test suite first, and do not add real-order trading
code to this repository.

## License

[MIT](LICENSE)
