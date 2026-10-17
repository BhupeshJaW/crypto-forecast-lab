import os, glob, sqlite3
from datetime import datetime, timezone
import config

def run():
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    dst = os.path.join(config.BACKUP_DIR, f"tracker_{datetime.now(timezone.utc):%Y%m%d_%H%M}.db")
    src, out = sqlite3.connect(config.DB_PATH), sqlite3.connect(dst)
    with out:
        src.backup(out)               # safe even while the dashboard is reading
    src.close(); out.close()
    for old in sorted(glob.glob(os.path.join(config.BACKUP_DIR, "tracker_*.db")))[:-config.BACKUPS_KEEP]:
        os.remove(old)
    return dst

if __name__ == "__main__":
    print("Backup written:", run())
