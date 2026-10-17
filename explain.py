"""Turns the raw numbers into plain-English sentences for the dashboard and the daily alert.
No Streamlit in here, so it can be tested on its own."""
import math
import pandas as pd
import config

def _pct(x):
    return f"{x:.2f}%"

def direction_words(ret):
    a = abs(ret) * 100
    if a < 0.05:
        return "➡️ About flat"
    size = "slightly" if a < 0.15 else "a little" if a < 0.4 else "noticeably"
    return ("🔼 Up " if ret > 0 else "🔽 Down ") + size

def trust_words(run):
    """run: latest model_runs row (or None) -> (level, one sentence)."""
    if run is None:
        return "low", "No practice-test results yet."
    from model import confidence                      # imported here so tests of this file stay light
    n = run.get("holdout_n") if hasattr(run, "get") else None
    n = int(n) if n is not None and pd.notna(n) else None
    lvl = confidence(run["cv_mae"], run["baseline_mae"], run["cv_dir_acc"], n)
    skill = (1 - run["cv_mae"] / run["baseline_mae"]) * 100
    d = run["cv_dir_acc"] * 100
    msg = {"high": "Passed its practice tests clearly",
           "medium": "Passed its practice tests, but only narrowly",
           "low": "Did NOT beat 'price stays the same' in practice tests, so treat this as a guess"}[lvl]
    return lvl, f"{msg} (direction right {d:.0f}% of the time in practice, error {skill:+.1f}% vs. guessing)."

def verdict(r):
    """r: resolved predictions of ONE coin. Returns (emoji, headline, [plain sentences])."""
    n = len(r)
    need = config.MIN_RESOLVED_FOR_VERDICT
    if n == 0:
        return "⚪", "No results yet", ["Wait for the next hour to pass, then the first forecast gets checked."]
    err_pct = r["pct_error"].mean()
    naive_pct = ((r["actual_price"] - r["base_price"]).abs() / r["actual_price"]).mean() * 100
    calls = r["direction_correct"].dropna()
    m, k = len(calls), int(calls.sum())
    acc = k / m if m else 0.5
    lines = []
    if m:
        lines.append(f"Up/down calls: {k} right out of {m} ({acc:.0%}). Flipping a coin gets about 50%.")
    lines.append(f"Typical miss: {_pct(err_pct)} of the price. Simply assuming 'the price stays the same' would miss by {_pct(naive_pct)}.")
    if n < need:
        return "🟡", "Too early to tell", [f"Only {n} forecast{'s' if n != 1 else ''} checked so far; we need at least {need} before the score means anything."] + lines
    z = (acc - 0.5) / (0.5 / math.sqrt(m)) if m else 0.0
    better = err_pct < naive_pct
    if z > 1.64 and better:
        return "🟢", "Better than guessing", lines
    if z < -1.64 or (not better and acc < 0.5):
        return "🔴", "Worse than guessing", lines
    return "🟡", "About the same as guessing", lines

def paper_sentence(E, T, start):
    """E: paper_equity, T: paper_trades. One plain sentence about the pretend-money account."""
    if len(E) == 0:
        return "No pretend trading data yet."
    eq, bh = float(E["equity"].iloc[-1]), float(E["bh_equity"].iloc[-1])
    chg = (eq / start - 1) * 100
    n = len(T)
    s = (f"If you had started with {start:,.0f} USDT of pretend money, it would now be {eq:,.2f} ({chg:+.2f}%). "
         f"Simply buying the coins once and holding would be {bh:,.2f}. ")
    if n == 0:
        s += "No trades have been made yet: the bot only buys when it is confident, and so far it has not been."
    else:
        wins = int((T["pnl"] > 0).sum())
        s += f"The bot has made {n} trade{'s' if n != 1 else ''}, {wins} of them profitable, paying {T['fees'].sum():,.2f} USDT in fees."
    return s
