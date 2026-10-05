-- KPI 5: rank by market cap within our coin set, using each coin's last observation in each UTC hour.
CREATE OR REPLACE VIEW `crypto-analytics-pipeline-lc.crypto_metrics.rank_hourly` AS
WITH last_in_hour AS (
  SELECT coin_id, name, market_cap, TIMESTAMP_TRUNC(observed_at, HOUR) AS hour
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
  WHERE market_cap IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY coin_id, TIMESTAMP_TRUNC(observed_at, HOUR)
                             ORDER BY observed_at DESC) = 1
)
SELECT
  hour,
  coin_id,
  name,
  market_cap,
  RANK() OVER (PARTITION BY hour ORDER BY market_cap DESC) AS market_cap_rank_tracked
FROM last_in_hour;
