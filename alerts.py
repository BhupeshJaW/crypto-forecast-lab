"""Telegram + email alerts. Never raises, never logs secrets."""
import os, smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
import requests
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass
import db
from logger import get_logger
log = get_logger()

def channels():
    ch = []
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        ch.append("telegram")
    if all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO")):
        ch.append("email")
    return ch

def _telegram(text):
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000]}, timeout=15)
    r.raise_for_status()

def _email(subject, text):
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subject, os.environ["SMTP_USER"], os.environ["ALERT_EMAIL_TO"]
    m.set_content(text)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(m)

def notify(text, subject="Crypto predictor"):
    sent = []
    for c in channels():
        try:
            _telegram(text) if c == "telegram" else _email(subject, text)
            sent.append(c)
        except Exception as e:          # only the exception TYPE is logged: messages can contain the bot token
            log.warning(f"alert via {c} failed: {type(e).__name__}")
    log.info(f"[alert] {text[:150].replace(chr(10), ' | ')} -> {sent or 'no channel configured'}")
    return sent

def notify_once(key, text, cooldown_hours=6, subject="Crypto predictor"):
    """Send at most once per cooldown (so a broken server doesn't spam you)."""
    last = db.kv_get(f"alert_{key}")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < cooldown_hours * 3600:
        return []
    db.kv_set(f"alert_{key}", datetime.now(timezone.utc).isoformat())
    return notify(text, subject)
