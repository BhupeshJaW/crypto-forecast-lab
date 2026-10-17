"""CoinSwitch client: signing against the documented example, read-only guarantees, response parsing, safe errors. No network."""
import inspect, os, re, tempfile, unittest
from unittest import mock
import config
_REAL = config.LOG_PATH
config.LOG_PATH = os.path.join(tempfile.mkdtemp(), "import.log")
import pandas as pd, requests                                           # noqa: E402
from cryptography.hazmat.primitives import serialization               # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519          # noqa: E402
import coinswitch_client as cs                                         # noqa: E402
config.LOG_PATH = _REAL

_KEY = ed25519.Ed25519PrivateKey.generate()
SECRET = _KEY.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()
PUBLIC = _KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
NOW = 1_719_905_777_483


class Resp:
    def __init__(self, payload=None, status=200, bad_json=False):
        self.status_code, self._p, self._bad = status, payload, bad_json
    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._p


class Base(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"COINSWITCH_API_KEY": PUBLIC, "COINSWITCH_SECRET_KEY": SECRET, "COINSWITCH_EXCHANGE": "coinswitchx"})
        env.start(); self.addCleanup(env.stop)
        for p in (mock.patch.object(cs, "_now_ms", return_value=NOW), mock.patch.object(cs, "_sleep")):
            p.start(); self.addCleanup(p.stop)
        cs._LISTED.clear(); self.addCleanup(cs._LISTED.clear)

    def serve(self, *responses):
        """Patch requests.get to return the given responses (or raise exceptions) in order."""
        m = mock.patch.object(cs.requests, "get", side_effect=list(responses))
        mg = m.start(); self.addCleanup(m.stop)
        return mg


class Signing(Base):
    def test_matches_the_documented_example_message(self):
        # CoinSwitch docs: GET /trade/api/v2/orders?open=true&exchanges=coinswitchx,c2c1 at epoch 1719905777483
        headers, path = cs._sign("GET", "/trade/api/v2/orders", {"open": "true", "exchanges": "coinswitchx,c2c1"})
        self.assertEqual(path, "/trade/api/v2/orders?open=true&exchanges=coinswitchx,c2c1")
        expected = "GET/trade/api/v2/orders?open=true&exchanges=coinswitchx,c2c11719905777483"
        _KEY.public_key().verify(bytes.fromhex(headers["X-AUTH-SIGNATURE"]), expected.encode())     # raises if wrong
        self.assertEqual(headers["X-AUTH-EPOCH"], str(NOW))
        self.assertEqual(headers["X-AUTH-APIKEY"], PUBLIC)
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_documented_time_example(self):
        headers, _ = cs._sign("GET", "/trade/api/v2/time")
        _KEY.public_key().verify(bytes.fromhex(headers["X-AUTH-SIGNATURE"]), b"GET/trade/api/v2/time1719905777483")

    def test_symbol_slash_and_comma_are_signed_decoded(self):
        headers, path = cs._sign("GET", cs.PATH_TICKER, {"exchange": "coinswitchx,c2c1", "symbol": "BTC/INR"})
        self.assertIn("symbol=BTC/INR", path)
        self.assertNotIn("%2F", path); self.assertNotIn("%2C", path)

    def test_bad_secret_is_a_config_error_without_leaking_it(self):
        with mock.patch.dict(os.environ, {"COINSWITCH_SECRET_KEY": "not-hex-SECRETVALUE"}):
            with self.assertRaises(cs.CoinSwitchError) as cm:
                cs._sign("GET", cs.PATH_COINS)
        self.assertEqual(cm.exception.kind, "config")
        self.assertNotIn("SECRETVALUE", str(cm.exception))


