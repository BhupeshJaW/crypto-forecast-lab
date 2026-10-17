import os, joblib, numpy as np, pandas as pd
from datetime import datetime, timezone
from sklearn.base import clone
from sklearn.ensemble import (ExtraTreesRegressor, GradientBoostingRegressor,
                              HistGradientBoostingRegressor, RandomForestRegressor, VotingRegressor)
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import config, db, alerts
from logger import get_logger
log = get_logger()

def make_features(df, ref=None):
    d = df.copy()
    c = d["close"]
    d["r"] = c.pct_change()
    for i in range(1, 7):
        d[f"lag{i}"] = d["r"].shift(i - 1)
    for h in (3, 12, 24, 48):                       # momentum over longer windows
        d[f"ret{h}"] = c.pct_change(h)
    for w in (6, 24, 72, 168):                      # distance from moving averages (incl. 1 week)
        d[f"ma{w}"] = c / c.rolling(w).mean() - 1
    d["vol12"], d["vol24"], d["vol72"] = (d["r"].rolling(w).std() for w in (12, 24, 72))
    d["vol_regime"] = d["vol12"] / d["vol72"]       # calm vs stormy market right now
    d["z1"] = d["r"] / d["vol24"]                   # last move measured in "normal moves" for this coin
    delta = c.diff()
    for n in (7, 14):
        up, dn = delta.clip(lower=0).rolling(n).mean(), (-delta.clip(upper=0)).rolling(n).mean()
        d[f"rsi{n}"] = (100 - 100 / (1 + up / dn.replace(0, np.nan))) / 100
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    d["macd_hist"] = (macd - macd.ewm(span=9).mean()) / c
    d["bb_pos"] = (c - c.rolling(20).mean()) / (2 * c.rolling(20).std())
    d["dist_hi24"] = c / c.rolling(24).max() - 1
    d["dist_lo24"] = c / c.rolling(24).min() - 1
    if "volume" in d and d["volume"].notna().all():
        d["range"] = (d["high"] - d["low"]) / c
        d["atr14"] = d["range"].rolling(14).mean()
        d["vol_ratio"] = d["volume"] / d["volume"].rolling(24).mean()
        d["trades_ratio"] = d["trades"] / d["trades"].rolling(24).mean()
        d["taker_ratio"] = d["taker_buy"] / d["volume"]
        d["taker_ratio6"] = d["taker_ratio"].rolling(6).mean()
    if ref is not None:
        rc = ref.set_index("ts")["close"]
        rr = rc.pct_change()
        d["ref_r0"], d["ref_r1"] = d["ts"].map(rr), d["ts"].map(rr.shift(1))
        d["ref_ret6"] = d["ts"].map(rc.pct_change(6))
    hr = d["ts"].dt.hour
    d["hour_sin"], d["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    d["weekend"] = (d["ts"].dt.dayofweek >= 5).astype(float)
    d["target"] = d["r"].shift(-1)
    skip = {"ts", "open", "high", "low", "close", "volume", "trades", "taker_buy", "r", "target"}
    feats = [x for x in d.columns if x not in skip]
    return d.replace([np.inf, -np.inf], np.nan), feats

def candidates():
    # Shallower, more regularised than before: hourly crypto is mostly noise, so simple models overfit less.
    tree = dict(n_estimators=250, max_depth=4, min_samples_leaf=40, max_features=0.5, random_state=0, n_jobs=-1)
    ridge = lambda: make_pipeline(StandardScaler(), Ridge(alpha=100.0))
    et = lambda: ExtraTreesRegressor(**tree)
    hgb = lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.04, max_iter=150,
                                                min_samples_leaf=40, l2_regularization=2.0, random_state=0)
    return {
        "ridge": ridge(),
        "rf": RandomForestRegressor(**tree),
        "extra_trees": et(),
        "hist_gbm": hgb(),
        "gbm": GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.04, loss="huber",
                                         subsample=0.8, min_samples_leaf=40, random_state=0),
        "ensemble": VotingRegressor([("ridge", ridge()), ("et", et()), ("hgb", hgb())]),
    }

def fit_model(model, X, y):
    """Fit on returns with the most extreme 1% on each side clipped, so a few crash/spike hours
    do not dominate training. Scoring always uses the real, unclipped returns."""
    lo, hi = y.quantile(0.01), y.quantile(0.99)
    return clone(model).fit(X, y.clip(lo, hi))

def confidence(mae, base, dir_acc, n=None):
    """Plain-language trust level: high / medium / low.
    n = number of unseen hours the score is based on. When given, the direction hit-rate must also clear
    a significance bar, because 52% over 150 hours is easily luck (standard error ~4%)."""
    skill = 1 - mae / base if base else 0.0
    if n:
        se = 0.5 / np.sqrt(n)
        hi_dir, mid_dir = 0.5 + 1.64 * se, 0.5 + 1.28 * se
    else:
        hi_dir, mid_dir = 0.54, 0.52
    if skill >= 0.02 and dir_acc >= hi_dir:
        return "high"
    if skill > 0 and dir_acc >= mid_dir:
        return "medium"
    return "low"

