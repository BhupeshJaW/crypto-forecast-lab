"""HTTP-level tests for api.py (FastAPI TestClient). Hermetic: temp DB and log, no network, no real env secrets.

Run:  python -m unittest tests.test_api_http -v
"""
import json, os, tempfile, time, unittest
from collections import deque
from unittest import mock

# The API module creates its logger at import time. Point the log at a temp dir for the import only,
# so running the tests never writes to the real logs/app.log. (Order matters, hence the E402 imports.)
import config
_REAL_LOG_PATH = config.LOG_PATH
config.LOG_PATH = os.path.join(tempfile.mkdtemp(), "import.log")
import numpy as np, pandas as pd                                    # noqa: E402
from fastapi.testclient import TestClient                           # noqa: E402
import api, data, db, services, signals                              # noqa: E402
from tests.test_model_safety import fake_candles                    # noqa: E402
config.LOG_PATH = _REAL_LOG_PATH

TOKEN = "test-token-abc123"
HEAD = {"Authorization": f"Bearer {TOKEN}"}
PROTECTED = ["/api/forecasts", "/api/signals", "/api/coins/BTCUSDT", "/api/coins/BTCUSDT/candles", "/api/models",
             "/api/backtest", "/api/paper/portfolio", "/api/paper/trades", "/api/paper/equity",
             "/api/alerts/config", "/api/alerts/recent"]
SECRETS = ["SECRET_TOKEN_999", "hunter2", "apikey=LEAK"]


def strict_json(resp):
    """Parse like a strict client would: NaN / Infinity tokens are a failure."""
    def bad(c):
        raise ValueError(f"non-JSON constant {c} in response body")
    return json.loads(resp.text, parse_constant=bad)


def make_candles(n=400, hours_old=1, source="binance", close_only=False):
    """Hourly candles whose newest candle closed `hours_old` hours ago (rounded down to the hour)."""
    df = fake_candles(n)
    end = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=hours_old)
    df["ts"] = pd.date_range(end=end, periods=n, freq="h")
    if close_only:
        df = df[["ts", "close"]].copy()
    df.attrs["source"] = source
    return df


def seed_populated_db():
    now = pd.Timestamp.now(tz="UTC").floor("h")
    # Relative to the real clock, not the floored hour: otherwise the forecast looks >1h old late in each hour.
    created = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5)).isoformat()
    target = (now + pd.Timedelta(hours=1)).isoformat()
    db.add_prediction(("BTCUSDT", created, target, 100.0, 100.4, 0.004, "v1", "ridge"))
    db.add_model_run((created, "BTCUSDT", "v1", "ridge", 0.003, 0.0031, None, 0.52, 1, "first model", 400))
    sig = signals.build_signal("BTCUSDT", 100.0, 0.006,
                               {"conf": "medium", "n": 800, "mae": 0.003, "vol_regime": 1.0}, 0.5)
    db.add_signal("BTCUSDT", target, created, sig["signal"], signals.to_json(sig))
    for i, pnl in enumerate((0.9, -0.4)):
        db.add_paper_trade({"symbol": "BTCUSDT", "entry_time": f"2026-10-1{i}T10:00:00+00:00",
                            "exit_time": f"2026-10-1{i}T13:00:00+00:00", "entry_price": 100 + i, "exit_price": 101 + i,
                            "qty": 1, "fees": 0.1, "pnl": pnl, "pnl_pct": pnl, "reason": "take_profit", "hold_hours": 3})
    for i, eq in enumerate((10000, 9800, 9900)):
        db.add_equity(f"2026-10-17T1{i}:00:00+00:00", 9000, eq, 10000, 1)
    db.kv_set("portfolio", json.dumps({"positions": {}}))
    db.kv_set("last_success", (pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=10)).isoformat())
    pd.DataFrame({"scenario": ["small sample", "large sample"], "return_%": [0.4, -16.1], "trades": [7, 207]}) \
        .to_csv(os.path.join(os.path.dirname(config.DB_PATH), "backtest_summary.csv"), index=False)
    return sig


