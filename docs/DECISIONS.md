# Decisions

One line per choice. Newest at the bottom.

- Project lives in `C:\Users\leant\projects`, not OneDrive. A synced `.git` folder causes conflicts, and key files should not sync to the cloud.
- New GCP project for this work only: `crypto-analytics-pipeline-lc` (the plain ID was taken). Its own gcloud config, `crypto`, keeps commands off other projects. The existing `analytics-pipeline` project is never touched.
- BigQuery location: US multi-region. Cannot change after datasets exist.
- Three datasets: `crypto_raw` (as received), `crypto_clean` (typed, deduped), `crypto_metrics` (SQL views).
- Source: CoinGecko `/coins/markets` with a free Demo key. One call returns all 10 coins, so 15-minute runs use about 2,900 calls a month against a 10,000 cap.
- Coin list lives in `ingestion/crypto_coins.json` so it changes without a code edit.
- No stablecoins. Their price barely moves, so they add noise to volatility and anomaly metrics.
- Service account key stays outside the repo in `%USERPROFILE%\.gcp\`. GitHub Actions gets it from the `CRYPTO_GCP_KEY` secret.
- `observed_at` is CoinGecko's `last_updated`, not our fetch time. Re-runs don't create fake observations.
- All metric windows are time-based (`RANGE` on seconds), not row-based. Missed runs don't stretch a "7-day" window.
- 15-minute returns are null across gaps over 30 minutes. A skipped run shouldn't look like a big move.
- We compute 24h % change ourselves. CoinGecko's own figure is kept only as a cross-check.
- Rank is hourly, not per run. A run can be missing coins.
- Anomaly = |z| >= 3 against the coin's own trailing 7 days, current row excluded. The flag is null when there's not enough data.
- The z-score threshold (3) lives in a one-row config view, `crypto_metrics.anomaly_config`. The SQL and the dashboard read the same value.
- Raw keeps the full API record in a `payload` JSON column, so new fields aren't lost.
- BigQuery sandbox, no billing account. Costs nothing. On `crypto_raw.prices` the sandbox sets a 60-day *partition* expiry, not a table expiry: rows older than 60 days drop off and the table stays. Link billing to keep full history.
- Loads use load jobs, not streaming inserts. Load jobs are free and work in the sandbox.
- The re-run check looks back 2 days of partitions. Each check is billed at BigQuery's 10 MB minimum, about 29 GB a month at 96 runs a day, inside the 1 TB free tier. A coin stuck for more than 2 days could repeat in raw; clean dedupes it.
- `crypto-pipeline-sa` gets `bigquery.jobUser` on the project and write access on `crypto_raw` only, not project-wide `dataEditor`.
- Two runtime dependencies for Phase 1: `requests` and `google-cloud-bigquery`. No pandas until something needs it.
- `crypto_clean.prices` is a view, not a table. At about 1,000 rows a day, deduping on read is free and needs no load step. The sandbox doesn't allow DML anyway.
- KPIs 1-4 and 6 are one view, `crypto_metrics.prices`, at the observation grain. Rank is its own view, `crypto_metrics.rank_hourly`, because it's at the hour grain.
- The sandbox makes views expire after 60 days, and the expiry can't be removed. Re-running the `sql/` files resets it. Link billing to drop this.
- Data tests are `ASSERT` statements in `sql/tests/crypto_data_tests.sql`. A failed one makes `bq` exit non-zero.
- Freshness tests are in their own file, `sql/tests/crypto_freshness_tests.sql`, and only the scheduled workflow runs them. Between manual runs they would always fail.
- Freshness thresholds: newest `ingested_at` within 60 minutes (the pipeline is running), each coin's newest `observed_at` within 2 hours (no coin has stopped updating). They are `DECLARE`d at the top of that file. Only the tests read them, so they don't need a config view.
- The metrics view is tested against 8 days of synthetic data built inside the query, so the test reads no real rows.
