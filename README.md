# Crypto Analytics Pipeline

> ✍️ **[YOUR WORDS]** One or two sentences. What this is and why you built it.

## What it does

- Pulls price, market cap, 24h volume, and 24h high/low for 10 coins from CoinGecko every 15 minutes.
- Stores raw responses in BigQuery, then cleans and dedupes them in SQL.
- Calculates % change, 7-day moving average, volatility, rank, and a z-score anomaly flag.
- Runs data tests on every load. A failed test fails the run.
- Shows it all in a Streamlit dashboard that refreshes every 60 seconds.

## Architecture

See [docs/architecture.md](docs/architecture.md). Column definitions are in [docs/data_dictionary.md](docs/data_dictionary.md).

## Stack

| Layer | Tool |
|---|---|
| Source | CoinGecko API (Demo key) |
| Ingestion | Python, GitHub Actions (every 15 min) |
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

Each run appends new snapshots to `crypto_raw.prices`. Running it again before CoinGecko updates adds 0 rows.

## Design decisions

See [docs/DECISIONS.md](docs/DECISIONS.md).

> ✍️ **[YOUR WORDS]** The two or three choices you'd defend in an interview, and why.

## What I'd do next

> ✍️ **[YOUR WORDS]** For example: USGS earthquake source, Snowflake port.
