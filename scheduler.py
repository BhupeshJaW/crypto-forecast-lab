import time, signal, argparse, requests, os
from datetime import datetime, timezone, timedelta
import config, db, alerts, reports, backup
import pipeline
from logger import get_logger
log = get_logger()

STOP, FAILS = False, 0

def _stop(*_):
    global STOP
    STOP = True
    log.info("stop requested, finishing up...")

def housekeeping():
    now = datetime.now(timezone.utc)
    today = str(now.date())
    try:
        if db.kv_get("last_backup_date") != today:
            log.info(f"backup: {backup.run()}")
            db.kv_set("last_backup_date", today)
        if db.kv_get("last_summary_date") != today:
            alerts.notify(reports.daily_summary(), subject="Crypto predictor daily summary")
            db.kv_set("last_summary_date", today)
        E = db.read("paper_equity")
        if len(E) > 1:
            dd = E["equity"].iloc[-1] / E["equity"].max() - 1
            if dd <= -config.ALERT_DRAWDOWN:
                alerts.notify_once("drawdown", f"📉 Paper account is {dd*100:.1f}% below its peak "
                                   f"(equity {E['equity'].iloc[-1]:,.2f}).", cooldown_hours=24)
    except Exception as e:
        log.exception(f"housekeeping failed: {e}")

def cycle():
    global FAILS
    try:
        if pipeline.run_cycle() == 0:
            raise RuntimeError("no coin produced a prediction (data source down or blocked?)")
        db.kv_set("last_success", datetime.now(timezone.utc).isoformat())
        if FAILS >= 3:
            alerts.notify("✅ Worker recovered, cycles are succeeding again.")
        FAILS = 0
        url = os.getenv("HEALTHCHECKS_URL")
        if url:
            try: requests.get(url, timeout=10)
            except Exception: pass
    except Exception as e:
        FAILS += 1
        log.exception(f"cycle failed ({FAILS} in a row): {e}")
        if FAILS == 3:
            alerts.notify_once("cycle_fail", f"🚨 {FAILS} failed cycles in a row: {e}", cooldown_hours=6)
    housekeeping()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run one cycle and exit (for cron)")
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if a.once:
        cycle(); return
    alerts.notify(f"▶️ Worker started. Coins: {', '.join(config.SYMBOLS)}. Alert channels: {alerts.channels() or 'none'}")
    while not STOP:
        cycle()
        now = datetime.now(timezone.utc)
        nxt = (now + timedelta(hours=1)).replace(minute=1, second=0, microsecond=0)
        log.info(f"sleeping until {nxt.isoformat()}")
        while not STOP and datetime.now(timezone.utc) < nxt:
            time.sleep(10)
    log.info("worker stopped")

if __name__ == "__main__":
    main()
