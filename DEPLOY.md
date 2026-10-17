# Running it 24/7

The worker must run every hour without gaps. A laptop that sleeps will miss hours (the tracker still
resolves old predictions after a gap, but paper trading skips the missed hours).

## 1. Set up alerts first (5 minutes)
1. Telegram: message @BotFather, send /newbot, copy the token. Message your new bot once, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat` `id`.
2. `cp .env.example .env`, fill TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Never share `.env`.
3. Run `streamlit run app.py` and press "Send test alert" in the sidebar.
Optional: email (use a Gmail App Password), DASHBOARD_PASSWORD, and a free https://healthchecks.io check
(put its URL in HEALTHCHECKS_URL). Healthchecks.io is the one thing that can tell you the whole machine
died, because a dead server cannot message you itself.

## 2. Where to run it
- **Easiest:** your own PC/Mac, left on, with sleep disabled. Fine for testing.
- **Better:** a small always-on machine: Raspberry Pi, old laptop, or a cheap cloud VPS (1 GB RAM is enough).
  Some cloud IPs are blocked by Binance. If you see fetch errors, set `BINANCE_BASE=https://data-api.binance.vision`
  in `.env` (public market-data mirror). If that fails too, try a VPS in another region.

## 3a. Docker (recommended)
    docker compose up -d --build
    docker compose logs -f worker
Dashboard is bound to localhost only. From your own computer view it with an SSH tunnel:
    ssh -L 8501:localhost:8501 user@your-server      then open http://localhost:8501
Don't open port 8501 to the internet without DASHBOARD_PASSWORD and HTTPS in front of it.

## 3b. Without Docker (systemd, Linux)
    sudo mkdir -p /opt/crypto_predictor && sudo chown $USER /opt/crypto_predictor
    # copy the project there, then:
    cd /opt/crypto_predictor && python3 -m venv venv && venv/bin/pip install -r requirements.txt
    sudo cp deploy/*.service /etc/systemd/system/   # edit User= if not "ubuntu"
    sudo systemctl daemon-reload && sudo systemctl enable --now crypto-worker crypto-dashboard
    journalctl -u crypto-worker -f

## 3c. Cron instead of a loop
    1 * * * * cd /opt/crypto_predictor && venv/bin/python scheduler.py --once
    */30 * * * * cd /opt/crypto_predictor && venv/bin/python healthcheck.py --alert

## What you will receive
Buy/sell alerts from the paper account, model-type switches, a daily summary, a drawdown warning
(config.ALERT_DRAWDOWN), failure alerts after 3 bad cycles in a row, and a recovery message.
Backups of the database go to `backups/` once a day (last 14 kept). Copy that folder somewhere else occasionally.

## Updating
Docker: replace the code files (keep data/, models/, .env), then `docker compose up -d --build`.
