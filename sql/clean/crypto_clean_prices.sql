-- One row per (coin_id, observed_at). If two overlapping runs loaded the same snapshot, the latest ingested_at wins.
CREATE OR REPLACE VIEW `crypto-analytics-pipeline-lc.crypto_clean.prices` AS
SELECT
  coin_id,
  TIMESTAMP(last_updated) AS observed_at,
  ingested_at,
  ingestion_id,
  symbol,
  name,
  current_price,
  market_cap,
  market_cap_rank,
  total_volume,
  high_24h,
  low_24h,
  price_change_percentage_24h
FROM `crypto-analytics-pipeline-lc.crypto_raw.prices`
QUALIFY ROW_NUMBER() OVER (PARTITION BY coin_id, TIMESTAMP(last_updated) ORDER BY ingested_at DESC) = 1;
