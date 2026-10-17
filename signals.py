"""BUY / SELL / HOLD / NO TRADE decision engine (spot, long-only).

Pure functions: no network, no database, so every rule can be unit-tested.
A signal is a structured, time-limited *suggestion* from a model that has to prove it beat 'price stays the same'
on unseen data. It is not a prediction of profit, and `confidence` is a validation grade, not a probability."""
import json, math
from datetime import datetime, timedelta, timezone
import config as C

PRICE_NOTE = ("Reference price is the Binance USDT close used for training. It is NOT a CoinSwitch INR price "
              "and not an executable quote. Check the live CoinSwitch price before acting.")

def round_trip_cost(fee=None, slippage=None, spread=0.0):
    """Fraction of position value lost to costs on a buy followed by a sell."""
    fee = C.FEE_RATE if fee is None else fee
    slippage = C.SLIPPAGE if slippage is None else slippage
    return 2 * (fee + slippage) + spread

def _signal(symbol, kind, price, pred, info, age_h, now, cost, reasons, blockers, sell_type=None, levels=None):
    horizon = C.SIGNAL_HORIZON_HOURS
    mae = info.get("mae")
    band = None
    if mae and math.isfinite(pred):
        band = [round((pred - mae * 1.25) * 100, 3), round((pred + mae * 1.25) * 100, 3)]   # ~ +/- one typical miss
    out = {
        "symbol": symbol, "signal": kind, "sell_type": sell_type,
        "reference_price": price, "price_source": "binance_usdt_close", "price_note": PRICE_NOTE,
        "horizon_hours": horizon,
        "predicted_return_pct": round(pred * 100, 4) if math.isfinite(pred) else None,
        "typical_error_band_pct": band,
        "estimated_round_trip_cost_pct": round(cost * 100, 3),
        "net_edge_after_costs_pct": round((pred - cost) * 100, 4) if math.isfinite(pred) else None,
        "model_grade": info.get("conf", "low"), "holdout_hours": info.get("n"),
        "grade_note": "Grade from unseen-data tests. It is not the chance of making money.",
        "data_age_hours": None if age_h is None else round(age_h, 2),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=horizon)).isoformat(),
        "reasons": reasons, "blockers": blockers,
    }
    if levels:
        out.update(levels)
    return out

def build_signal(symbol, price, pred, info, data_age_h, held=False, now=None, spread=0.0, source="binance"):
    """info: model grade dict ({'conf','n','mae','vol_regime'}). held: do we hold this coin in the paper account."""
    now = now or datetime.now(timezone.utc)
    cost = round_trip_cost(spread=spread)
    reasons, blockers = [], []
    mk = lambda kind, **kw: _signal(symbol, kind, price, pred, info, data_age_h, now, cost, reasons, blockers, **kw)

    # ---- hard blockers: any one of these means NO TRADE (never a guess) ----
    if price is None or not math.isfinite(price) or price <= 0 or pred is None or not math.isfinite(pred):
        blockers.append("Price or forecast is missing or invalid.")
    if source != "binance":
        blockers.append("Data came from a fallback source without volume; the model is not valid on it.")
    if data_age_h is None or data_age_h > C.MAX_DATA_AGE_HOURS:
        blockers.append(f"Data is stale ({'unknown age' if data_age_h is None else f'{data_age_h:.1f}h'} since the last candle closed).")
    vr = info.get("vol_regime")
    if vr is not None and vr > C.MAX_VOL_REGIME:
        blockers.append(f"Volatility is abnormal ({vr:.1f}x its 3-day level).")
    if blockers:
        return mk("NO_TRADE")

    grade = info.get("conf", "low")
    edge = pred - cost

    # ---- an open position is managed separately from new entries ----
    if held:
        if grade != "low" and pred < C.EXIT_THRESHOLD:
            reasons.append(f"Forecast turned negative ({pred*100:+.2f}%) and the model has a validated edge.")
            return mk("SELL", sell_type="exit_position")
        reasons.append("Position is held; stop-loss and take-profit stay active."
                       if grade == "low" else "Forecast has not turned negative.")
        return mk("HOLD")

    if grade == "low":
        blockers.append("Model has not beaten 'price stays the same' on unseen data, so its forecast is not used.")
        return mk("NO_TRADE")

    if pred >= C.ENTRY_THRESHOLD and edge >= C.MIN_NET_EDGE:
        stop, target = price * (1 - C.STOP_LOSS), price * (1 + C.TAKE_PROFIT)
        rr = C.TAKE_PROFIT / C.STOP_LOSS
        if rr < C.MIN_REWARD_RISK:
            blockers.append(f"Reward-to-risk {rr:.2f} is below the minimum {C.MIN_REWARD_RISK}.")
            return mk("NO_TRADE")
        reasons.append(f"Forecast {pred*100:+.2f}% leaves {edge*100:+.2f}% after an estimated {cost*100:.2f}% round-trip cost.")
        reasons.append("Model grade is " + grade + " on unseen data (not a profit probability).")
        return mk("BUY", levels={
            "entry_zone": [price, price * (1 + C.SLIPPAGE * 2)],
            "stop_loss": stop, "take_profit": target, "reward_to_risk": round(rr, 2)})

    if pred <= -C.MIN_NET_EDGE:
        reasons.append(f"Bearish forecast ({pred*100:+.2f}%). Spot long-only: nothing to sell, so stay out.")
        return mk("SELL", sell_type="bearish_not_held")

    reasons.append(f"Forecast {pred*100:+.2f}% is too small to beat costs of {cost*100:.2f}%.")
    return mk("HOLD")

def to_json(sig):
    return json.dumps(sig, default=str)

def alert_text(sig):
    p = sig["reference_price"]
    lines = [f"{'🟢' if sig['signal']=='BUY' else '🔴'} {sig['signal']} signal {sig['symbol']} "
             f"{'(exit position)' if sig.get('sell_type')=='exit_position' else '(bearish, not held)' if sig.get('sell_type') else ''}".strip(),
             f"Reference price (Binance USDT, not CoinSwitch): {p:,.4f}",
             f"Forecast {sig['predicted_return_pct']:+.2f}% over {sig['horizon_hours']}h; est. costs {sig['estimated_round_trip_cost_pct']:.2f}%"]
    if sig["signal"] == "BUY":
        lines.append(f"Stop-loss {sig['stop_loss']:,.4f} | Target {sig['take_profit']:,.4f} | R:R {sig['reward_to_risk']}")
    lines.append(f"Expires {sig['expires_at'][:16].replace('T',' ')} UTC. Paper-trading idea, not advice; confirm the live CoinSwitch price.")
    return "\n".join(lines)
