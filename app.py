import os, hmac, pandas as pd, streamlit as st
import config, db, alerts

st.set_page_config(page_title="Crypto Predictor Tracker", layout="wide")
_pw = os.getenv("DASHBOARD_PASSWORD")
if _pw and not st.session_state.get("auth"):
    _x = st.text_input("Password", type="password")
    if _x and hmac.compare_digest(_x, _pw):
        st.session_state["auth"] = True
        st.rerun()
    st.stop()

st.title("Crypto Prediction Tracker")
st.caption("Learning project. Predictions are not financial advice.")

if st.sidebar.button("Run one cycle now"):
    from pipeline import run_cycle
    with st.spinner("Running..."):
        run_cycle()
    st.sidebar.success("Done")
symbol = st.sidebar.selectbox("Coin", config.SYMBOLS)
from datetime import datetime, timezone
_last = db.kv_get("last_success")
if _last:
    _age = (datetime.now(timezone.utc) - datetime.fromisoformat(_last)).total_seconds() / 3600
    (st.sidebar.success if _age <= config.HEALTH_MAX_AGE_HOURS else st.sidebar.error)(f"Worker: last good cycle {_age:.1f}h ago")
else:
    st.sidebar.warning("Worker: no successful cycle yet")
st.sidebar.caption(f"Alerts: {', '.join(alerts.channels()) or 'not configured'}")
if st.sidebar.button("Send test alert"):
    st.sidebar.write("Sent via: " + (", ".join(alerts.notify("Test alert from your crypto tracker")) or "nothing (no channel set up)"))

P, R, C = db.read("predictions"), db.read("model_runs"), db.read("candidate_scores")
res_all = P[P["resolved"] == 1]

tabS, tab2, tab3, tabP, tab4, tab5 = st.tabs(["Summary", "Accuracy", "Models", "Paper trading", "CoinSwitch", "Logs"])
import explain

with tabS:
    st.subheader("Forecast for the next hour")
    cols = st.columns(len(config.SYMBOLS))
    for col, s in zip(cols, config.SYMBOLS):
        nxt = P[(P["symbol"] == s) & (P["resolved"] == 0)].sort_values("created_at")
        runs = R[R["symbol"] == s].sort_values("id")
        with col:
            if len(nxt):
                n = nxt.iloc[-1]
                when = pd.to_datetime(n["target_time"]).strftime("%H:%M UTC")
                col.metric(f"{s.replace('USDT', '')} at {when}", f"{n['predicted_price']:,.2f}",
                           f"{n['predicted_return']*100:+.2f}%")
                col.write(explain.direction_words(n["predicted_return"]))
                lvl, msg = explain.trust_words(runs.iloc[-1] if len(runs) else None)
                col.caption({"high": "🟢 ", "medium": "🟡 ", "low": "🔴 "}[lvl] + msg)
            else:
                col.info(f"{s}: no forecast yet")

    st.subheader("Are the forecasts any good?")
    for s in config.SYMBOLS:
        emoji, head, lines = explain.verdict(res_all[res_all["symbol"] == s])
        st.markdown(f"**{emoji} {s.replace('USDT', '')}: {head}**")
        for ln in lines:
            st.markdown(f"- {ln}")

    st.subheader("Pretend-money trading")
    _E, _T = db.read("paper_equity"), db.read("paper_trades")
    st.write(explain.paper_sentence(_E, _T, config.PAPER_START_BALANCE))

    with st.expander("What do these words mean?"):
        st.markdown(
            "- **Forecast**: the model's guess for the price one hour from now.\n"
            "- **Guessing / 'price stays the same'**: the laziest forecast possible. A model is only useful if it beats this.\n"
            "- **Practice tests**: before going live, the model is tested on past hours it has never seen.\n"
            "- **Direction right**: how often the model got up vs. down correct. 50% = coin flip.\n"
            "- **Pretend money**: a simulated account with fake money and realistic fees. Nothing real is ever traded.")
    with st.expander("Numbers by coin"):
        rows = []
        for s in config.SYMBOLS:
            r = res_all[res_all["symbol"] == s]
            if len(r):
                rows.append({"Coin": s, "Forecasts checked": len(r),
                             "Typical miss (%)": round(r["pct_error"].mean(), 3),
                             "'Price stays same' miss (%)": round(((r["actual_price"] - r["base_price"]).abs() / r["actual_price"]).mean() * 100, 3),
                             "Up/down right (%)": round(r["direction_correct"].mean() * 100, 1)})
        st.dataframe(pd.DataFrame(rows), hide_index=True) if rows else st.info("No checked forecasts yet.")

