"""Dashboard KPIs and insights from crypto_metrics.prices rows (KPIs 7-9, staleness, insights in docs/metrics_spec.md).

Pure pandas, no Streamlit, so tests/test_crypto_dashboard.py can check it.
Callers pass a non-empty frame; the app shows an empty state before calling these.
"""
from datetime import timedelta

import pandas as pd

DAY = pd.Timedelta(hours=24)
WEEK = pd.Timedelta(days=7)
BREADTH_MIN = 7
MAX_LOOKBACK_GAP = pd.Timedelta(minutes=30)
STALE_AFTER = timedelta(minutes=60)


def latest_per_coin(df):
    """Each coin's newest observation, for coins seen within STALE_AFTER of the newest data.

    A coin that stopped updating (or was taken off the coin list) drops out instead of being counted as current.
    """
    latest = df.sort_values(["observed_at", "coin_id"]).groupby("coin_id").tail(1).set_index("coin_id")
    return latest[latest["observed_at"] >= df["observed_at"].max() - STALE_AFTER]


def total_market_cap(df, lookback=DAY):
    """KPI 7: (total, change over lookback). total is None if a coin's latest market cap is missing (never a
    partial sum); change is None unless every coin also has a value from lookback ago, within 30 minutes."""
    latest = latest_per_coin(df)
    if latest["market_cap"].isna().any():
        return None, None
    total = latest["market_cap"].sum()
    mark = df["observed_at"].max() - lookback
    before = df[df["observed_at"] <= mark].sort_values("observed_at").groupby("coin_id").tail(1).set_index("coin_id")
    usable = before[(mark - before["observed_at"] <= MAX_LOOKBACK_GAP) & before["market_cap"].notna()]
    usable = usable[usable.index.isin(latest.index)]
    if set(usable.index) != set(latest.index):
        return total, None
    return total, total / usable["market_cap"].sum() - 1


def movers(df):
    """KPI 8: (gainer, loser) as rows of the latest observations, or (None, None)."""
    latest = latest_per_coin(df).dropna(subset=["pct_change_24h"])
    if latest.empty:
        return None, None
    return latest.loc[latest["pct_change_24h"].idxmax()], latest.loc[latest["pct_change_24h"].idxmin()]


def anomaly_count_24h(df):
    """KPI 9: (anomalies, checked) in the 24h before the newest observation."""
    window = df[df["observed_at"] > df["observed_at"].max() - DAY]
    checked = window["is_anomaly"].notna()
    return int((window["is_anomaly"][checked] == True).sum()), int(checked.sum())  # noqa: E712


RUN_EVERY = pd.Timedelta(minutes=15)


def available_around(df):
    """Estimated times when early-history metrics fill in, assuming a run every 15 minutes from now on.

    The latest-starting coin sets each estimate, so "around" errs late. Never earlier than the next run.
    """
    t = df["observed_at"].max()
    ordered = df.sort_values("observed_at")
    step = ordered.groupby("coin_id")["observed_at"].diff()
    # start of each coin's current unbroken run: its first row, or its last row after a gap over 30 minutes
    starts = ordered[step.isna() | (step > MAX_LOOKBACK_GAP)].groupby("coin_id")["observed_at"].max()
    streak = starts.max()
    returns = df.dropna(subset=["return_15m"])
    have_24h = returns[returns["observed_at"] > t - DAY].groupby("coin_id").size().max()
    have_7d = returns[returns["observed_at"] > t - WEEK].groupby("coin_id").size().max()
    have_24h, have_7d = (0 if pd.isna(h) else int(h) for h in (have_24h, have_7d))

    def later(ts):
        return max(ts, t + RUN_EVERY)

    return {
        "change_24h": later(streak + DAY),                        # KPI 2/7/8: a value 24h back, no gaps
        "volatility": later(t + (48 - have_24h) * RUN_EVERY),     # KPI 4: 48 returns in 24h
        "anomaly": later(t + (97 - have_7d) * RUN_EVERY),         # KPI 6: 96 prior returns, so the 97th row
        "ma_7d": df.groupby("coin_id")["observed_at"].min().max() + WEEK,  # KPI 3: 7 days after the first row
        "trend_7d": later(streak + WEEK),                          # insight 5: a value 7 days back, no gaps
    }


def is_stale(newest_observed_at, now):
    """True when the newest observation is over 60 minutes old, or there is none."""
    return pd.isna(newest_observed_at) or now - newest_observed_at > STALE_AFTER


def usd(v):
    if v is None or pd.isna(v):
        return "n/a"
    for div, suffix in [(1e12, "T"), (1e9, "B"), (1e6, "M")]:
        if abs(v) >= div:
            return f"${v / div:,.2f}{suffix}"
    return f"${v:,.2f}" if abs(v) >= 1 else f"${v:,.4g}"


def _moved(v):
    """'rose 1.23%' / 'fell 1.23%'; a move that rounds to 0.00% says so instead of 'rose 0.00%'."""
    return "moved less than 0.01%" if round(v, 4) == 0 else f"{'rose' if v > 0 else 'fell'} {abs(v):.2%}"


def _coins(n):
    return f"{n} coin{'' if n == 1 else 's'}"


def insights(df):
    """The five insight rules in docs/metrics_spec.md, in order. A rule without enough data is left out."""
    out = []
    latest = latest_per_coin(df)
    moves = latest["pct_change_24h"].dropna()
    t = df["observed_at"].max()

    if len(moves):
        coin = moves.abs().idxmax()
        out.append(f"{latest.at[coin, 'name']} {_moved(moves[coin])} in 24 hours, "
                   f"the largest move of the {_coins(len(moves))}.")

    recent = df[df["observed_at"] > t - DAY]
    checked = int(recent["is_anomaly"].notna().sum())
    flagged = recent[recent["is_anomaly"].eq(True)]
    if len(flagged):
        a = flagged.sort_values(["observed_at", "coin_id"]).iloc[-1]
        out.append(f"Latest unusual move: {a['name']} {_moved(a['return_15m'])} in 15 minutes at "
                   f"{a['observed_at']:%H:%M} UTC (z-score {a['z_score']:+.1f}, threshold {a['z_threshold']:g}).")
    elif checked:
        out.append(f"No unusual 15-minute moves in the last 24 hours, across {checked:,} check{'' if checked == 1 else 's'}.")

    up, down = int((moves > 0).sum()), int((moves < 0).sum())
    if up >= BREADTH_MIN:
        out.append(f"{up} of {_coins(len(moves))} are up over 24 hours.")
    elif down >= BREADTH_MIN:
        out.append(f"{down} of {_coins(len(moves))} are down over 24 hours.")

    vol = latest["volatility_24h"].dropna()
    if len(vol):
        coin = vol.idxmax()
        out.append(f"{latest.at[coin, 'name']} was the most volatile coin over 24 hours: its 15-minute returns "
                   f"had a standard deviation of {vol[coin]:.2%}.")

    total, change = total_market_cap(df, WEEK)
    if change is not None:
        direction = ("within 0.1% of its level" if round(change, 3) == 0
                     else f"{'up' if change > 0 else 'down'} {abs(change):.1%}")
        out.append(f"The combined market cap of the {_coins(len(latest))} is {direction} over 7 days, at {usd(total)}.")
    return out
