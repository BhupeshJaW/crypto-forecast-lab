import sqlite3, os
from contextlib import closing
import pandas as pd
import config

def conn():
    """One short-lived connection per call. WAL + busy timeout stop 'database is locked' errors when the
    worker and the dashboard touch the file at the same time."""
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
        created_at TEXT, target_time TEXT, base_price REAL,
        predicted_price REAL, predicted_return REAL, model_version TEXT, model_name TEXT,
        actual_price REAL, abs_error REAL, pct_error REAL,
        direction_correct INTEGER, resolved INTEGER DEFAULT 0,
        UNIQUE(symbol, target_time))""")
    c.execute("""CREATE TABLE IF NOT EXISTS model_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, symbol TEXT, version TEXT,
        candidate TEXT, cv_mae REAL, baseline_mae REAL, champion_cv_mae REAL,
        cv_dir_acc REAL, switched INTEGER, note TEXT)""")
    try:        # migration: how many unseen hours the honest score is based on (old rows stay NULL)
        c.execute("ALTER TABLE model_runs ADD COLUMN holdout_n INTEGER")
    except sqlite3.OperationalError:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS candidate_scores(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, symbol TEXT, candidate TEXT,
        cv_mae REAL, cv_dir_acc REAL, baseline_mae REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS coinswitch_ticks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, pair TEXT, price REAL, raw TEXT)""")
    for col, typ in (("bid", "REAL"), ("ask", "REAL"), ("exchange", "TEXT")):       # columns added after the first release; migrate older databases
        try:
            c.execute(f"ALTER TABLE coinswitch_ticks ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    c.execute("""CREATE TABLE IF NOT EXISTS paper_state(key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS paper_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, entry_time TEXT, exit_time TEXT,
        entry_price REAL, exit_price REAL, qty REAL, fees REAL, pnl REAL, pnl_pct REAL,
        reason TEXT, hold_hours REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS paper_equity(
        ts TEXT PRIMARY KEY, cash REAL, equity REAL, bh_equity REAL, open_positions INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, target_time TEXT, created_at TEXT,
        signal TEXT, payload TEXT, UNIQUE(symbol, target_time))""")
    return c

def _exec(sql, args=()):
    with closing(conn()) as c:
        with c:
            return c.execute(sql, args).rowcount

def add_prediction(row):
    _exec("""INSERT OR IGNORE INTO predictions
        (symbol,created_at,target_time,base_price,predicted_price,predicted_return,model_version,model_name)
        VALUES(?,?,?,?,?,?,?,?)""", row)

def unresolved(symbol):
    with closing(conn()) as c:
        return pd.read_sql("SELECT * FROM predictions WHERE resolved=0 AND symbol=?", c, params=(symbol,))

def resolve(pred_id, actual, abs_err, pct_err, ok):
    _exec("""UPDATE predictions SET actual_price=?,abs_error=?,pct_error=?,direction_correct=?,resolved=1
        WHERE id=?""", (actual, abs_err, pct_err, ok, pred_id))

def add_model_run(row):
    """row = (run_at, symbol, version, candidate, mae, baseline_mae, champion_mae, dir_acc, switched, note[, holdout_n])"""
    row = tuple(row) + (None,) * (11 - len(row))
    _exec("""INSERT INTO model_runs(run_at,symbol,version,candidate,cv_mae,baseline_mae,
        champion_cv_mae,cv_dir_acc,switched,note,holdout_n) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", row)

def add_candidate_score(row):
    _exec("""INSERT INTO candidate_scores(run_at,symbol,candidate,cv_mae,cv_dir_acc,baseline_mae)
        VALUES(?,?,?,?,?,?)""", row)

def add_tick(row):
    """row = (ts, symbol, pair, last_price, raw_json, bid, ask, exchange). A 5-tuple (older callers) is still accepted."""
    row = tuple(row) + (None,) * (8 - len(row))
    _exec("INSERT INTO coinswitch_ticks(ts,symbol,pair,price,raw,bid,ask,exchange) VALUES(?,?,?,?,?,?,?,?)", row)

def add_signal(symbol, target_time, created_at, signal, payload_json):
    """Returns True only the first time a signal is stored for (symbol, target_time) -> use it to avoid duplicate alerts."""
    return _exec("INSERT OR IGNORE INTO signals(symbol,target_time,created_at,signal,payload) VALUES(?,?,?,?,?)",
                 (symbol, target_time, created_at, signal, payload_json)) == 1

def read(table):
    with closing(conn()) as c:
        return pd.read_sql(f"SELECT * FROM {table}", c)

def kv_get(key):
    with closing(conn()) as c:
        r = c.execute("SELECT value FROM paper_state WHERE key=?", (key,)).fetchone()
    return r[0] if r else None

def kv_set(key, value):
    _exec("INSERT OR REPLACE INTO paper_state(key,value) VALUES(?,?)", (key, value))

def add_paper_trade(t):
    _exec("""INSERT INTO paper_trades(symbol,entry_time,exit_time,entry_price,exit_price,qty,fees,pnl,pnl_pct,reason,hold_hours)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (t["symbol"], t["entry_time"], t["exit_time"], t["entry_price"],
        t["exit_price"], t["qty"], t["fees"], t["pnl"], t["pnl_pct"], t["reason"], t["hold_hours"]))

def add_equity(ts, cash, equity, bh, n_open):
    _exec("INSERT OR REPLACE INTO paper_equity VALUES(?,?,?,?,?)", (ts, cash, equity, bh, n_open))

def reset_paper():
    with closing(conn()) as c:
        with c:
            for t in ("paper_state", "paper_trades", "paper_equity"):
                c.execute(f"DELETE FROM {t}")
