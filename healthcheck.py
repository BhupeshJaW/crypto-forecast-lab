"""Exit 0 if the worker completed a cycle recently, else 1. Used by Docker HEALTHCHECK; run with --alert from cron too."""
import sys
from datetime import datetime, timezone
import config, db, alerts

last = db.kv_get("last_success")
age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600 if last else None
if age is None or age > config.HEALTH_MAX_AGE_HOURS:
    msg = f"UNHEALTHY: last successful cycle {'never' if age is None else f'{age:.1f}h ago'}"
    print(msg)
    if "--alert" in sys.argv:
        alerts.notify_once("unhealthy", "⚠️ " + msg)
    sys.exit(1)
print(f"healthy: last successful cycle {age:.1f}h ago")
