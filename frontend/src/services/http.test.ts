import test from "node:test";
import assert from "node:assert/strict";
import { createClient, buildUrl, normalizeBaseUrl } from "./http";
import { ApiError, parseRetryAfter } from "./errors";

type Call = { url: string; init: RequestInit };
function mockFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>, calls: Call[] = []) {
  const f = (async (input: unknown, init: RequestInit = {}) => {
    calls.push({ url: String(input), init });
    return handler(String(input), init);
  }) as unknown as typeof fetch;
  return { f, calls };
}
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
const client = (f: typeof fetch, token: string | null = "secret-token", extra = {}) =>
  createClient({ baseUrl: "", getToken: () => token, fetchImpl: f, ...extra });

test("sends bearer token on authed routes and never on /health", async () => {
  const { f, calls } = mockFetch(() => json({ ok: 1 }));
  const c = client(f);
  await c.get("/api/forecasts");
  await c.get("/health", { auth: false });
  const h0 = calls[0]!.init.headers as Record<string, string>;
  const h1 = calls[1]!.init.headers as Record<string, string>;
  assert.equal(h0.Authorization, "Bearer secret-token");
  assert.equal(h1.Authorization, undefined);
});

test("no Authorization header when no token is set", async () => {
  const { f, calls } = mockFetch(() => json([]));
  await client(f, null).get("/api/signals");
  assert.equal((calls[0]!.init.headers as Record<string, string>).Authorization, undefined);
});

test("only GET is ever used", async () => {
  const { f, calls } = mockFetch(() => json([]));
  await client(f).get("/api/models");
  assert.equal(calls[0]!.init.method, "GET");
});

test("401 -> unauthorized, calls onUnauthorized, message never contains the token", async () => {
  let called = 0;
  const { f } = mockFetch(() => json({ detail: "Missing or invalid token" }, 401));
  const c = client(f, "secret-token", { onUnauthorized: () => called++ });
  await assert.rejects(c.get("/api/models"), (e: ApiError) => {
    assert.equal(e.kind, "unauthorized");
    assert.ok(!e.message.includes("secret-token"));
    return true;
  });
  assert.equal(called, 1);
});

test("403, 404, 429, 502, 500 map to the right kinds", async () => {
  const cases: [number, string][] = [[403, "forbidden"], [404, "not_found"], [429, "rate_limited"], [502, "upstream"], [500, "server"], [422, "bad_request"]];
  for (const [status, kind] of cases) {
    const { f } = mockFetch(() => json({ detail: "x" }, status));
    await assert.rejects(client(f).get("/api/x"), (e: ApiError) => e.kind === kind && e.status === status, `status ${status}`);
  }
});

test("404 shows the backend's safe detail text", async () => {
  const { f } = mockFetch(() => json({ detail: "Unknown symbol DOGEUSDT" }, 404));
  await assert.rejects(client(f).get("/api/coins/DOGEUSDT"), (e: ApiError) => e.message === "Unknown symbol DOGEUSDT");
});

test("429 carries Retry-After seconds; defaults to 60", async () => {
  const a = mockFetch(() => json({ detail: "Too many requests" }, 429, { "Retry-After": "12" }));
  await assert.rejects(client(a.f).get("/api/x"), (e: ApiError) => e.retryAfterSec === 12);
  const b = mockFetch(() => json({ detail: "Too many requests" }, 429));
  await assert.rejects(client(b.f).get("/api/x"), (e: ApiError) => e.retryAfterSec === 60);
});

test("parseRetryAfter handles seconds, HTTP dates, junk and caps", () => {
  assert.equal(parseRetryAfter("5"), 5);
  assert.equal(parseRetryAfter("abc"), 60);
  assert.equal(parseRetryAfter(null), 60);
  assert.equal(parseRetryAfter("999999"), 3600);
  const now = Date.parse("2026-10-17T10:00:00Z");
  assert.equal(parseRetryAfter("Sat, 17 Oct 2026 10:00:30 GMT", now), 30);
});

test("non-JSON error bodies are never shown", async () => {
  const { f } = mockFetch(() => new Response("<html>Traceback secret path /srv/app.py</html>", { status: 500 }));
  await assert.rejects(client(f).get("/api/x"), (e: ApiError) => e.kind === "server" && !e.message.includes("Traceback"));
});

test("422 array detail falls back to a generic message", async () => {
  const { f } = mockFetch(() => json({ detail: [{ loc: ["query", "limit"], msg: "too small" }] }, 422));
  await assert.rejects(client(f).get("/api/x"), (e: ApiError) => e.kind === "bad_request" && e.message.startsWith("The request was rejected"));
});

test("2xx with invalid JSON -> invalid_response", async () => {
  const { f } = mockFetch(() => new Response("not json", { status: 200 }));
  await assert.rejects(client(f).get("/api/x"), (e: ApiError) => e.kind === "invalid_response");
});

test("fetch rejection -> network", async () => {
  const f = (async () => { throw new TypeError("Failed to fetch"); }) as unknown as typeof fetch;
  await assert.rejects(client(f).get("/api/x"), (e: ApiError) => e.kind === "network");
});

test("timeout -> timeout kind", async () => {
  const f = ((_u: unknown, init: RequestInit) =>
    new Promise((_res, rej) => init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))))) as unknown as typeof fetch;
  await assert.rejects(client(f, "t", { timeoutMs: 20 }).get("/api/x"), (e: ApiError) => e.kind === "timeout");
});

test("caller abort -> aborted kind", async () => {
  const f = ((_u: unknown, init: RequestInit) =>
    new Promise((_res, rej) => init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))))) as unknown as typeof fetch;
  const ctrl = new AbortController();
  const p = client(f).get("/api/x", { signal: ctrl.signal });
  ctrl.abort();
  await assert.rejects(p, (e: ApiError) => e.kind === "aborted");
});

test("buildUrl drops undefined query values and normalizeBaseUrl validates", () => {
  assert.equal(buildUrl("", "/api/a", { limit: 5, x: undefined }), "/api/a?limit=5");
  assert.equal(buildUrl("http://h:1", "/a"), "http://h:1/a");
  assert.equal(normalizeBaseUrl(""), "");
  assert.equal(normalizeBaseUrl("https://api.example.com/"), "https://api.example.com");
  assert.throws(() => normalizeBaseUrl("javascript:alert(1)"));
  assert.throws(() => normalizeBaseUrl("not a url"));
});
