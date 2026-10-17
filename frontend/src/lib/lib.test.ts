import test from "node:test";
import assert from "node:assert/strict";
import { fmtAge, fmtFraction, fmtNumber, fmtPct, fmtPrice, fmtUtc, tone } from "./format";
import { ageHoursFrom, freshness, isExpired, liveAge } from "./freshness";
import { nextDelay } from "./polling";
import { describeSource } from "./source";

test("formatters render null / NaN / Infinity as n/a, never 'NaN'", () => {
  for (const bad of [null, undefined, NaN, Infinity, -Infinity]) {
    assert.equal(fmtNumber(bad), "n/a");
    assert.equal(fmtPct(bad), "n/a");
    assert.equal(fmtPrice(bad), "n/a");
    assert.equal(fmtFraction(bad), "n/a");
    assert.equal(fmtAge(bad), "unknown age");
  }
});

test("percent and price formatting", () => {
  assert.equal(fmtPct(0.1234), "+0.12%");
  assert.equal(fmtPct(-0.5), "-0.50%");
  assert.equal(fmtPct(0), "0.00%");
  assert.equal(fmtFraction(0.5182), "51.8%");
  assert.equal(fmtPrice(81727.84), "81,727.84 USDT");
  assert.equal(fmtPrice(2415.74), "2,415.74 USDT");
  assert.equal(fmtPrice(0.123456, "INR"), "0.123456 INR");
});

test("fmtUtc is explicit about UTC and tolerates garbage", () => {
  assert.equal(fmtUtc("2026-10-16T21:01:11.224554+00:00"), "2026-10-16 21:01 UTC");
  assert.equal(fmtUtc("2026-10-17T02:31:00+05:30"), "2026-10-16 21:01 UTC");
  assert.equal(fmtUtc("nonsense"), "n/a");
  assert.equal(fmtUtc(null), "n/a");
});

test("fmtAge and tone", () => {
  assert.equal(fmtAge(0.5), "30 min ago");
  assert.equal(fmtAge(1.42), "1.4 h ago");
  assert.equal(fmtAge(72), "3 d ago");
  assert.equal(tone(1), "up");
  assert.equal(tone(-1), "down");
  assert.equal(tone(0), "flat");
  assert.equal(tone(null), "flat");
});

test("freshness thresholds follow the backend limit", () => {
  assert.equal(freshness(0.4, 3), "fresh");
  assert.equal(freshness(2, 3), "aging");
  assert.equal(freshness(3.01, 3), "stale");
  assert.equal(freshness(null, 3), "unknown");
  assert.equal(freshness(NaN, 3), "unknown");
});

test("age, expiry and live-age helpers", () => {
  const now = Date.parse("2026-10-17T12:00:00Z");
  assert.equal(ageHoursFrom("2026-10-17T10:00:00Z", now), 2);
  assert.equal(ageHoursFrom("bad", now), null);
  assert.equal(isExpired("2026-10-17T11:59:59Z", now), true);
  assert.equal(isExpired("2026-10-17T12:00:01Z", now), false);
  assert.equal(isExpired(null, now), false);
  assert.equal(liveAge(1, now - 1_800_000, now), 1.5);
  assert.equal(liveAge(null, now, now), null);
});

test("polling: normal, stop on 401/403, honour Retry-After, back off and cap", () => {
  assert.equal(nextDelay(60_000, null, 0), 60_000);
  assert.equal(nextDelay(60_000, { kind: "unauthorized", retryAfterSec: null }, 1), null);
  assert.equal(nextDelay(60_000, { kind: "forbidden", retryAfterSec: null }, 1), null);
  assert.equal(nextDelay(60_000, { kind: "rate_limited", retryAfterSec: 120 }, 1), 120_000);
  assert.equal(nextDelay(60_000, { kind: "rate_limited", retryAfterSec: 5 }, 1), 60_000);
  assert.equal(nextDelay(60_000, { kind: "network", retryAfterSec: null }, 1), 120_000);
  assert.equal(nextDelay(60_000, { kind: "server", retryAfterSec: null }, 10), 300_000);
});

test("source labels: Binance is never presented as CoinSwitch INR", () => {
  for (const s of ["binance", "binance_usdt_close", "binance_usdt_last_closed_candle"]) {
    const i = describeSource(s);
    assert.equal(i.kind, "binance_usdt");
    assert.equal(i.executable, false);
  }
  assert.equal(describeSource("coingecko").kind, "coingecko_usd");
  assert.equal(describeSource(undefined).kind, "unknown");
  assert.equal(describeSource("coinswitch_inr_ticker").kind, "coinswitch_inr");
});