class ReadOnlyGuarantees(Base):
    def test_only_get_requests_to_allow_listed_paths(self):
        src = inspect.getsource(cs)
        self.assertIsNone(re.search(r"requests\.(post|put|patch|delete)\b", src))
        for p in cs.ALLOWED_GET_PATHS:
            self.assertNotIn("order", p.lower())
            self.assertNotIn("transfer", p.lower())
        self.assertEqual(sorted(cs.ALLOWED_GET_PATHS), sorted(["/trade/api/v2/coins", "/trade/api/v2/tradingFee",
                                                              "/trade/api/v2/candles", "/trade/api/v2/24hr/ticker"]))

    def test_other_paths_are_refused_before_any_network_call(self):
        g = self.serve()
        for p in ("/trade/api/v2/order", "/trade/api/v2/orders", "/trade/api/v2/user/portfolio", "/trade/api/v2/tds",
                  "/trade/api/v2/futures/order", "/dma/api/v1/transfer", "/anything"):
            with self.subTest(path=p), self.assertRaises(ValueError):
                cs._get(p)
        g.assert_not_called()

    def test_no_public_function_can_place_or_cancel_orders(self):
        names = [n.lower() for n, _ in inspect.getmembers(cs, inspect.isfunction)]
        for bad in ("order", "buy", "sell", "cancel", "transfer", "withdraw", "place"):
            self.assertFalse([n for n in names if bad in n], bad)

    def test_requests_use_get_with_timeout_and_decoded_path(self):
        g = self.serve(Resp({"data": {"coinswitchx": ["BTC/INR"]}}))
        cs.active_coins()
        args, kw = g.call_args
        self.assertEqual(args[0], "https://coinswitch.co/trade/api/v2/coins?exchange=coinswitchx")
        self.assertEqual(kw["timeout"], cs.TIMEOUT)

    def test_not_configured_means_no_request(self):
        g = self.serve()
        with mock.patch.dict(os.environ, {"COINSWITCH_API_KEY": ""}):
            self.assertFalse(cs.enabled())
            with self.assertRaises(cs.CoinSwitchError) as cm:
                cs.active_coins()
        self.assertEqual(cm.exception.kind, "config")
        g.assert_not_called()


class Parsing(Base):
    def test_active_coins_and_is_listed(self):
        g = self.serve(Resp({"data": {"coinswitchx": ["BAT/INR", "BTC/INR", "ETH/INR"]}}))
        self.assertEqual(cs.active_coins(), ["BAT/INR", "BTC/INR", "ETH/INR"])
        g2 = self.serve(Resp({"data": {"coinswitchx": ["BTC/INR", "ETH/INR"]}}))
        self.assertTrue(cs.is_listed("BTC/INR"))
        self.assertFalse(cs.is_listed("SOL/INR"))           # not in CoinSwitch's own list: never assumed
        self.assertEqual(g2.call_count, 1)                  # cached
    def test_active_coins_bad_shape(self):
        self.serve(Resp({"data": {"other": []}}))
        with self.assertRaises(cs.CoinSwitchError) as cm:
            cs.active_coins()
        self.assertEqual(cm.exception.kind, "unexpected_response")

    DOC_TICKER = {"data": {"WAVES/INR": {"symbol": "WAVES/INR", "openPrice": "127.65", "lowPrice": "125.53", "highPrice": "129.88",
                                         "lastPrice": "125.56", "baseVolume": "1910.65", "quoteVolume": "240593.58",
                                         "percentageChange": "-1.63728946337642", "bidPrice": "125.56", "askPrice": "127.29",
                                         "at": NOW - 5000}}}

    def test_ticker_from_documented_sample(self):
        self.serve(Resp(self.DOC_TICKER))
        t = cs.ticker("WAVES/INR")
        self.assertEqual((t["last"], t["bid"], t["ask"]), (125.56, 125.56, 127.29))
        self.assertAlmostEqual(t["spread"], (127.29 - 125.56) / ((127.29 + 125.56) / 2))
        self.assertAlmostEqual(t["age_seconds"], 5.0)
        self.assertEqual(t["source"], "coinswitch_ticker")
        self.assertEqual(t["exchange"], "coinswitchx")

    def test_ticker_missing_symbol_is_none(self):
        self.serve(Resp({"data": {}}))
        self.assertIsNone(cs.ticker("SOL/INR"))

    def test_crossed_or_zero_quote_gives_no_spread(self):
        for bid, ask in (("130", "127"), ("0", "127"), ("abc", "127")):
            with self.subTest(bid=bid, ask=ask):
                d = {"data": {"X/INR": {"lastPrice": "1", "bidPrice": bid, "askPrice": ask}}}
                self.serve(Resp(d))
                t = cs.ticker("X/INR")
                self.assertEqual((t["bid"], t["ask"], t["spread"]), (None, None, None))
                self.assertEqual(t["last"], 1.0)

    def test_ticker_without_valid_last_price_raises(self):
        self.serve(Resp({"data": {"X/INR": {"lastPrice": "nan", "bidPrice": "1", "askPrice": "2"}}}))
        with self.assertRaises(cs.CoinSwitchError):
            cs.ticker("X/INR")

    def test_trading_fee_uses_after_discount_and_skips_malformed_rows(self):
        d = {"data": {"coinswitchx": {"BTC": {"maker_fee": 0.0009, "taker_fee": 0.0009, "maker_fee_after_discount": 0,
                                              "taker_fee_after_discount": 0.0005, "maker_discount_percentage": 100},
                                      "ETH": {"maker_fee": "bad"}, "XRP": {"maker_fee": 5, "taker_fee": 5,
                                                                          "maker_fee_after_discount": 5, "taker_fee_after_discount": 5}}}}
        self.serve(Resp(d))
        f = cs.trading_fee()
        self.assertEqual(list(f), ["BTC"])
        self.assertEqual((f["BTC"]["maker"], f["BTC"]["taker"], f["BTC"]["taker_base"]), (0, 0.0005, 0.0009))

    def test_candles_from_documented_sample_drops_open_candle(self):
        closed = {"o": "1591001.0", "h": "1610988.0", "l": "1588000.0", "c": "1591000.0", "interval": "60", "symbol": "BTC/INR",
                  "close_time": str(NOW - 1000), "volume": "0.30468", "start_time": str(NOW - 3_601_000)}
        still_open = dict(closed, start_time=str(NOW - 1_800_000), close_time=str(NOW + 1_800_000))
        broken = dict(closed, h="oops", start_time=str(NOW - 7_201_000), close_time=str(NOW - 3_700_000))
        self.serve(Resp({"data": [still_open, closed, closed, broken]}))
        df = cs.candles("BTC/INR", 60, NOW - 10_000_000, NOW)
        self.assertEqual(len(df), 1)                         # open candle dropped, duplicate removed, broken row ignored
        self.assertEqual(df.loc[0, "close"], 1591000.0)
        self.assertEqual(df.loc[0, "ts"], pd.Timestamp(NOW - 3_601_000, unit="ms", tz="UTC"))
        self.assertEqual(df.attrs["source"], "coinswitch_inr")
        self.assertEqual(list(df.columns), ["ts", "open", "high", "low", "close", "volume", "close_time"])

    def test_usdt_candles_are_not_labelled_inr(self):
        self.serve(Resp({"data": []}))
        self.assertEqual(cs.candles("BTC/USDT", 60, 0, NOW, exchange="c2c1").attrs["source"], "coinswitch")

    def test_candles_history_pages_in_chunks(self):
        self.serve(*[Resp({"data": []}) for _ in range(3)])
        g = cs.requests.get
        cs.candles_history("BTC/INR", hours=2500, chunk=1000)       # 2500 h -> 3 requests of <=1000 candles
        self.assertEqual(g.call_count, 3)
        starts = [re.search(r"start_time=(\d+)", c.args[0]).group(1) for c in g.call_args_list]
        self.assertEqual(len(set(starts)), 3)