class ApiTestBase(unittest.TestCase):
    token = None            # subclasses set TOKEN to require auth

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patches = [
            mock.patch.object(config, "DB_PATH", os.path.join(self.tmp, "t.db")),
            mock.patch.object(config, "LOG_PATH", os.path.join(self.tmp, "app.log")),
            mock.patch.object(api, "LIMIT", 10_000),
            mock.patch.dict(os.environ, {}),
        ]
        for p in patches:
            p.start(); self.addCleanup(p.stop)
        for k in ("API_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                  "ALERT_EMAIL_TO", "COINSWITCH_API_KEY"):
            os.environ.pop(k, None)
        if self.token:
            os.environ["API_TOKEN"] = self.token
        api._HITS.clear(); services._CACHE.clear()
        self.addCleanup(api._HITS.clear); self.addCleanup(services._CACHE.clear)
        fp = mock.patch.object(data, "fetch_prices", return_value=make_candles())
        self.fetch = fp.start(); self.addCleanup(fp.stop)
        self.client = TestClient(api.app)
        self.headers = HEAD if self.token else {}

    def get(self, path, **kw):
        kw.setdefault("headers", self.headers)
        return self.client.get(path, **kw)


class AuthWithToken(ApiTestBase):
    token = TOKEN

    def test_health_is_open_and_never_contains_the_token(self):
        for h in ({}, {"Authorization": "Bearer wrong"}, HEAD):
            r = self.client.get("/health", headers=h)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn(TOKEN, r.text)
            self.assertIn(r.json()["status"], ("ok", "degraded"))

    def test_missing_or_wrong_token_is_401_on_every_protected_route(self):
        bad = {"missing": {}, "wrong": {"Authorization": "Bearer nope"}, "empty": {"Authorization": "Bearer "},
               "basic scheme": {"Authorization": f"Basic {TOKEN}"}, "bare token": {"Authorization": TOKEN},
               "prefix only": {"Authorization": f"Bearer {TOKEN[:-1]}"},
               "suffix added": {"Authorization": f"Bearer {TOKEN}x"}}
        for path in PROTECTED:
            for label, h in bad.items():
                with self.subTest(path=path, case=label):
                    r = self.client.get(path, headers=h)
                    self.assertEqual(r.status_code, 401)
                    self.assertEqual(r.json(), {"detail": "Missing or invalid token"})
        self.fetch.assert_not_called()          # auth runs before any upstream fetch

    def test_non_ascii_token_header_is_401_not_a_server_error(self):
        for raw in (b"Bearer \xe9\xe8", b"Bearer \xff"):
            with self.subTest(raw=raw):
                r = self.client.get("/api/signals", headers={"Authorization": raw})
                self.assertEqual(r.status_code, 401)

    def test_correct_token_is_200_on_every_protected_route(self):
        for path in PROTECTED:
            with self.subTest(path=path):
                r = self.get(path)
                self.assertEqual(r.status_code, 200, r.text)
                strict_json(r)

    def test_auth_is_checked_before_symbol_and_limit_validation(self):
        """Unauthenticated callers must not learn which symbols exist or how limits are validated."""
        for path in ("/api/coins/DOGEUSDT", "/api/coins/BTCUSDT/candles?limit=1", "/api/paper/trades?limit=0"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_every_api_route_requires_auth_and_is_covered_here(self):
        seen = []
        for r in api.app.routes:
            path = getattr(r, "path", "")
            if not path.startswith("/api"):
                continue
            seen.append(path.replace("{symbol}", "BTCUSDT"))
            self.assertTrue(any(d.call is api.require_auth for d in r.dependant.dependencies), f"{path} has no auth")
        self.assertEqual(sorted(seen), sorted(PROTECTED), "new /api route: add it to PROTECTED so it is tested")


class NoTokenConfigured(ApiTestBase):
    def test_everything_is_open(self):
        for path in ["/health"] + PROTECTED:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_blank_token_counts_as_not_configured(self):
        os.environ["API_TOKEN"] = ""
        self.assertEqual(self.client.get("/api/signals").status_code, 200)


class Validation(ApiTestBase):
    def test_unknown_symbol_is_404_with_json_body(self):
        for path in ("/api/coins/DOGEUSDT", "/api/coins/DOGEUSDT/candles", "/api/coins/BTCUSDT%3BDROP%20TABLE%20x"):
            with self.subTest(path=path):
                r = self.get(path)
                self.assertEqual(r.status_code, 404)
                self.assertTrue(r.headers["content-type"].startswith("application/json"))
                self.assertIn("Unknown symbol", r.json()["detail"])
        self.fetch.assert_not_called()

    def test_symbol_is_case_insensitive(self):
        self.assertEqual(self.get("/api/coins/btcusdt").status_code, 200)

    def test_invalid_limits_are_422(self):
        bad = ["/api/coins/BTCUSDT/candles?limit=49", "/api/coins/BTCUSDT/candles?limit=1001",
               "/api/coins/BTCUSDT/candles?limit=abc", "/api/paper/trades?limit=0", "/api/paper/trades?limit=1001",
               "/api/paper/equity?limit=9", "/api/paper/equity?limit=10001", "/api/alerts/recent?limit=0",
               "/api/alerts/recent?limit=201", "/api/alerts/recent?limit=-5"]
        for path in bad:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 422)

    def test_limit_boundaries_are_accepted(self):
        for path in ("/api/coins/BTCUSDT/candles?limit=50", "/api/coins/BTCUSDT/candles?limit=1000",
                     "/api/paper/trades?limit=1", "/api/paper/trades?limit=1000", "/api/paper/equity?limit=10",
                     "/api/paper/equity?limit=10000", "/api/alerts/recent?limit=1", "/api/alerts/recent?limit=200"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 200)

    def test_api_is_read_only(self):
        for r in api.app.routes:
            self.assertLessEqual(set(getattr(r, "methods", None) or ()), {"GET", "HEAD"}, r.path)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)("/api/signals").status_code, 405)


