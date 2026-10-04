# Data dictionary

All times are UTC. GCP project: `crypto-analytics-pipeline-lc`. Location: US.

## `crypto_raw.prices`

One row per coin per ingestion run, as received from CoinGecko `/coins/markets`. Append-only, never updated.
- Partitioned by day on `ingested_at`, clustered by `coin_id`.
- Re-runs are safe: the loader skips any `(coin_id, last_updated)` pair already in the table.

| Column | Type | Null? | Description |
|---|---|---|---|
| `ingestion_id` | STRING | no | UUID for one run. Up to 10 rows share it. There are fewer if the API leaves a coin out or a coin hasn't updated since the last run. |
| `ingested_at` | TIMESTAMP | no | When our script fetched the data. |
| `coin_id` | STRING | no | CoinGecko ID, e.g. `bitcoin`, `avalanche-2`. |
| `symbol` | STRING | yes | Ticker, e.g. `btc`. |
| `name` | STRING | yes | Display name, e.g. `Bitcoin`. |
| `current_price` | FLOAT64 | yes | Price in USD. |
| `market_cap` | FLOAT64 | yes | Market cap in USD. |
| `market_cap_rank` | INT64 | yes | CoinGecko's global rank. Reference only. |
| `total_volume` | FLOAT64 | yes | 24h trading volume in USD. |
| `high_24h` | FLOAT64 | yes | 24h high in USD. |
| `low_24h` | FLOAT64 | yes | 24h low in USD. |
| `price_change_percentage_24h` | FLOAT64 | yes | CoinGecko's own 24h % change. Cross-check only. |
| `last_updated` | STRING | no | CoinGecko's source timestamp, ISO 8601, kept as text. Becomes `observed_at` in clean. |
| `payload` | JSON | no | The full API record for this coin, so fields we don't map now are not lost. |

## `crypto_clean.prices` (Phase 2)

Typed and deduped: one row per `(coin_id, observed_at)`. Columns match raw, with `last_updated` cast to `observed_at TIMESTAMP` and `payload` dropped. The loader's skip check should prevent duplicates. If two overlapping runs still create one, the row with the latest `ingested_at` wins.

## `crypto_metrics` views (Phase 2)

Columns follow the KPIs in [metrics_spec.md](metrics_spec.md): `return_15m`, `pct_change_24h`, `ma_7d`, `ma_7d_is_partial`, `volatility_24h`, `market_cap_rank_tracked`, `z_score`, `is_anomaly`.
