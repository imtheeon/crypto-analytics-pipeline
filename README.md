# Crypto Analytics Pipeline

> ✍️ **[YOUR WORDS]** One or two sentences. What this is and why you built it.

## What it does

- Pulls price, market cap, 24h volume, and 24h high/low for 10 coins from CoinGecko every 15 minutes.
- Stores raw responses in BigQuery, then cleans and dedupes them in SQL.
- Calculates % change, 7-day moving average, volatility, rank, and a z-score anomaly flag.
- Runs data tests on every load. A failed test fails the run.
- Shows it all in a Streamlit dashboard that refreshes every 60 seconds.

## Architecture

> 🚧 Diagram goes here (Phase 1, step 2).

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

> 🚧 Filled in once ingestion works.

## Design decisions

See [docs/DECISIONS.md](docs/DECISIONS.md).

> ✍️ **[YOUR WORDS]** The two or three choices you'd defend in an interview, and why.

## What I'd do next

> ✍️ **[YOUR WORDS]** For example: USGS earthquake source, Snowflake port.
