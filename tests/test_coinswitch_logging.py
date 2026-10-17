"""pipeline.log_coinswitch + ticks table migration. Temp DB, no network."""
import os, sqlite3, tempfile, unittest
from unittest import mock
import config
_REAL = config.LOG_PATH
config.LOG_PATH = os.path.join(tempfile.mkdtemp(), "import.log")
import pandas as pd                                                    # noqa: E402
import coinswitch_client as cs, db, pipeline                            # noqa: E402
config.LOG_PATH = _REAL

TICK = {"symbol": "BTC/INR", "exchange": "coinswitchx", "last": 6_900_000.0, "bid": 6_895_000.0, "ask": 6_905_000.0,
        "spread": 10_000 / 6_900_000, "at_ms": 1_700_000_000_000, "pct_change_24h": -0.4}


class LogCoinSwitch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        for p in (mock.patch.object(config, "DB_PATH", os.path.join(tmp, "t.db")),
                  mock.patch.object(config, "LOG_PATH", os.path.join(tmp, "app.log")),
                  mock.patch.dict(os.environ, {"COINSWITCH_API_KEY": "k", "COINSWITCH_SECRET_KEY": "s"})):
            p.start(); self.addCleanup(p.stop)

    def ticks(self):
        return db.read("coinswitch_ticks")

    def test_logs_real_quote_with_bid_ask_and_exchange(self):
        with mock.patch.object(cs, "is_listed", return_value=True), mock.patch.object(cs, "ticker", return_value=TICK):
            pipeline.log_coinswitch("BTCUSDT")
        t = self.ticks()
        self.assertEqual(len(t), 1)
        r = t.iloc[0]
        self.assertEqual((r["pair"], r["price"], r["bid"], r["ask"], r["exchange"]), ("BTC/INR", 6_900_000.0, 6_895_000.0, 6_905_000.0, "coinswitchx"))

    def test_unlisted_pair_is_skipped_not_guessed(self):
        with mock.patch.object(cs, "is_listed", return_value=False), mock.patch.object(cs, "ticker") as tk, \
                self.assertLogs("predictor", "WARNING") as cm:
            pipeline.log_coinswitch("SOLUSDT")
        tk.assert_not_called()
        self.assertEqual(len(self.ticks()), 0)
        self.assertIn("not in CoinSwitch's list", "\n".join(cm.output))

    def test_no_keys_means_nothing_happens(self):
        with mock.patch.dict(os.environ, {"COINSWITCH_API_KEY": ""}), mock.patch.object(cs, "is_listed") as il:
            pipeline.log_coinswitch("BTCUSDT")
        il.assert_not_called()

    def test_api_failures_are_logged_safely_and_never_raise(self):
        for exc in (cs.CoinSwitchError("rate_limited", "HTTP 429: rate limit exceeded, back off", 429), RuntimeError("secret-xyz")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(cs, "is_listed", side_effect=exc), \
                    self.assertLogs("predictor", "WARNING") as cm:
                pipeline.log_coinswitch("BTCUSDT")
            self.assertNotIn("secret-xyz", "\n".join(cm.output))
        self.assertEqual(len(self.ticks()), 0)

    def test_missing_ticker_is_logged(self):
        with mock.patch.object(cs, "is_listed", return_value=True), mock.patch.object(cs, "ticker", return_value=None), \
                self.assertLogs("predictor", "WARNING"):
            pipeline.log_coinswitch("BTCUSDT")
        self.assertEqual(len(self.ticks()), 0)

    def test_config_points_at_inr_pairs(self):
        self.assertEqual(config.COINSWITCH_PAIRS, {"BTCUSDT": "BTC/INR", "ETHUSDT": "ETH/INR", "SOLUSDT": "SOL/INR"})


class Migration(unittest.TestCase):
    def test_old_ticks_table_gains_columns_and_keeps_rows(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE coinswitch_ticks(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, pair TEXT, price REAL, raw TEXT)")
        c.execute("INSERT INTO coinswitch_ticks(ts,symbol,pair,price,raw) VALUES('t0','BTCUSDT','BTC/USDT',1.0,'{}')")
        c.commit(); c.close()
        with mock.patch.object(config, "DB_PATH", path):
            db.add_tick(("t1", "BTCUSDT", "BTC/INR", 2.0, "{}", 1.9, 2.1, "coinswitchx"))
            db.add_tick(("t2", "BTCUSDT", "BTC/INR", 3.0, "{}"))                      # older 5-field callers still work
            t = db.read("coinswitch_ticks")
            db.add_tick(("t3", "ETHUSDT", "ETH/INR", 4.0, "{}", None, None, None))     # running migration twice is harmless
        self.assertEqual(len(t), 3)
        self.assertTrue({"bid", "ask", "exchange"} <= set(t.columns))
        self.assertTrue(pd.isna(t.iloc[0]["bid"]))
        self.assertEqual(t.iloc[1]["ask"], 2.1)


if __name__ == "__main__":
    unittest.main()