class Errors(Base):
    def message_is_clean(self, exc):
        text = str(exc)
        for secret in (SECRET, PUBLIC, "coinswitch.co", "X-AUTH", "http"):
            self.assertNotIn(secret, text)

    def test_http_statuses_map_to_kinds_without_leaking(self):
        for status, kind in ((401, "auth"), (403, "auth"), (429, "rate_limited"), (422, "bad_request")):
            with self.subTest(status=status):
                self.serve(Resp({"message": "Input symbol is missing"}, status=status))
                with self.assertRaises(cs.CoinSwitchError) as cm:
                    cs.active_coins()
                self.assertEqual((cm.exception.kind, cm.exception.status), (kind, status))
                self.message_is_clean(cm.exception)

    def test_429_is_not_retried(self):
        g = self.serve(Resp({}, status=429), Resp({"data": {"coinswitchx": []}}))
        with self.assertRaises(cs.CoinSwitchError):
            cs.active_coins()
        self.assertEqual(g.call_count, 1)

    def test_network_error_is_retried_once_then_reported_safely(self):
        g = self.serve(requests.ConnectTimeout("boom https://coinswitch.co/?k=" + PUBLIC), requests.ConnectionError("again"))
        with self.assertRaises(cs.CoinSwitchError) as cm:
            cs.active_coins()
        self.assertEqual((cm.exception.kind, g.call_count), ("network", 2))
        self.message_is_clean(cm.exception)
        self.assertIn("ConnectionError", str(cm.exception))

    def test_5xx_then_success_uses_a_fresh_signature_each_attempt(self):
        g = self.serve(Resp({}, status=502), Resp({"data": {"coinswitchx": ["BTC/INR"]}}))
        with mock.patch.object(cs, "_now_ms", side_effect=[NOW, NOW + 1500]):
            self.assertEqual(cs.active_coins(), ["BTC/INR"])
        epochs = [c.kwargs["headers"]["X-AUTH-EPOCH"] for c in g.call_args_list]
        self.assertEqual(epochs, [str(NOW), str(NOW + 1500)])

    def test_non_json_and_missing_data_field(self):
        self.serve(Resp(bad_json=True))
        with self.assertRaises(cs.CoinSwitchError) as cm:
            cs.active_coins()
        self.assertEqual(cm.exception.kind, "unexpected_response")
        self.serve(Resp({"oops": 1}))
        with self.assertRaises(cs.CoinSwitchError):
            cs.active_coins()


if __name__ == "__main__":
    unittest.main()
