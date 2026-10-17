import test from "node:test";
import assert from "node:assert/strict";
import { ascendingUnique, drawdownSeries, equityPoints, isoToSeconds, prepareCandles } from "./chartData";
import { changePct } from "./market";
import { totalPnl, unrealizedPnl, versusBuyHold } from "./portfolio";
import { parseAlertLine, parseAlertLines } from "./alertLog";
import { hrefFor, parseHash } from "./route";
import { bySymbol, isForecastAvailable, isSignalPresent } from "./guards";
import type { Candle, PaperPortfolio } from "../types/api";

const cd = (time: number, o: Partial<Candle> = {}): Candle => ({ time, open: 10, high: 12, low: 9, close: 11, volume: 5, ...o });

test("ascendingUnique sorts, de-duplicates (keeps last) and drops bad times", () => {
  const r = ascendingUnique([{ time: 3, v: "c" }, { time: 1, v: "a" }, { time: 3, v: "c2" }, { time: NaN, v: "x" }]);
  assert.deepEqual(r.map((x) => x.time), [1, 3]);
  assert.equal(r[1]!.v, "c2");
});

test("prepareCandles drops null/inconsistent OHLC and counts them", () => {
  const p = prepareCandles([cd(1), cd(2, { close: null }), cd(3, { high: 5, low: 9 }), cd(4, { volume: null })]);
  assert.equal(p.ohlc.length, 2);
  assert.equal(p.dropped, 2);
  assert.equal(p.volume.length, 1);
});

test("prepareCandles handles unsorted input and indicator warm-up nulls", () => {
  const p = prepareCandles([cd(300, { sma20: 10.5, rsi14: 55 }), cd(100, { sma20: null }), cd(200, { sma20: 10 })]);
  assert.deepEqual(p.ohlc.map((c) => c.time), [100, 200, 300]);
  assert.deepEqual(p.sma20.map((c) => c.time), [200, 300]);
  assert.equal(p.rsi.length, 1);
});

test("volume bars are marked up/down by candle direction", () => {
  const p = prepareCandles([cd(1, { open: 10, close: 11 }), cd(2, { open: 11, close: 10 })]);
  assert.deepEqual(p.volume.map((v) => v.up), [true, false]);
});

test("equityPoints parses ISO times to unix seconds, drops bad rows; drawdown is <= 0", () => {
  assert.equal(isoToSeconds("2026-10-16T20:00:00+00:00"), Date.parse("2026-10-16T20:00:00Z") / 1000);
  assert.equal(isoToSeconds("junk"), null);
  const pts = equityPoints([
    { ts: "2026-10-16T22:00:00+00:00", cash: 1, equity: 90, bh_equity: 100, open_positions: 0 },
    { ts: "2026-10-16T20:00:00+00:00", cash: 1, equity: 100, bh_equity: null, open_positions: 0 },
    { ts: "bad", cash: 1, equity: 5, bh_equity: 5, open_positions: 0 },
    { ts: "2026-10-16T21:00:00+00:00", cash: 1, equity: null, bh_equity: 5, open_positions: 0 },
  ]);
  assert.equal(pts.length, 2);
  assert.equal(pts[0]!.buyHold, null);
  const dd = drawdownSeries(pts);
  assert.equal(dd[0]!.value, 0);
  assert.ok(Math.abs(dd[1]!.value - -10) < 1e-9);
});

test("changePct", () => {
  assert.ok(Math.abs((changePct([100, 101, 110], 2) ?? 0) - 10) < 1e-9);
  assert.equal(changePct([100, null, 110], 1), null);
  assert.equal(changePct([100], 24), null);
  assert.equal(changePct([0, 5], 1), null);
});

const pf = (o: Partial<PaperPortfolio> = {}): PaperPortfolio => ({
  start_balance: 10000, currency: "USDT (paper)", open_positions: {}, trades: 0, realized_pnl: 0, fees_paid: 0,
  win_rate_pct: null, statistically_conclusive: false, note: "", ...o,
});

test("portfolio derived numbers", () => {
  assert.equal(totalPnl(pf()), null);
  assert.deepEqual(totalPnl(pf({ equity: 10100 })), { abs: 100, pct: 1 });
  assert.equal(unrealizedPnl(pf({ equity: 10000, cash: 10000 })), 0);
  const open = { BTCUSDT: { qty: 0.1, entry_fill: 80000, entry_fee: 8, entry_time: "t" } };
  assert.equal(unrealizedPnl(pf({ equity: 10050, cash: 2000, open_positions: open })), 10050 - 2000 - 8000);
  assert.equal(unrealizedPnl(pf()), null);
  assert.equal(versusBuyHold(pf({ equity: 10000, buy_hold_equity: 10058.54 }))?.toFixed(2), "-0.58");
  assert.equal(versusBuyHold(pf({ equity: 10000 })), null);
});

test("alert log parsing", () => {
  const a = parseAlertLine("2026-10-16 22:26:29,202 | ERROR | [BTCUSDT] fetch failed: timeout\r");
  assert.equal(a.loggedAt, "2026-10-16 22:26:29");
  assert.equal(a.level, "ERROR");
  assert.equal(a.kind, "fetch_failed");
  assert.equal(parseAlertLine("2026-10-16 22:00:00,000 | INFO | [alert] telegram sent").kind, "alert");
  const odd = parseAlertLine("Traceback weird line");
  assert.equal(odd.loggedAt, null);
  assert.equal(odd.level, "OTHER");
  assert.equal(parseAlertLine("x".repeat(2000)).message.length, 500);
  assert.equal(parseAlertLines(["2026-10-16 01:00:00,000 | ERROR | a", "2026-10-16 02:00:00,000 | ERROR | b"])[0]!.message, "b");
});

test("routing", () => {
  assert.deepEqual(parseHash(""), { page: "overview" });
  assert.deepEqual(parseHash("#/coin/btcusdt"), { page: "coin", symbol: "BTCUSDT" });
  assert.deepEqual(parseHash("#/coin/../../x"), { page: "coin", symbol: null });
  assert.deepEqual(parseHash("#/portfolio"), { page: "portfolio" });
  assert.deepEqual(parseHash("#/nonsense"), { page: "overview" });
  assert.equal(hrefFor({ page: "coin", symbol: "ETHUSDT" }), "#/coin/ETHUSDT");
  assert.equal(hrefFor({ page: "overview" }), "#/");
});

test("guards", () => {
  assert.equal(isForecastAvailable({ symbol: "A", available: false }), false);
  assert.equal(isSignalPresent({ symbol: "A", signal: null, note: "n" }), false);
  assert.equal(isSignalPresent({ symbol: "A", signal: "HOLD" } as never), true);
  assert.equal(bySymbol([{ symbol: "A" }, { symbol: "B" }], "B")?.symbol, "B");
});