class RateLimit(ApiTestBase):
    def test_429_after_limit_and_recovers_after_window(self):
        with mock.patch.object(api, "LIMIT", 3):
            codes = [self.client.get("/health").status_code for _ in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
            self.assertEqual(self.client.get("/health").json(), {"detail": "Too many requests"})
            api._HITS["testclient"] = deque([time.time() - api.WINDOW - 1] * 3)     # all hits are now outside the window
            self.assertEqual(self.client.get("/health").status_code, 200)

    def test_unauthenticated_floods_are_limited_too(self):
        os.environ["API_TOKEN"] = TOKEN
        with mock.patch.object(api, "LIMIT", 3):
            codes = [self.client.get("/api/signals").status_code for _ in range(5)]
        self.assertEqual(codes, [401, 401, 401, 429, 429])

    def test_limit_is_tracked_per_client_ip(self):
        with mock.patch.object(api, "LIMIT", 2):
            api._HITS["10.0.0.9"] = deque([time.time()] * 2)
            self.assertEqual(self.client.get("/health").status_code, 200)    # a different client is unaffected


class ErrorBodies(ApiTestBase):
    def test_service_failure_hides_exception_text_and_secrets(self):
        def latest_signals():
            raise RuntimeError(f"db at /home/u/.env {SECRETS[0]} password={SECRETS[1]}")
        with mock.patch.object(services, "latest_signals", latest_signals), self.assertLogs("predictor", "ERROR"):
            r = self.get("/api/signals")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {"detail": "latest_signals failed (RuntimeError)"})
        for s in SECRETS + ["/home/u", "Traceback"]:
            self.assertNotIn(s, r.text)

    def test_upstream_fetch_failure_is_502_without_url_or_key(self):
        self.fetch.side_effect = ConnectionError(f"GET https://x/klines?{SECRETS[2]} failed")
        with self.assertLogs("predictor", "ERROR"):
            r = self.get("/api/coins/BTCUSDT/candles")
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json(), {"detail": "candles failed (ConnectionError)"})
        for s in SECRETS + ["https://x"]:
            self.assertNotIn(s, r.text)

    def test_failed_fetch_is_not_cached(self):
        self.fetch.side_effect = [ConnectionError("down"), make_candles()]
        with self.assertLogs("predictor", "ERROR"):
            self.assertEqual(self.get("/api/coins/BTCUSDT/candles").status_code, 502)
        self.assertEqual(self.get("/api/coins/BTCUSDT/candles").status_code, 200)

    def test_unwrapped_routes_also_leak_nothing(self):
        """/health and /api/alerts/config are not wrapped in _safe; Starlette's generic 500 must still be clean."""
        def boom():
            raise RuntimeError(f"{SECRETS[0]} password={SECRETS[1]}")
        quiet = TestClient(api.app, raise_server_exceptions=False)
        for path, fn in (("/health", "health"), ("/api/alerts/config", "alert_config")):
            with self.subTest(path=path), mock.patch.object(services, fn, boom):
                r = quiet.get(path)
                self.assertEqual(r.status_code, 500)
                for s in SECRETS:
                    self.assertNotIn(s, r.text)

    def test_422_body_contains_no_server_state(self):
        os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = SECRETS[0], "1"
        r = self.get("/api/paper/trades?limit=0")
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(SECRETS[0], r.text)

    def test_config_and_health_never_return_configured_secrets(self):
        os.environ.update({"TELEGRAM_BOT_TOKEN": SECRETS[0], "TELEGRAM_CHAT_ID": "1", "SMTP_HOST": "h", "SMTP_USER": "u",
                           "SMTP_PASSWORD": SECRETS[1], "ALERT_EMAIL_TO": "a@b.c", "COINSWITCH_API_KEY": SECRETS[2]})
        for path in ("/health", "/api/alerts/config"):
            r = self.get(path)
            self.assertEqual(r.status_code, 200)
            for s in SECRETS:
                self.assertNotIn(s, r.text)
        self.assertEqual(sorted(self.get("/api/alerts/config").json()["channels"]), ["email", "telegram"])
        self.assertTrue(self.get("/health").json()["coinswitch_configured"])


