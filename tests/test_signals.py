import unittest, math
from datetime import datetime, timezone
import config, signals

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
GOOD = {"conf": "medium", "n": 800, "mae": 0.003, "vol_regime": 1.0}

def sig(pred=0.006, price=100.0, info=GOOD, age=0.5, held=False, source="binance"):
    return signals.build_signal("BTCUSDT", price, pred, info, age, held=held, now=NOW, source=source)

class SignalRules(unittest.TestCase):
    def test_buy_when_edge_beats_costs_and_grade_ok(self):
        s = sig()
        self.assertEqual(s["signal"], "BUY")
        self.assertLess(s["stop_loss"], s["reference_price"])
        self.assertGreater(s["take_profit"], s["reference_price"])
        self.assertGreaterEqual(s["reward_to_risk"], config.MIN_REWARD_RISK)
        self.assertGreater(s["net_edge_after_costs_pct"], 0)
        self.assertEqual(s["expires_at"][:13], "2026-10-17T13")

    def test_low_grade_never_buys(self):
        s = sig(info={**GOOD, "conf": "low"})
        self.assertEqual(s["signal"], "NO_TRADE")
        self.assertTrue(s["blockers"])

    def test_stale_data_blocks_everything(self):
        for held in (False, True):
            self.assertEqual(sig(age=config.MAX_DATA_AGE_HOURS + 0.1, held=held)["signal"], "NO_TRADE")
        self.assertEqual(sig(age=None)["signal"], "NO_TRADE")

    def test_fallback_source_blocks(self):
        self.assertEqual(sig(source="coingecko")["signal"], "NO_TRADE")

    def test_abnormal_volatility_blocks(self):
        self.assertEqual(sig(info={**GOOD, "vol_regime": 3.0})["signal"], "NO_TRADE")

    def test_nan_and_bad_price_block(self):
        self.assertEqual(sig(pred=float("nan"))["signal"], "NO_TRADE")
        self.assertEqual(sig(price=0)["signal"], "NO_TRADE")

    def test_edge_equal_to_costs_is_not_enough(self):
        cost = signals.round_trip_cost()
        s = sig(pred=cost + 0.0005)          # above cost but below MIN_NET_EDGE
        self.assertNotEqual(s["signal"], "BUY")

    def test_sell_distinguishes_exit_from_bearish(self):
        self.assertEqual(sig(pred=-0.004, held=True)["sell_type"], "exit_position")
        s = sig(pred=-0.004, held=False)
        self.assertEqual((s["signal"], s["sell_type"]), ("SELL", "bearish_not_held"))

    def test_held_position_with_low_grade_just_holds(self):
        s = sig(pred=-0.01, held=True, info={**GOOD, "conf": "low"})
        self.assertEqual(s["signal"], "HOLD")

    def test_small_forecast_is_hold(self):
        self.assertEqual(sig(pred=0.0005)["signal"], "HOLD")

    def test_no_price_is_presented_as_coinswitch(self):
        s = sig()
        self.assertEqual(s["price_source"], "binance_usdt_close")
        self.assertIn("NOT a CoinSwitch", s["price_note"])

    def test_alert_text_has_required_fields(self):
        t = signals.alert_text(sig())
        for word in ("BUY", "Stop-loss", "Target", "Expires"):
            self.assertIn(word, t)

class Confidence(unittest.TestCase):
    def test_small_sample_cannot_earn_trust(self):
        import model
        self.assertEqual(model.confidence(0.99, 1.0, 0.53, n=150), "low")        # 53% over 150 hours = luck
        self.assertIn(model.confidence(0.99, 1.0, 0.53, n=20000), ("medium", "high"))
        self.assertEqual(model.confidence(1.01, 1.0, 0.60, n=20000), "low")      # worse than naive error
if __name__ == "__main__":
    unittest.main()
