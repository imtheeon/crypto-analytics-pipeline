"""Run: python tests/test_crypto_dashboard.py  (or pytest)"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from crypto_dashboard_logic import anomaly_count_24h, insights, is_stale, movers, total_market_cap  # noqa: E402

T = pd.Timestamp("2026-10-05 12:00", tz="UTC")


def rows(*recs):
    cols = ["coin_id", "observed_at", "market_cap", "pct_change_24h", "is_anomaly"]
    return pd.DataFrame([dict(zip(cols, r)) for r in recs])


def test_total_market_cap():
    df = rows(
        ("btc", T - pd.Timedelta(hours=24, minutes=10), 100.0, None, None),
        ("eth", T - pd.Timedelta(hours=24), 50.0, None, None),
        ("btc", T, 120.0, 0.2, False),
        ("eth", T - pd.Timedelta(minutes=5), 60.0, 0.2, None),
    )
    total, change = total_market_cap(df)
    assert total == 180.0
    assert abs(change - (180 / 150 - 1)) < 1e-12
    # btc's 24h-ago value is 40 minutes before the mark -> change unknown, not a partial sum
    df.loc[0, "observed_at"] = T - pd.Timedelta(hours=24, minutes=40)
    assert total_market_cap(df) == (180.0, None)
    # a coin with no 24h history -> change unknown
    assert total_market_cap(df.iloc[[1, 2, 3]])[1] is None
    # a coin's latest market cap missing -> total unknown, not understated
    df.loc[2, "market_cap"] = None
    assert total_market_cap(df) == (None, None)


def test_movers():
    df = rows(("btc", T, 1, 0.05, None), ("eth", T, 1, -0.03, None), ("sol", T, 1, None, None),
              ("eth", T - pd.Timedelta(hours=1), 1, 0.50, None))  # older eth row must not count
    gainer, loser = movers(df)
    assert gainer.name == "btc" and loser.name == "eth"
    assert movers(rows(("btc", T, 1, None, None))) == (None, None)
    tie = rows(("sol", T, 1, 0.05, None), ("btc", T, 1, 0.05, None))
    assert movers(tie)[0].name == "btc"  # ties resolve by coin_id, not row order


def test_anomaly_count():
    df = rows(("btc", T, 1, 0, True), ("btc", T - pd.Timedelta(hours=1), 1, 0, False),
              ("eth", T, 1, 0, None), ("btc", T - pd.Timedelta(hours=25), 1, 0, True))  # outside 24h
    assert anomaly_count_24h(df) == (1, 2)
    assert anomaly_count_24h(rows(("btc", T, 1, 0, None))) == (0, 0)
    df["is_anomaly"] = df["is_anomaly"].astype("boolean")  # BigQuery's nullable bool arrives like this
    assert anomaly_count_24h(df) == (1, 2)


def test_is_stale():
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    assert not is_stale(now - timedelta(minutes=60), now)
    assert is_stale(now - timedelta(minutes=61), now)
    assert is_stale(pd.NaT, now)  # no data counts as stale


def coins_frame(changes, vol=0.004, flagged=False, checked=True, week=True):
    """Latest row per coin at T (plus a row 7 days earlier per coin when week=True)."""
    recs = []
    for i, ch in enumerate(changes):
        coin = f"c{i}"
        recs.append(dict(coin_id=coin, name=f"Coin{i}", observed_at=T, market_cap=110.0, pct_change_24h=ch,
                         return_15m=-0.0326 if (flagged and i == 0) else 0.001, volatility_24h=vol + i / 1000,
                         z_score=-7.1 if (flagged and i == 0) else 0.2, z_threshold=3.0,
                         is_anomaly=(flagged and i == 0) if checked else None))
        if week:
            recs.append(dict(coin_id=coin, name=f"Coin{i}", observed_at=T - pd.Timedelta(days=7), market_cap=100.0,
                             pct_change_24h=None, return_15m=None, volatility_24h=None, z_score=None,
                             z_threshold=3.0, is_anomaly=None))
    return pd.DataFrame(recs)


def test_insights_full():
    lines = insights(coins_frame([0.01, 0.02, -0.08, 0.03, 0.01, 0.02, 0.01, 0.04, -0.01, 0.02], flagged=True))
    assert lines == [
        "Coin2 fell 8.00% in 24 hours, the largest move of the 10 coins.",
        "Latest unusual move: Coin0 fell 3.26% in 15 minutes at 12:00 UTC (z-score -7.1, threshold 3).",
        "8 of 10 coins are up over 24 hours.",
        "Coin9 was the most volatile coin over 24 hours: its 15-minute returns had a standard deviation of 1.30%.",
        "The combined market cap of the 10 coins is up 10.0% over 7 days, at $1,100.00.",
    ], lines
    for line in lines:
        assert any(ch.isdigit() for ch in line), line
        assert not any(w in line.lower() for w in ("buy", "sell", "surge", "soar", "plunge", "crash", "moon")), line


def test_insights_skip_rules():
    # 6 up / 4 down: no breadth sentence. Checked but nothing flagged: the "no unusual moves" fallback.
    lines = insights(coins_frame([0.01] * 6 + [-0.01] * 4, week=False))
    assert not any("coins are" in line for line in lines)
    assert "No unusual 15-minute moves in the last 24 hours, across 10 checks." in lines
    assert not any("7 days" in line for line in lines)  # no 7-day history
    # 7 down: breadth says down
    assert "7 of 10 coins are down over 24 hours." in insights(coins_frame([-0.01] * 7 + [0.01] * 3))
    # brand-new data: nothing computable, so nothing is said
    bare = coins_frame([None] * 10, vol=float("nan"), checked=False, week=False)
    bare["volatility_24h"] = None
    assert insights(bare) == []


def test_insights_edge_cases():
    # tiny moves never print "rose 0.00%" / "up 0.0%"
    tiny = coins_frame([0.00004] + [0.00001] * 9)
    tiny.loc[tiny["observed_at"] == T, "market_cap"] = 100.02
    lines = insights(tiny)
    assert lines[0] == "Coin0 moved less than 0.01% in 24 hours, the largest move of the 10 coins.", lines
    assert "The combined market cap of the 10 coins is within 0.1% of its level over 7 days, at $1,000.20." in lines
    # a coin whose newest row is 2 hours old drops out of every rule, including the 7-day total
    stale = coins_frame([0.01] * 10)
    stale.loc[(stale["coin_id"] == "c9") & (stale["observed_at"] == T), "observed_at"] = T - pd.Timedelta(hours=2)
    lines = insights(stale)
    assert "9 of 9 coins are up over 24 hours." in lines and "of the 9 coins" in lines[0], lines
    assert lines[-1].startswith("The combined market cap of the 9 coins is up 10.0%"), lines
    # BigQuery's nullable boolean dtype with NA, and singular wording
    one = coins_frame([0.02], flagged=False, week=False)
    one["is_anomaly"] = one["is_anomaly"].astype("boolean")
    one.loc[0, "is_anomaly"] = pd.NA
    one = pd.concat([one, coins_frame([0.02], week=False).assign(observed_at=T - pd.Timedelta(minutes=15))])
    lines = insights(one)
    assert "the largest move of the 1 coin." in lines[0], lines
    assert "No unusual 15-minute moves in the last 24 hours, across 1 check." in lines, lines


if __name__ == "__main__":
    test_total_market_cap()
    test_movers()
    test_anomaly_count()
    test_is_stale()
    test_insights_full()
    test_insights_skip_rules()
    test_insights_edge_cases()
    print("ok")
