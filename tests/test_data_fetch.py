"""data.fetch_prices paging and failure logging, and services.candles fetching only what the chart needs. No network."""
import os, tempfile, unittest
from unittest import mock
import config
_REAL = config.LOG_PATH
config.LOG_PATH = os.path.join(tempfile.mkdtemp(), "import.log")      # logger is created at import; keep tests off the real log
import pandas as pd, requests                                          # noqa: E402
import data, services                                                  # noqa: E402
from tests.test_model_safety import fake_candles                       # noqa: E402
config.LOG_PATH = _REAL
H = 3_600_000
SECRET_URL = "https://api.binance.com/api/v3/klines?apikey=LEAK"


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom " + SECRET_URL, response=self)
    def json(self):
        return self._p


def fake_binance(calls):
    """Serves hourly klines like Binance: newest `limit` rows ending at endTime (or 'now')."""
    last_open = int(pd.Timestamp.now(tz="UTC").floor("h").timestamp() * 1000)
    def get(url, params=None, timeout=None):
        calls.append(dict(params or {}, url=url))
        end = params.get("endTime", last_open + H - 1)
        top = min(last_open, (end // H) * H)
        rows = [[top - (params["limit"] - 1 - i) * H, "1", "2", "0.5", "1.5", "10", 0, "0", 5, "3", "0", "0"]
                for i in range(params["limit"])]
        return FakeResp(rows)
    return get


class Fetch(unittest.TestCase):
    def test_n_limits_what_is_requested(self):
        calls = []
        with mock.patch.object(data.requests, "get", fake_binance(calls)):
            df = data.fetch_prices("BTCUSDT", 150)
        self.assertEqual([c["limit"] for c in calls], [150])
        self.assertEqual(len(df), 149)                         # the in-progress candle is dropped
        self.assertEqual(df.attrs["source"], "binance")

    def test_default_still_pages_the_full_history(self):
        calls = []
        with mock.patch.object(config, "CANDLES", 2500), mock.patch.object(data.requests, "get", fake_binance(calls)):
            df = data.fetch_prices("BTCUSDT")
        self.assertEqual([c["limit"] for c in calls], [1000, 1000, 500])
        self.assertEqual(len(df), 2499)
        self.assertTrue(df["ts"].is_monotonic_increasing)

    def test_failure_is_logged_with_reason_but_not_url_and_falls_back(self):
        def get(url, params=None, timeout=None):
            if "binance" in url:
                raise requests.ReadTimeout("read timed out " + SECRET_URL)
            return FakeResp({"prices": [[1_700_000_000_000 + i * H, 100.0 + i] for i in range(200)]})
        with mock.patch.object(data.requests, "get", get), self.assertLogs("predictor", "WARNING") as cm:
            df = data.fetch_prices("BTCUSDT", 150)
        line = "\n".join(cm.output)
        self.assertIn("ReadTimeout", line)
        self.assertNotIn("LEAK", line)
        self.assertNotIn("https://", line)
        self.assertEqual(df.attrs["source"], "coingecko")

    def test_http_status_is_in_the_reason(self):
        def get(url, params=None, timeout=None):
            if "binance" in url:
                return FakeResp([], status=451)
            return FakeResp({"prices": [[1_700_000_000_000 + i * H, 1.0] for i in range(10)]})
        with mock.patch.object(data.requests, "get", get), self.assertLogs("predictor", "WARNING") as cm:
            data.fetch_prices("BTCUSDT", 150)
        self.assertIn("HTTPError, HTTP 451", "\n".join(cm.output))


class ChartFetchSize(unittest.TestCase):
    def setUp(self):
        services._CACHE.clear(); self.addCleanup(services._CACHE.clear)

    def frame(self, n):
        df = fake_candles(n)
        df["ts"] = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1), periods=n, freq="h")
        df.attrs["source"] = "binance"
        return df

    def test_chart_requests_limit_plus_warmup_and_reuses_the_cache(self):
        with mock.patch.object(data, "fetch_prices", side_effect=lambda s, n=None: self.frame(n)) as f:
            p = services.candles("BTCUSDT", 300)
            self.assertEqual(f.call_args.args, ("BTCUSDT", 400))
            self.assertEqual(len(p["candles"]), 300)
            self.assertIsNotNone(p["candles"][0]["sma50"])     # warm-up history fills indicators from the first candle
            services.candles("BTCUSDT", 100)                    # smaller request: served from cache
            self.assertEqual(f.call_count, 1)
            services.candles("BTCUSDT", 1000)                   # bigger than cached: fetched again, 2 pages at most
            self.assertEqual(f.call_args.args, ("BTCUSDT", 1100))
            self.assertEqual(f.call_count, 2)


if __name__ == "__main__":
    unittest.main()
