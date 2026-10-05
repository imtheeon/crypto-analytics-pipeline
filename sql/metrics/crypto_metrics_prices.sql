-- Per-observation KPIs from docs/metrics_spec.md (1-4 and 6). Windows are RANGE on seconds, never rows.
CREATE OR REPLACE VIEW `crypto-analytics-pipeline-lc.crypto_metrics.prices` AS
WITH base AS (
  SELECT
    *,
    UNIX_SECONDS(observed_at) AS ts,
    LAG(current_price) OVER w AS prev_price,
    UNIX_SECONDS(observed_at) - LAG(UNIX_SECONDS(observed_at)) OVER w AS prev_gap_s,
    -- Latest observation at or before observed_at - 24h, and how far before the 24h mark it is.
    LAST_VALUE(current_price) OVER w_24h_ago AS price_24h_ago,
    UNIX_SECONDS(observed_at) - 86400 - LAST_VALUE(UNIX_SECONDS(observed_at)) OVER w_24h_ago AS gap_24h_s,
    MIN(observed_at) OVER (PARTITION BY coin_id) AS first_observed_at
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
  WINDOW
    w AS (PARTITION BY coin_id ORDER BY observed_at),
    w_24h_ago AS (PARTITION BY coin_id ORDER BY UNIX_SECONDS(observed_at)
                  RANGE BETWEEN UNBOUNDED PRECEDING AND 86400 PRECEDING)
),
returns AS (
  SELECT
    *,
    IF(prev_gap_s <= 1800, current_price / prev_price - 1, NULL) AS return_15m,
    IF(gap_24h_s <= 1800, current_price / price_24h_ago - 1, NULL) AS pct_change_24h,
    AVG(current_price) OVER (PARTITION BY coin_id ORDER BY ts
                             RANGE BETWEEN 604800 PRECEDING AND CURRENT ROW) AS ma_7d,
    observed_at < TIMESTAMP_ADD(first_observed_at, INTERVAL 7 DAY) AS ma_7d_is_partial
  FROM base
),
windows AS (
  SELECT
    *,
    STDDEV_SAMP(return_15m) OVER d1 AS vol_sd,
    COUNT(return_15m) OVER d1 AS vol_n,
    AVG(return_15m) OVER d7_prior AS mean_7d,
    STDDEV_SAMP(return_15m) OVER d7_prior AS stddev_7d,
    COUNT(return_15m) OVER d7_prior AS n_7d
  FROM returns
  WINDOW
    d1 AS (PARTITION BY coin_id ORDER BY ts RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW),
    d7_prior AS (PARTITION BY coin_id ORDER BY ts RANGE BETWEEN 604800 PRECEDING AND 1 PRECEDING)
),
scored AS (
  SELECT
    *,
    IF(vol_n >= 48, vol_sd, NULL) AS volatility_24h,
    IF(n_7d >= 96 AND stddev_7d > 0, (return_15m - mean_7d) / stddev_7d, NULL) AS z_score
  FROM windows
)
SELECT
  s.coin_id,
  s.observed_at,
  s.symbol,
  s.name,
  s.current_price,
  s.market_cap,
  s.total_volume,
  s.high_24h,
  s.low_24h,
  s.return_15m,
  s.pct_change_24h,
  s.ma_7d,
  s.ma_7d_is_partial,
  s.volatility_24h,
  s.z_score,
  ABS(s.z_score) >= c.z_threshold AS is_anomaly
FROM scored AS s
CROSS JOIN `crypto-analytics-pipeline-lc.crypto_metrics.anomaly_config` AS c;
