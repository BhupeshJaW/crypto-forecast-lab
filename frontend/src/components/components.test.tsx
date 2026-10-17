import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { ErrorState } from "./ErrorState";
import { FreshnessBadge } from "./FreshnessBadge";
import { SourceBadge } from "./SourceBadge";
import { ApiError } from "../services/errors";

test("ErrorState: 401 asks for a token, hides Retry, flags stale data", () => {
  const html = renderToStaticMarkup(
    <ErrorState error={new ApiError("unauthorized", "Authentication required, or the API token was rejected.", 401)} onRetry={() => {}} showingStale />,
  );
  assert.match(html, /API token needed/);
  assert.doesNotMatch(html, /Retry now/);
  assert.match(html, /last data received/);
});

test("ErrorState: network error offers Retry and the start command", () => {
  const html = renderToStaticMarkup(<ErrorState error={new ApiError("network", "Cannot reach the backend.")} onRetry={() => {}} />);
  assert.match(html, /Retry now/);
  assert.match(html, /uvicorn api:app/);
});

test("FreshnessBadge: stale data carries an explicit warning", () => {
  const html = renderToStaticMarkup(<FreshnessBadge ageHours={5} maxHours={3} />);
  assert.match(html, /stale/);
  assert.match(html, /Do not act on this/);
});

test("SourceBadge: Binance is labelled as a USDT reference, never as CoinSwitch INR", () => {
  const html = renderToStaticMarkup(<SourceBadge source="binance_usdt_close" />);
  assert.match(html, /Binance USDT/);
  assert.match(html, /reference only/);
  assert.doesNotMatch(html, />CoinSwitch INR</);
});
