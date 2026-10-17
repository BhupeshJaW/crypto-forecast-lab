"""Paper-trading engine: long-only spot, fees, slippage, stop-loss, take-profit, exposure caps, daily loss halt.
The same Portfolio.step() is used by the live loop and by backtest.py."""
import json, numpy as np, pandas as pd
import config as C
import db, alerts
from logger import get_logger
log = get_logger()

class Portfolio:
    def __init__(self):
        self.cash = C.PAPER_START_BALANCE
        self.start_equity = self.cash
        self.positions = {}      # symbol -> {qty, entry_fill, entry_fee, entry_time}
        self.day = None
        self.day_start_equity = self.cash
        self.last_ts = {}        # symbol -> last processed candle (iso)

    def equity(self, prices):
        return self.cash + sum(p["qty"] * prices.get(s, p["entry_fill"]) for s, p in self.positions.items())

    def to_json(self):
        return json.dumps(self.__dict__, default=str)

    @classmethod
    def from_json(cls, s):
        p = cls(); p.__dict__.update(json.loads(s)); return p

    def _sell(self, symbol, ts, px, reason):
        pos = self.positions.pop(symbol)
        fill = px * (1 - C.SLIPPAGE)
        proceeds = pos["qty"] * fill
        fee = proceeds * (C.FEE_RATE + C.TDS_RATE)
        self.cash += proceeds - fee
        basis = pos["qty"] * pos["entry_fill"] + pos["entry_fee"]
        pnl = proceeds - fee - basis
        hold = (pd.Timestamp(ts) - pd.Timestamp(pos["entry_time"])).total_seconds() / 3600
        return {"symbol": symbol, "entry_time": pos["entry_time"], "exit_time": pd.Timestamp(ts).isoformat(),
                "entry_price": pos["entry_fill"], "exit_price": fill, "qty": pos["qty"],
                "fees": pos["entry_fee"] + fee, "pnl": pnl, "pnl_pct": pnl / basis, "reason": reason, "hold_hours": hold}

    def step(self, symbol, ts, candle, pred_ret, prices, trade_ok=True):
        """candle: just-closed candle (close, optional low/high). pred_ret: predicted NEXT-hour return.
        prices: latest close of every coin (for equity). Returns list of closed-trade dicts."""
        ts = pd.Timestamp(ts)
        closed = []
        if self.day != str(ts.date()):
            self.day, self.day_start_equity = str(ts.date()), self.equity(prices)
        close = candle["close"]
        low, high = candle.get("low", close), candle.get("high", close)
        pos, exited = self.positions.get(symbol), False
        if pos:
            stop, tp = pos["entry_fill"] * (1 - C.STOP_LOSS), pos["entry_fill"] * (1 + C.TAKE_PROFIT)
            if low <= stop:                     # stop assumed hit first if both levels touched (conservative)
                closed.append(self._sell(symbol, ts, stop, "stop_loss")); exited = True
            elif high >= tp:
                closed.append(self._sell(symbol, ts, tp, "take_profit")); exited = True
            elif pred_ret < C.EXIT_THRESHOLD and (ts - pd.Timestamp(pos["entry_time"])).total_seconds() / 3600 >= C.MIN_HOLD_HOURS:
                closed.append(self._sell(symbol, ts, close, "signal_exit")); exited = True
        eq = self.equity(prices)
        halted = self.day_start_equity > 0 and (eq - self.day_start_equity) / self.day_start_equity <= -C.MAX_DAILY_LOSS
        if symbol not in self.positions and not exited and not halted and trade_ok and pred_ret >= C.ENTRY_THRESHOLD:
            size = min(self.cash, C.POSITION_FRACTION * eq, C.MAX_EXPOSURE * eq - (eq - self.cash))
            if size > 10:
                fill = close * (1 + C.SLIPPAGE)
                qty = size / (fill * (1 + C.FEE_RATE))
                fee = qty * fill * C.FEE_RATE
                self.cash -= qty * fill + fee
                self.positions[symbol] = {"qty": qty, "entry_fill": fill, "entry_fee": fee, "entry_time": ts.isoformat()}
        self.last_ts[symbol] = ts.isoformat()
        return closed

def summary(eq, trades):
    """eq: DataFrame[equity, bh_equity] (hourly); trades: DataFrame of closed trades."""
    out = {}
    e = eq["equity"]
    out["return_%"] = (e.iloc[-1] / e.iloc[0] - 1) * 100
    out["buy_hold_%"] = (eq["bh_equity"].iloc[-1] / eq["bh_equity"].iloc[0] - 1) * 100
    out["max_drawdown_%"] = (e / e.cummax() - 1).min() * 100
    r = e.pct_change().dropna()
    out["sharpe"] = float(r.mean() / r.std() * np.sqrt(8760)) if len(r) > 2 and r.std() > 0 else 0.0
    out["trades"] = len(trades)
    if len(trades):
        w, l = trades[trades.pnl > 0].pnl.sum(), -trades[trades.pnl < 0].pnl.sum()
        out["win_rate_%"] = (trades.pnl > 0).mean() * 100
        out["avg_trade_%"] = trades.pnl_pct.mean() * 100
        out["profit_factor"] = float(w / l) if l > 0 else float("inf")
        out["fees_paid"] = trades.fees.sum()
    return out

def live_update(dfs, preds, gate=None):
    """Called once per cycle with {symbol: candles_df} and {symbol: predicted_return}."""
    raw = db.kv_get("portfolio")
    pf = Portfolio.from_json(raw) if raw else Portfolio()
    prices = {s: float(d["close"].iloc[-1]) for s, d in dfs.items()}
    start = json.loads(db.kv_get("bh_start") or "null")
    if start is None:
        start = {s: prices[s] for s in config_symbols() if s in prices}
        db.kv_set("bh_start", json.dumps(start))
    latest = None
    for s, ret in preds.items():
        row = dfs[s].iloc[-1]
        ts = row["ts"]
        latest = ts if latest is None or ts > latest else latest
        if pf.last_ts.get(s, "") >= ts.isoformat():
            continue
        candle = {k: float(row[k]) for k in ("close", "low", "high") if k in row and pd.notna(row[k])}
        for t in pf.step(s, ts, candle, ret, prices, True if gate is None else gate.get(s, False)):
            db.add_paper_trade(t)
            log.info(f"[paper] SELL {s} {t['reason']} pnl={t['pnl']:+.2f} ({t['pnl_pct']*100:+.2f}%) fees={t['fees']:.2f}")
            alerts.notify(f"{'🔴' if t['pnl'] < 0 else '🟢'} PAPER SELL {s} ({t['reason']}) pnl {t['pnl']:+.2f} ({t['pnl_pct']*100:+.2f}%)")
        if s in pf.positions and pf.positions[s]["entry_time"] == ts.isoformat():
            log.info(f"[paper] BUY {s} qty={pf.positions[s]['qty']:.6f} @ {pf.positions[s]['entry_fill']:.4f}")
            alerts.notify(f"🛒 PAPER BUY {s} @ {pf.positions[s]['entry_fill']:.4f} (predicted {ret*100:+.2f}% next hour)")
    if latest is not None:
        eq = pf.equity(prices)
        bh = pf.start_equity * (1 - C.FEE_RATE) * np.mean([prices[s] / p for s, p in start.items() if s in prices])
        db.add_equity(latest.isoformat(), pf.cash, eq, bh, len(pf.positions))
        log.info(f"[paper] equity={eq:.2f} cash={pf.cash:.2f} open={list(pf.positions)} buy&hold={bh:.2f}")
    db.kv_set("portfolio", pf.to_json())

def config_symbols():
    return C.SYMBOLS
