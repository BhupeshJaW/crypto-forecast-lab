import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { SignalDetail } from "./SignalDetail";
import type { Signal, SignalPresent } from "../types/api";

const base: SignalPresent = {
  symbol: "BTCUSDT", signal: "BUY", sell_type: null, reference_price: 81727.84, price_source: "binance_usdt_close",
  price_note: "Reference price is the Binance USDT close.", horizon_hours: 1, predicted_return_pct: 0.4,
  typical_error_band_pct: [0.1, 0.7], estimated_round_trip_cost_pct: 0.3, net_edge_after_costs_pct: 0.1, model_grade: "medium",
  holdout_hours: 300, grade_note: "n", data_age_hours: 0.5, created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 3_600_000).toISOString(), reasons: ["Forecast +0.40% leaves +0.10% after costs."], blockers: [],
  entry_zone: [81727.84, 81809.5], stop_loss: 80093.28, take_profit: 84179.67, reward_to_risk: 1.5,
};

test("BUY signal shows entry zone, stop, target and reasons", () => {
  const html = renderToStaticMarkup(<SignalDetail signal={base} />);
  assert.match(html, /Entry zone/); assert.match(html, /Stop-loss/); assert.match(html, /Take-profit/);
  assert.match(html, /leaves \+0\.10% after costs/); assert.doesNotMatch(html, /expired/i);
});

test("expired signal is flagged and told not to be acted on", () => {
  const html = renderToStaticMarkup(<SignalDetail signal={{ ...base, expires_at: "2020-01-01T00:00:00+00:00" }} />);
  assert.match(html, /This signal has expired/); assert.match(html, /Do not act on it/);
});

test("NO_TRADE shows blockers and no trade levels", () => {
  const s: Signal = { ...base, signal: "NO_TRADE", blockers: ["Data is stale (5.0h since the last candle closed)."], entry_zone: undefined, stop_loss: undefined, take_profit: undefined };
  const html = renderToStaticMarkup(<SignalDetail signal={s} />);
  assert.match(html, /Blocked by a safety rule/); assert.match(html, /Data is stale/); assert.doesNotMatch(html, /Entry zone/);
});

test("missing signal renders an empty state, not a crash", () => {
  const html = renderToStaticMarkup(<SignalDetail signal={{ symbol: "BTCUSDT", signal: null, note: "no signal generated yet" }} />);
  assert.match(html, /No signal generated yet/); assert.match(html, /scheduler\.py --once/);
});

test("null numeric fields render as n/a, never NaN", () => {
  const html = renderToStaticMarkup(<SignalDetail signal={{ ...base, predicted_return_pct: null, net_edge_after_costs_pct: null, typical_error_band_pct: null }} />);
  assert.match(html, /n\/a/); assert.doesNotMatch(html, /NaN/);
});
