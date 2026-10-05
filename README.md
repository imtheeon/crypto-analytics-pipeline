# Crypto Analytics Pipeline

> ✍️ **[YOUR WORDS]** One or two sentences. What this is and why you built it.

## What it does

- Pulls price, market cap, 24h volume, and 24h high/low for 10 coins from CoinGecko every 15 minutes.
- Stores raw responses in BigQuery, then cleans and dedupes them in SQL.
- Calculates % change, 7-day moving average, volatility, rank, and a z-score anomaly flag.
- Runs data tests on every load. A failed test fails the run.
- Shows it all in a Streamlit dashboard with a "last updated" time. Query results are cached for 1 hour, and a "Refresh now" button works once every 5 minutes.

## Architecture

See [docs/architecture.md](docs/architecture.md). Column definitions are in [docs/data_dictionary.md](docs/data_dictionary.md).

## Stack

| Layer | Tool |
|---|---|
| Source | CoinGecko API (Demo key) |
| Ingestion | Python, GitHub Actions, started every 15 min by a Google Apps Script timer |
| Warehouse | BigQuery: `crypto_raw` → `crypto_clean` → `crypto_metrics` |
| Dashboard | Streamlit + Plotly |

## Metrics

Defined in [docs/metrics_spec.md](docs/metrics_spec.md).

## Run it locally

Windows PowerShell, conda env with `requirements.txt` installed:

```powershell
$env:CRYPTO_COINGECKO_API_KEY = "<CoinGecko Demo key>"
$env:GOOGLE_APPLICATION_CREDENTIALS = "$env:USERPROFILE\.gcp\crypto-pipeline-sa.json"
python ingestion/crypto_ingest.py
python tests/test_crypto_ingest.py
```

Deploy the views as your own gcloud user, in this order, then run the data tests. After that, the monthly `crypto-views-refresh` workflow re-deploys them so the sandbox's 60-day expiry never hits. `cmd /c` avoids the BOM that PowerShell 5.1 adds when piping:

```powershell
cmd /c "bq query --use_legacy_sql=false < sql\clean\crypto_clean_prices.sql"
cmd /c "bq query --use_legacy_sql=false < sql\metrics\crypto_anomaly_config.sql"
cmd /c "bq query --use_legacy_sql=false < sql\metrics\crypto_metrics_prices.sql"
cmd /c "bq query --use_legacy_sql=false < sql\metrics\crypto_rank_hourly.sql"
cmd /c "bq query --use_legacy_sql=false < sql\tests\crypto_data_tests.sql"
python tests/test_crypto_metrics_sql.py
```

`sql\tests\crypto_freshness_tests.sql` is for the scheduled workflow only (`.github/workflows/crypto_pipeline.yml`), which runs both test files with `python tests/run_sql_tests.py`. Run by hand, it fails whenever the last run was over an hour ago.

Each run appends new snapshots to `crypto_raw.prices`. Running it again before CoinGecko updates adds 0 rows.

## Dashboard

Streamlit app in `dashboard/streamlit_app.py`. It reads `crypto_metrics` only, as the read-only `crypto-dashboard-sa`.

```powershell
pip install -r dashboard/requirements.txt
streamlit run dashboard/streamlit_app.py
```

Run it from the repo root so `.streamlit/config.toml` (the theme) applies. Credentials go in `.streamlit/secrets.toml` as a `[gcp_service_account]` block (git-ignored). Without that file, it uses `GOOGLE_APPLICATION_CREDENTIALS`.

The hosted app runs on Streamlit Community Cloud's free tier. It goes to sleep after a while with no visitors, and the first visit after that takes about a minute to wake it.

## Scheduler

GitHub's own `schedule:` trigger fired once in about 12 hours for this repo, so a Google Apps Script timer starts the workflow instead. The cron line stays in the workflow as a backup.

- Code: [scheduler/crypto_pipeline_trigger.gs](scheduler/crypto_pipeline_trigger.gs), in the Apps Script project `crypto-pipeline-timer` (Google account that owns the GCP project).
- Trigger: time-driven, every 15 minutes, failure notifications set to "Notify me immediately".
- Token: fine-grained GitHub token `crypto-pipeline-timer`, this repo only, Actions read and write. It's stored in the project's Script Properties as `CRYPTO_GITHUB_TOKEN`, never in code. **It expires Dec 4, 2026.**
- When it expires, the script emails "crypto-pipeline-timer: workflow dispatch failed" (HTTP 401). To renew it:
  1. Regenerate the token on GitHub (Settings > Developer settings > Fine-grained tokens > crypto-pipeline-timer).
  2. Paste the new value into Script Properties.
  3. Update the date here and in DECISIONS.md.
- An HTTP 403 "Resource not accessible by personal access token" means the token's Actions permission isn't "Read and write".

## Troubleshooting

- If the app shows an ImportError after a deploy, reboot it from Manage app.

## Design decisions

See [docs/DECISIONS.md](docs/DECISIONS.md).

> ✍️ **[YOUR WORDS]** The two or three choices you'd defend in an interview, and why.

## What I'd do next

> ✍️ **[YOUR WORDS]** For example: USGS earthquake source, Snowflake port.
