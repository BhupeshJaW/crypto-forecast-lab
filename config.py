SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]        # add more Binance symbols here
COINGECKO_IDS = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana"}  # fallback source
# CoinSwitch INR pairs (exchange "coinswitchx" per CoinSwitch's docs). Whether each pair is really listed is checked at
# run time against CoinSwitch's own /coins list; a pair that is not listed is skipped, never guessed.
COINSWITCH_PAIRS = {"BTCUSDT": "BTC/INR", "ETHUSDT": "ETH/INR", "SOLUSDT": "SOL/INR"}
REFERENCE_SYMBOL = "BTCUSDT"   # used as a cross-coin feature for the other coins
INTERVAL = "1h"
CANDLES = 4000                 # ~5.5 months of hourly data (more history = steadier models)
FEATURE_VERSION = 2            # bump to force every model to retrain after feature changes
RETRAIN_EVERY_HOURS = 24
SWITCH_MARGIN = 0.01           # switch model type only if >=1% better CV error than current one
DB_PATH = "data/tracker_v2.db"
MODEL_DIR = "models"
LOG_PATH = "logs/app.log"

# ---- Paper trading (simulated money) ----
PAPER_START_BALANCE = 10000.0   # USDT
FEE_RATE = 0.001                # per side (Binance spot default 0.1%). Check CoinSwitch's own fee.
SLIPPAGE = 0.0005               # per side, price moves against you
TDS_RATE = 0.0                  # set 0.01 to mimic India's 1% TDS on sells (verify current rules)
ENTRY_THRESHOLD = 0.003         # buy only if predicted next-hour return >= 0.3% (about the round-trip cost)
EXIT_THRESHOLD = 0.0            # sell on signal only when prediction turns negative (stops constant buy/sell churn)
MIN_HOLD_HOURS = 3              # signal exits wait this long (stop-loss / take-profit still act at once)
POSITION_FRACTION = 0.20        # max share of equity per coin
MAX_EXPOSURE = 0.60             # max share of equity invested at once
STOP_LOSS = 0.02                # exit if price falls 2% below entry
TAKE_PROFIT = 0.03              # exit if price rises 3% above entry
MAX_DAILY_LOSS = 0.03           # no new buys for the rest of the UTC day after a 3% equity drop

# ---- Alerts, health checks, backups ----
ALERT_DRAWDOWN = 0.05          # alert if paper account is 5% below its peak
HEALTH_MAX_AGE_HOURS = 3       # healthcheck fails if no successful cycle for this long
BACKUP_DIR = "backups"
BACKUPS_KEEP = 14

# ---- Honest accuracy checks ----
MIN_RESOLVED_FOR_VERDICT = 30   # below this many checked predictions the dashboard says "too early to tell"
TRADE_ONLY_WITH_EDGE = True     # paper trading opens new trades only when the model beat "price stays the same" in validation

# ---- Signal engine and data-safety guards ----
MAX_DATA_AGE_HOURS = 3         # candle older than this (since it closed) = stale -> NO TRADE, no prediction
MAX_VOL_REGIME = 2.5           # short-term volatility more than 2.5x its 3-day level = abnormal -> NO TRADE
MIN_NET_EDGE = 0.002           # BUY needs predicted return minus round-trip costs >= 0.2% (ENTRY_THRESHOLD alone only breaks even)
MIN_REWARD_RISK = 1.2          # take-profit distance / stop-loss distance must be at least this
SIGNAL_HORIZON_HOURS = 1
HOLDOUT_FRAC = 0.20            # last 20% of history is never used for choosing a model; it gives the honest score
HOLDOUT_GAP = 6                # candles skipped between selection data and holdout