def holdout_eval(model, Xd, yd, Xh, yh):
    """Fit on the selection data only, score on the untouched holdout (real, unclipped returns)."""
    p = fit_model(model, Xd, yd).predict(Xh)
    return (float(np.mean(np.abs(p - yh))), float(np.mean(np.sign(p) == np.sign(yh))),
            float(np.mean(np.abs(yh))), int(len(yh)))

def _cv(model, X, y):
    maes, dirs, base = [], [], []
    for tr, te in TimeSeriesSplit(n_splits=5, gap=6).split(X):     # gap: no overlap between train and test
        p = fit_model(model, X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        maes.append(np.mean(np.abs(p - y.iloc[te])))
        dirs.append(np.mean(np.sign(p) == np.sign(y.iloc[te])))
        base.append(np.mean(np.abs(y.iloc[te])))
    return float(np.mean(maes)), float(np.mean(dirs)), float(np.mean(base))

def model_path(symbol):
    return os.path.join(config.MODEL_DIR, f"{symbol}.joblib")

def train(symbol, df, ref=None):
    d, feats = make_features(df, ref)
    d = d.dropna(subset=feats + ["target"])
    X, y = d[feats], d["target"]
    n_h = max(int(len(X) * config.HOLDOUT_FRAC), 300)
    if len(X) < n_h * 3:
        raise ValueError(f"not enough history to train {symbol}: {len(X)} usable rows")
    split = len(X) - n_h
    Xd, yd = X.iloc[:split], y.iloc[:split]                              # used to CHOOSE the model
    Xh, yh = X.iloc[split + config.HOLDOUT_GAP:], y.iloc[split + config.HOLDOUT_GAP:]   # never used to choose
    now = datetime.now(timezone.utc).isoformat()
    scores = {}
    for name, m in candidates().items():
        mae, da, base = _cv(m, Xd, yd)
        scores[name] = (mae, da, base)
        db.add_candidate_score((now, symbol, name, mae, da, base))
        log.info(f"[{symbol}] {name}: cv_mae={mae:.6f} dir_acc={da:.3f} baseline={base:.6f}")
    best = min(scores, key=lambda k: scores[k][0])

    old = joblib.load(model_path(symbol)) if os.path.exists(model_path(symbol)) else None
    champ_mae, switched, chosen, note = None, True, best, "first model"
    if old:
        champ_mae = scores.get(old["name"], (None,))[0]
        if champ_mae is not None and scores[best][0] >= champ_mae * (1 - config.SWITCH_MARGIN):
            chosen, switched, note = old["name"], False, "champion kept (retrained on new data)"
        else:
            note = f"switched {old['name']} -> {best}"
    # Honest score: picking the best of 6 models on the same folds that score them flatters the winner.
    hmae, hdir, hbase, hn = holdout_eval(candidates()[chosen], Xd, yd, Xh, yh)
    conf = confidence(hmae, hbase, hdir, hn)
    version = datetime.now(timezone.utc).strftime("v%Y%m%d_%H%M")
    final = fit_model(candidates()[chosen], X, y)
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    joblib.dump({"model": final, "version": version, "name": chosen, "feats": feats, "fv": config.FEATURE_VERSION,
                 "conf": conf, "skill": 1 - hmae / hbase, "dir": hdir, "n": hn, "mae": hmae}, model_path(symbol))
    db.add_model_run((now, symbol, version, chosen, hmae, hbase, champ_mae, hdir, int(switched),
                      note + f" | score on {hn} unseen hours", hn))
    log.info(f"[{symbol}] champion={chosen} {version} ({note}) confidence={conf} "
             f"holdout skill={1 - hmae / hbase:+.1%} dir={hdir:.1%} n={hn}")
    if old and switched:
        alerts.notify(f"🧠 {symbol}: {note}")

def predict_next(symbol, df, ref=None):
    b = joblib.load(model_path(symbol))
    d, _ = make_features(df, ref)
    last = d.iloc[[-1]]
    X = last.reindex(columns=b["feats"])
    bad = [c for c in b["feats"] if not np.isfinite(X[c].iloc[0])]
    if bad:       # the old code silently used 0 here, which turns missing data into a confident-looking forecast
        raise ValueError(f"{symbol}: cannot predict, missing/invalid features {bad[:5]}")
    ret = float(b["model"].predict(X)[0])
    base = float(last["close"].iloc[0])
    tt = (last["ts"].iloc[0] + pd.Timedelta(hours=1)).isoformat()
    info = {"conf": b.get("conf", "low"), "skill": b.get("skill", 0.0), "dir": b.get("dir", 0.5),
            "n": b.get("n"), "mae": b.get("mae"),
            "vol_regime": float(last["vol_regime"].iloc[0]) if "vol_regime" in last and np.isfinite(last["vol_regime"].iloc[0]) else None}
    return tt, base, base * (1 + ret), ret, b["version"], b["name"], info

def bundle_fv(symbol):
    """Feature version the saved model was trained with (None if no model yet)."""
    if not os.path.exists(model_path(symbol)):
        return None
    return joblib.load(model_path(symbol)).get("fv", 1)
