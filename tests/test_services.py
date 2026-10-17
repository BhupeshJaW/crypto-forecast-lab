import json, os, tempfile, unittest
import numpy as np, pandas as pd
import config, db, services, signals
from tests.test_model_safety import fake_candles

class Services(unittest.TestCase):
    def setUp(self):
        self.old = (config.DB_PATH, config.LOG_PATH)
        d = tempfile.mkdtemp()
        config.DB_PATH, config.LOG_PATH = os.path.join(d, "t.db"), os.path.join(d, "app.log")

    def tearDown(self):
        config.DB_PATH, config.LOG_PATH = self.old

    def test_empty_database_is_handled(self):
        self.assertTrue(all(not f["available"] for f in services.latest_forecasts()))
        self.assertTrue(all(s["signal"] is None for s in services.latest_signals()))
        self.assertFalse(services.backtest_report()["available"])
        p = services.paper_portfolio()
        self.assertEqual(p["trades"], 0)
        self.assertFalse(p["statistically_conclusive"])
        self.assertEqual(services.health()["status"], "degraded")

    def test_unknown_symbol_rejected(self):
        with self.assertRaises(KeyError):
            services.check_symbol("DOGEUSDT; DROP TABLE")

    def test_signal_roundtrip_and_nan_clean(self):
        s = signals.build_signal("BTCUSDT", 100.0, 0.006, {"conf": "medium", "n": 800, "mae": 0.003, "vol_regime": 1.0}, 0.5)
        db.add_signal("BTCUSDT", "2026-10-17T13:00:00+00:00", "x", s["signal"], signals.to_json(s))
        got = services.latest_signals()[0]
        self.assertEqual(got["signal"], "BUY")
        self.assertIsNone(services.clean(float("nan")))
        json.dumps(services.clean({"a": np.float64("inf"), "b": np.int64(3)}))

    def test_accuracy_needs_enough_samples(self):
        a = services.accuracy("BTCUSDT")
        self.assertEqual(a["verdict"], "too early to tell")

    def test_paper_flags_few_trades(self):
        db.add_paper_trade({"symbol": "BTCUSDT", "entry_time": "a", "exit_time": "b", "entry_price": 1, "exit_price": 2,
                            "qty": 1, "fees": 0.1, "pnl": 0.9, "pnl_pct": 0.9, "reason": "take_profit", "hold_hours": 2})
        db.add_equity("2026-10-17T10:00:00+00:00", 9000, 10000, 10000, 1)
        db.add_equity("2026-10-17T11:00:00+00:00", 9000, 9500, 10000, 1)
        p = services.paper_portfolio()
        self.assertEqual(p["trades"], 1)
        self.assertIn("inconclusive", p["note"])
        self.assertAlmostEqual(p["max_drawdown_pct"], -5.0)

    def test_candles_payload_has_source_age_and_indicators(self):
        df = fake_candles(400)
        df["ts"] = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1), periods=400, freq="h")
        df.attrs["source"] = "binance"
        out = services.candles_payload("BTCUSDT", df, 100)
        self.assertEqual(len(out["candles"]), 100)
        self.assertIn("not live", out["note"].lower())
        self.assertIn(out["regime"], ("bullish", "bearish", "sideways"))
        last = out["candles"][-1]
        for k in ("rsi14", "macd", "bb_up", "sma50"):
            self.assertIsNotNone(last[k])
        self.assertTrue(0 <= last["rsi14"] <= 100)

    def test_alert_config_never_contains_secrets(self):
        os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = "SECRET_TOKEN_123", "999"
        try:
            self.assertNotIn("SECRET_TOKEN_123", json.dumps(services.alert_config()))
            self.assertNotIn("SECRET_TOKEN_123", json.dumps(services.health()))
        finally:
            del os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
if __name__ == "__main__":
    unittest.main()