class Cors(ApiTestBase):
    ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o]

    def preflight(self, origin, method="GET"):
        return self.client.options("/api/signals", headers={"Origin": origin, "Access-Control-Request-Method": method,
                                                            "Access-Control-Request-Headers": "Authorization"})

    def test_allow_list_has_no_wildcard(self):
        self.assertNotIn("*", self.ORIGINS)

    def test_allowed_origin_is_echoed_and_foreign_origin_is_not(self):
        ok = self.preflight(self.ORIGINS[0])
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers.get("access-control-allow-origin"), self.ORIGINS[0])
        evil = self.preflight("https://evil.example")
        self.assertNotIn("access-control-allow-origin", evil.headers)
        self.assertNotIn("access-control-allow-origin",
                         self.client.get("/health", headers={"Origin": "https://evil.example"}).headers)

    def test_only_get_is_allowed_cross_origin(self):
        self.assertEqual(self.preflight(self.ORIGINS[0], "POST").status_code, 400)


class EmptyDatabase(ApiTestBase):
    def test_every_route_answers_with_honest_empty_state(self):
        for path in ["/health"] + PROTECTED:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 200)
        self.assertEqual(self.get("/health").json()["status"], "degraded")
        self.assertTrue(all(not f["available"] for f in self.get("/api/forecasts").json()))
        self.assertTrue(all(s["signal"] is None for s in self.get("/api/signals").json()))
        self.assertTrue(all(not m["available"] for m in self.get("/api/models").json()))
        self.assertFalse(self.get("/api/backtest").json()["available"])
        pf = self.get("/api/paper/portfolio").json()
        self.assertEqual((pf["trades"], pf["statistically_conclusive"]), (0, False))
        self.assertIn("inconclusive", pf["note"])
        self.assertEqual(self.get("/api/paper/trades").json(), [])
        self.assertEqual(self.get("/api/paper/equity").json(), [])
        self.assertEqual(self.get("/api/alerts/recent").json(), [])

    def test_coin_analysis_on_empty_db(self):
        c = self.get("/api/coins/BTCUSDT").json()
        self.assertFalse(c["forecast"]["available"])
        self.assertIsNone(c["signal"]["signal"])
        self.assertFalse(c["model"]["available"])
        self.assertIn("Not financial advice", c["disclaimer"])


