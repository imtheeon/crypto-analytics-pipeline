-- Freshness tests. Run only by the scheduled workflow: between manual local runs they fail by design.
-- Any failed ASSERT stops the script and bq exits non-zero, which fails the run.
-- Run: cmd /c "bq query --use_legacy_sql=false < sql\tests\crypto_freshness_tests.sql"

-- Thresholds. Change them here and log it in docs/DECISIONS.md.
DECLARE max_ingest_age_minutes INT64 DEFAULT 60;
DECLARE max_coin_age_minutes INT64 DEFAULT 120;

-- Pipeline: the newest ingested_at in the table is recent, so runs are happening.
ASSERT (
  SELECT MAX(ingested_at)
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL max_ingest_age_minutes MINUTE)
AS 'stale pipeline: no ingestion within max_ingest_age_minutes';

-- Per coin: every coin's newest observed_at is recent, so no single coin has stopped updating.
ASSERT NOT EXISTS (
  SELECT coin_id
  FROM `crypto-analytics-pipeline-lc.crypto_clean.prices`
  GROUP BY coin_id
  HAVING MAX(observed_at) < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL max_coin_age_minutes MINUTE)
) AS 'stale coin: a coin has no observation within max_coin_age_minutes';
