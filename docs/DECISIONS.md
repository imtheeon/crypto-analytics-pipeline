# Decisions

One line per choice. Newest at the bottom.

- Project lives in `C:\Users\leant\projects`, not OneDrive. A synced `.git` folder causes conflicts, and key files should not sync to the cloud.
- New GCP project for this work only. The existing `analytics-pipeline` project is never touched.
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
- Two runtime dependencies for Phase 1: `requests` and `google-cloud-bigquery`. No pandas until something needs it.
