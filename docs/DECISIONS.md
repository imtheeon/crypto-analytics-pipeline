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
- Two runtime dependencies for Phase 1: `requests` and `google-cloud-bigquery`. No pandas until something needs it.
