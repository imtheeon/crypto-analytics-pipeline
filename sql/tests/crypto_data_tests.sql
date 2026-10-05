-- Data tests. Any failed ASSERT stops the script and bq exits non-zero, which fails the run.
-- Run: cmd /c "bq query --use_legacy_sql=false < sql\tests\crypto_data_tests.sql"

-- Dupes: clean must have one row per (coin_id, observed_at).
ASSERT NOT EXISTS (
  SELECT 1
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
  GROUP BY coin_id, observed_at
  HAVING COUNT(*) > 1
) AS 'dupes: crypto_clean.prices has repeated (coin_id, observed_at)';

-- Nulls: every observation in the last 2 days has a price and a market cap.
ASSERT NOT EXISTS (
  SELECT 1
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
  WHERE observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)
    AND (current_price IS NULL OR market_cap IS NULL)
) AS 'nulls: crypto_clean.prices has observations missing current_price or market_cap';

-- Staleness checks live in crypto_freshness_tests.sql, run only by the scheduled workflow.
