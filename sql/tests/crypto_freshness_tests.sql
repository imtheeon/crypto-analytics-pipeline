-- Freshness tests. Run only by the scheduled workflow: between manual local runs they fail by design.
-- Any failed ASSERT stops the script and the runner exits non-zero, which fails the run.
-- Run: python tests/run_sql_tests.py sql/tests/crypto_freshness_tests.sql  (it passes @coins)

-- Thresholds. Change them here and log it in docs/DECISIONS.md.
DECLARE max_ingest_age_minutes INT64 DEFAULT 60;
DECLARE max_coin_age_minutes INT64 DEFAULT 120;

-- Pipeline: the newest ingested_at in the table is recent, so runs are happening.
ASSERT (
  SELECT MAX(ingested_at)
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL max_ingest_age_minutes MINUTE)
AS 'stale pipeline: no ingestion within max_ingest_age_minutes';

-- Per coin: every coin in crypto_coins.json (@coins) has a recent observed_at. A listed coin that never
-- arrived fails; a coin removed from the list is no longer checked.
ASSERT NOT EXISTS (
  SELECT wanted
  FROM UNNEST(@coins) AS wanted
  LEFT JOIN (
    SELECT coin_id, MAX(observed_at) AS last_observed_at
    FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
    GROUP BY coin_id
  ) AS p ON p.coin_id = wanted
  WHERE p.last_observed_at IS NULL
     OR p.last_observed_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL max_coin_age_minutes MINUTE)
) AS 'stale coin: a coin in crypto_coins.json has no observation within max_coin_age_minutes';