class PopulatedDatabase(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.sig = seed_populated_db()

    def test_forecasts_and_coin_analysis(self):
        f = {x["symbol"]: x for x in self.get("/api/forecasts").json()}
        self.assertTrue(f["BTCUSDT"]["available"])
        self.assertFalse(f["ETHUSDT"]["available"])
        self.assertAlmostEqual(f["BTCUSDT"]["predicted_return_pct"], 0.4)
        self.assertEqual(f["BTCUSDT"]["price_source"], "binance_usdt_last_closed_candle")
        self.assertLess(f["BTCUSDT"]["forecast_age_hours"], 1)
        c = self.get("/api/coins/BTCUSDT").json()
        self.assertEqual(c["forecast"]["model"], "ridge")
        self.assertEqual(c["signal"]["signal"], self.sig["signal"])
        self.assertTrue(c["model"]["available"])

    def test_signals_payload_roundtrips(self):
        s = {x["symbol"]: x for x in self.get("/api/signals").json()}
        self.assertEqual(s["BTCUSDT"]["signal"], self.sig["signal"])
        self.assertIsNone(s["ETHUSDT"]["signal"])

    def test_models_report_holdout_basis_and_grade(self):
        m = {x["symbol"]: x for x in self.get("/api/models").json()}["BTCUSDT"]
        self.assertEqual(m["score_basis"], "untouched holdout")
        self.assertEqual(m["unseen_hours_scored"], 400)
        self.assertIn("grade", m)
        self.assertEqual(m["live_accuracy"]["verdict"], "too early to tell")

    def test_paper_endpoints(self):
        pf = self.get("/api/paper/portfolio").json()
        self.assertEqual(pf["trades"], 2)
        self.assertFalse(pf["statistically_conclusive"])
        self.assertAlmostEqual(pf["max_drawdown_pct"], -2.0)
        self.assertAlmostEqual(pf["realized_pnl"], 0.5)
        self.assertIn("USDT", pf["currency"])
        trades = self.get("/api/paper/trades").json()
        self.assertEqual([t["pnl"] for t in trades], [-0.4, 0.9])             # newest first
        self.assertEqual(len(self.get("/api/paper/trades?limit=1").json()), 1)
        eq = self.get("/api/paper/equity").json()
        self.assertEqual([e["equity"] for e in eq], [10000, 9800, 9900])        # oldest first

    def test_backtest_rows_flag_small_samples(self):
        b = self.get("/api/backtest").json()
        self.assertTrue(b["available"])
        flags = {r["scenario"]: r["inconclusive"] for r in b["rows"]}
        self.assertEqual(flags, {"small sample": True, "large sample": False})

    def test_health_is_ok_after_a_recent_cycle(self):
        h = self.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertLess(h["worker_age_hours"], 1)

    def test_alerts_recent_filters_log_lines(self):
        with open(config.LOG_PATH, "w") as f:
            f.write("2026-10-17 01:00:00,000 | INFO | routine line\n"
                    "2026-10-17 01:01:00,000 | INFO | [alert] BUY signal BTCUSDT\n"
                    "2026-10-17 01:02:00,000 | ERROR | boom\n")
        lines = self.get("/api/alerts/recent").json()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("routine" not in l for l in lines))


