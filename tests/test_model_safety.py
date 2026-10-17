import os, tempfile, unittest
import numpy as np, pandas as pd
import config, db, model

def fake_candles(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    vol = rng.uniform(50, 150, n)
    return pd.DataFrame({"ts": ts, "open": close, "high": close * 1.002, "low": close * 0.998, "close": close,
                         "volume": vol, "trades": rng.uniform(100, 300, n), "taker_buy": vol * rng.uniform(.4, .6, n)})

class NoLookahead(unittest.TestCase):
    def test_features_at_t_ignore_the_future(self):
        df, ref = fake_candles(), fake_candles(seed=1)
        full, feats = model.make_features(df, ref)
        cut = 1200
        part, _ = model.make_features(df.iloc[:cut].copy(), ref.iloc[:cut].copy())
        a = full.iloc[:cut][feats].reset_index(drop=True)
        b = part[feats].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-12)

    def test_target_is_next_hour_return(self):
        df = fake_candles()
        d, _ = model.make_features(df)
        i = 700
        self.assertAlmostEqual(d["target"].iloc[i], df["close"].iloc[i + 1] / df["close"].iloc[i] - 1, places=12)

class TrainPredict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = (config.DB_PATH, config.MODEL_DIR, model.candidates)
        config.DB_PATH, config.MODEL_DIR = os.path.join(self.tmp, "t.db"), os.path.join(self.tmp, "m")
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        model.candidates = lambda: {"ridge": make_pipeline(StandardScaler(), Ridge(alpha=100.0))}

    def tearDown(self):
        config.DB_PATH, config.MODEL_DIR, model.candidates = self.old

    def test_train_stores_holdout_and_predicts(self):
        df = fake_candles(2000)
        model.train("TESTUSDT", df)
        runs = db.read("model_runs")
        self.assertEqual(len(runs), 1)
        self.assertGreaterEqual(int(runs["holdout_n"].iloc[0]), 300)
        tt, base, pred, ret, ver, name, info = model.predict_next("TESTUSDT", df)
        self.assertTrue(np.isfinite(ret))
        self.assertEqual(info["conf"], "low")      # pure random walk: must NOT earn trust

    def test_missing_volume_features_raise_instead_of_zero_fill(self):
        df = fake_candles(2000)
        model.train("TESTUSDT", df)
        with self.assertRaises(ValueError):
            model.predict_next("TESTUSDT", df[["ts", "close"]])

class DbSignals(unittest.TestCase):
    def test_signal_dedupe(self):
        old = config.DB_PATH
        config.DB_PATH = os.path.join(tempfile.mkdtemp(), "s.db")
        try:
            self.assertTrue(db.add_signal("BTCUSDT", "2026-10-17T13:00:00+00:00", "x", "BUY", "{}"))
            self.assertFalse(db.add_signal("BTCUSDT", "2026-10-17T13:00:00+00:00", "x", "BUY", "{}"))
        finally:
            config.DB_PATH = old
if __name__ == "__main__":
    unittest.main()
