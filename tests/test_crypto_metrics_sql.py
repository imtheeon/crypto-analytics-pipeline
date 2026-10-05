"""Runs sql/metrics/crypto_metrics_prices.sql against 8 days of synthetic 15-minute data in BigQuery.

Run:  python tests/test_crypto_metrics_sql.py
Env:  GOOGLE_APPLICATION_CREDENTIALS (reads crypto_metrics.anomaly_config, scans no real data)
"""
import re
from pathlib import Path

from google.cloud import bigquery

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "metrics" / "crypto_metrics_prices.sql"
CLEAN = "`crypto-analytics-pipeline-lc.crypto_clean.prices`"
N = 8 * 96  # 8 days of 15-minute observations, i = 0 .. N-1
GAP = (100, 101, 102)  # dropped observations -> 60-minute gap before i = 103
SPIKE = N - 1  # last observation jumps 5%

# Price cycles +0.1%, +0.1%, -0.2% so returns have a small, nonzero stddev.
FIXTURE = f"""
synthetic AS (
  SELECT
    'testcoin' AS coin_id,
    TIMESTAMP_ADD(TIMESTAMP '2026-01-01', INTERVAL 15 * i MINUTE) AS observed_at,
    'tst' AS symbol, 'Testcoin' AS name,
    100 * (1 + 0.001 * MOD(i, 3)) * IF(i = {SPIKE}, 1.05, 1) AS current_price,
    1e9 AS market_cap, 1e6 AS total_volume, CAST(NULL AS FLOAT64) AS high_24h, CAST(NULL AS FLOAT64) AS low_24h
  FROM UNNEST(GENERATE_ARRAY(0, {N - 1})) AS i
  WHERE i NOT IN UNNEST({list(GAP)})
)"""


def run_view_on_fixture():
    sql = SQL_PATH.read_text()
    select = re.sub(r"(?s)^.*?CREATE OR REPLACE VIEW `[^`]+` AS\s*WITH", "", sql)
    select = "WITH " + FIXTURE + "," + select.replace(CLEAN, "synthetic").rstrip().rstrip(";")
    query = f"SELECT *, DIV(UNIX_SECONDS(observed_at) - UNIX_SECONDS(TIMESTAMP '2026-01-01'), 900) AS i FROM ({select})"
    return {r.i: r for r in bigquery.Client(project="crypto-analytics-pipeline-lc").query(query).result()}


def test_metrics_view():
    rows = run_view_on_fixture()
    assert len(rows) == N - len(GAP)

    assert rows[0].return_15m is None                          # no previous observation
    assert abs(rows[1].return_15m - 0.001) < 1e-9
    assert rows[103].return_15m is None                        # 60-minute gap -> null, not a big move
    assert rows[104].return_15m is not None

    assert rows[95].pct_change_24h is None                     # less than 24h of history
    assert abs(rows[96].pct_change_24h - 0) < 1e-12            # i=96 and i=0 have the same price
    assert rows[198].pct_change_24h is None                    # 24h mark falls in the gap, nearest is 45 min old

    assert rows[47].volatility_24h is None                     # 47 returns so far
    assert rows[48].volatility_24h is not None                 # 48 returns

    assert rows[96].z_score is None and rows[96].is_anomaly is None   # 95 prior returns
    assert rows[97].z_score is not None                        # 96 prior returns
    assert rows[300].is_anomaly is False                       # normal move, checked
    assert rows[SPIKE].is_anomaly is True and rows[SPIKE].z_score > 3

    assert rows[7 * 96 - 1].ma_7d_is_partial is True
    assert rows[7 * 96].ma_7d_is_partial is False


if __name__ == "__main__":
    test_metrics_view()
    print("ok")