class NanHandling(ApiTestBase):
    def test_nan_in_database_rows_serialises_as_null(self):
        db.add_paper_trade({"symbol": "BTCUSDT", "entry_time": "a", "exit_time": "b", "entry_price": 1, "exit_price": 2,
                            "qty": 1, "fees": 0.1, "pnl": float("nan"), "pnl_pct": float("inf"), "reason": "x",
                            "hold_hours": 1})
        r = self.get("/api/paper/trades")
        self.assertEqual(r.status_code, 200)
        t = strict_json(r)[0]
        self.assertIsNone(t["pnl"])
        self.assertIsNone(t["pnl_pct"])

    def test_nan_and_infinity_inside_stored_signal_payload(self):
        db.add_signal("BTCUSDT", "t1", "c1", "HOLD",
                      '{"symbol": "BTCUSDT", "signal": "HOLD", "reference_price": NaN, "edge": Infinity, "ok": 1.5}')
        r = self.get("/api/signals")
        self.assertEqual(r.status_code, 200)
        s = strict_json(r)[0]
        self.assertIsNone(s["reference_price"])
        self.assertIsNone(s["edge"])
        self.assertEqual(s["ok"], 1.5)

    def test_indicator_warmup_nan_becomes_null_in_candles(self):
        self.fetch.return_value = make_candles(n=60)
        r = self.get("/api/coins/BTCUSDT/candles?limit=50")
        self.assertEqual(r.status_code, 200)
        rows = strict_json(r)["candles"]
        self.assertIsNone(rows[0]["sma50"])                 # SMA50 needs 50 candles; the first rows have none
        self.assertIsNotNone(rows[-1]["sma50"])
        self.assertNotIn("NaN", r.text)

    def test_flat_price_series_rsi_is_null_not_nan(self):
        df = make_candles(n=120)
        df["close"] = 100.0
        self.fetch.return_value = df
        r = self.get("/api/coins/BTCUSDT/candles?limit=100")
        self.assertEqual(r.status_code, 200)
        strict_json(r)


class CandlesFreshness(ApiTestBase):
    def test_fresh_candles_report_small_age_and_source(self):
        p = self.get("/api/coins/BTCUSDT/candles").json()
        self.assertLess(p["data_age_hours"], 1.1)
        self.assertGreaterEqual(p["data_age_hours"], 0)
        self.assertEqual(p["source"], "binance")
        self.assertIn("not live", p["note"].lower())
        self.assertIn("not coinswitch", p["note"].lower())
        self.assertEqual(p["interval"], "1h")
        self.assertEqual(len(p["candles"]), 300)

    def test_stale_candles_report_their_real_age(self):
        self.fetch.return_value = make_candles(hours_old=10)
        r = self.get("/api/coins/BTCUSDT/candles")
        self.assertEqual(r.status_code, 200)
        p = r.json()
        self.assertGreater(p["data_age_hours"], config.MAX_DATA_AGE_HOURS)
        self.assertTrue(8.9 < p["data_age_hours"] < 10.1, p["data_age_hours"])
        self.assertEqual(p["last_candle_time"], p["candles"][-1] and
                         pd.Timestamp(p["candles"][-1]["time"], unit="s", tz="UTC").isoformat())

    def test_coingecko_fallback_is_labelled_and_has_no_volume(self):
        self.fetch.return_value = make_candles(source="coingecko", close_only=True)
        r = self.get("/api/coins/BTCUSDT/candles")
        self.assertEqual(r.status_code, 200)
        p = r.json()
        self.assertEqual(p["source"], "coingecko")
        self.assertNotIn("volume", p["candles"][-1])

    def test_candles_are_cached_between_requests(self):
        self.get("/api/coins/BTCUSDT/candles"); self.get("/api/coins/BTCUSDT/candles?limit=100")
        self.assertEqual(self.fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