with tab2:
    res = res_all[res_all["symbol"] == symbol].copy()
    if len(res) >= 2:
        res["target_time"] = pd.to_datetime(res["target_time"])
        naive = (res["actual_price"] - res["base_price"]).abs()
        a, b, c = st.columns(3)
        a.metric("Forecasts checked", len(res))
        b.metric("Typical miss", f"{res['pct_error'].mean():.2f}%",
                 f"{res['pct_error'].mean() - (naive / res['actual_price']).mean() * 100:+.2f}% vs. 'price stays same'", delta_color="inverse")
        c.metric("Up/down right", f"{res['direction_correct'].mean()*100:.1f}%")
        st.caption("Actual vs. forecast price (the two lines should sit on top of each other)")
        st.line_chart(res.set_index("target_time")[["actual_price", "predicted_price"]])
        if len(res) >= 24:
            roll = pd.DataFrame({"model_error": res["abs_error"].rolling(24).mean(),
                                 "naive_error": naive.rolling(24).mean(),
                                 "direction_acc": res["direction_correct"].rolling(24).mean()}).set_index(res["target_time"]).dropna()
            x, y = st.columns(2)
            x.caption("Average miss over the last 24 hours: model vs. 'price stays same' (lower is better; model should be below)")
            x.line_chart(roll[["model_error", "naive_error"]])
            y.caption("Up/down right over the last 24 hours (0.5 = coin flip)")
            y.line_chart(roll[["direction_acc"]])
        else:
            st.info("Rolling charts appear after 24 checked forecasts.")
        st.subheader("Accuracy by model version")
        st.dataframe(res.groupby(["model_name", "model_version"]).agg(
            checked=("id", "count"), avg_miss_usd=("abs_error", "mean"), up_down_right=("direction_correct", "mean")))
    else:
        st.info("Charts appear once at least 2 forecasts for this coin have been checked (one per hour).")

with tab3:
    c = C[C["symbol"] == symbol]
    if len(c):
        latest = c[c["run_at"] == c["run_at"].max()].copy()
        latest["skill_vs_naive_%"] = (1 - latest["cv_mae"] / latest["baseline_mae"]) * 100
        st.subheader("Model practice-test scores (tested on hours the model had not seen)")
        st.dataframe(latest.sort_values("cv_mae")[["candidate", "cv_mae", "cv_dir_acc", "baseline_mae", "skill_vs_naive_%"]])
        st.caption("skill_vs_naive_% above 0 = beat 'price stays the same'. Near 0 or negative = no real edge. cv_dir_acc: 0.5 = coin flip.")
        c = c.copy(); c["run_at"] = pd.to_datetime(c["run_at"])
        st.subheader("Is training improving? (above 0 = beating 'price stays the same')")
        c["skill"] = (1 - c["cv_mae"] / c["baseline_mae"]) * 100
        st.line_chart(c.pivot_table(index="run_at", columns="candidate", values="skill"))
    r = R[R["symbol"] == symbol]
    st.subheader("Champion history")
    st.dataframe(r.sort_values("id", ascending=False))

with tab4:
    t = db.read("coinswitch_ticks")
    if len(t):
        t = t[t["symbol"] == symbol]
        st.line_chart(t.set_index(pd.to_datetime(t["ts"]))["price"])
        st.dataframe(t.tail(20))
    else:
        st.info("No CoinSwitch data. Add keys in a .env file (see .env.example).")

with tab5:
    if os.path.exists(config.LOG_PATH):
        st.code("".join(open(config.LOG_PATH).readlines()[-60:]))

with tabP:
    import json
    from paper import summary
    E, T = db.read("paper_equity"), db.read("paper_trades")
    st.caption(f"Fake money. Buys only when the model passed its practice tests. Start {config.PAPER_START_BALANCE:,.0f} USDT, fee {config.FEE_RATE*100:.2f}%/side, "
               f"slippage {config.SLIPPAGE*100:.2f}%/side, buy if predicted >= {config.ENTRY_THRESHOLD*100:.2f}%, "
               f"stop {config.STOP_LOSS*100:.0f}% / take-profit {config.TAKE_PROFIT*100:.0f}%.")
    st.write(explain.paper_sentence(E, T, config.PAPER_START_BALANCE))
    if len(E):
        E["ts"] = pd.to_datetime(E["ts"])
        m = summary(E, T)
        a, b, c, d = st.columns(4)
        a.metric("Equity", f"{E['equity'].iloc[-1]:,.2f}", f"{m['return_%']:+.2f}%")
        b.metric("Buy & hold", f"{E['bh_equity'].iloc[-1]:,.2f}", f"{m['buy_hold_%']:+.2f}%")
        c.metric("Max drawdown", f"{m['max_drawdown_%']:.2f}%")
        d.metric("Closed trades", m["trades"])
        st.line_chart(E.set_index("ts")[["equity", "bh_equity"]])
        if len(T):
            st.write({k: round(v, 2) for k, v in m.items() if k in ("win_rate_%", "avg_trade_%", "profit_factor", "fees_paid", "sharpe")})
            st.caption("Exit reasons"); st.bar_chart(T["reason"].value_counts())
            st.dataframe(T.sort_values("id", ascending=False))
        raw = db.kv_get("portfolio")
        if raw and json.loads(raw)["positions"]:
            st.subheader("Open positions"); st.dataframe(pd.DataFrame(json.loads(raw)["positions"]).T)
    else:
        st.info("No paper-trading data yet. Run a cycle (the sidebar button or scheduler.py).")
    if os.path.exists("data/backtest_summary.csv"):
        st.subheader("Replay of recent history (python backtest.py)")
        st.caption("Each row replays the last ~600 hours with different buy thresholds. return_% is the pretend account, buy_hold_% is just holding.")
        st.dataframe(pd.read_csv("data/backtest_summary.csv"))
