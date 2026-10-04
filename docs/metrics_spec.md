# Metrics spec

Every metric used in SQL or the dashboard is defined here first. If it's not in this file, it doesn't ship.

## Ground rules

- **Grain:** one row per coin per observation. An observation is a CoinGecko snapshot, identified by `(coin_id, observed_at)`.
- **`observed_at`:** CoinGecko's `last_updated` cast to a UTC timestamp. We use the source time, not our fetch time, so a re-run never creates a new observation.
- **Cadence:** the job runs every 15 minutes, so a normal day has 96 observations per coin. Runs can be late or skipped, so every window below is time-based (`RANGE` on seconds), never row-based.
- **Returns:** the 15-minute return is the base input for volatility and anomalies. It is `price_t / price_prev - 1`, where `price_prev` is the coin's previous observation. It is null when the gap to the previous observation is over 30 minutes, so a missed run doesn't look like a big move.
- **Currency:** USD only.
- **Nulls:** a metric is null when its inputs are missing or its minimum-data rule isn't met. We never fill with 0.

## KPIs

### 1. Price change (15m): `return_15m`
- **Formula:** `current_price / LAG(current_price) OVER (PARTITION BY coin_id ORDER BY observed_at) - 1`. Null if the previous observation is more than 30 minutes older.
- **Purpose:** the short-term move. It's the input for volatility and the anomaly flag.

### 2. Price change (24h): `pct_change_24h`
- **Formula:** `current_price / price_24h_ago - 1`, where `price_24h_ago` is the latest observation at or before `observed_at - 24h`. Null if that observation is more than 30 minutes older than the 24-hour mark.
- **Purpose:** the headline daily move on the KPI cards. We compute it ourselves. CoinGecko's `price_change_percentage_24h` is kept in raw only as a cross-check.

### 3. 7-day moving average: `ma_7d`, `ma_7d_is_partial`
- **Formula:** `AVG(current_price) OVER (PARTITION BY coin_id ORDER BY UNIX_SECONDS(observed_at) RANGE BETWEEN 604800 PRECEDING AND CURRENT ROW)`. That covers the trailing 7 days (604,800 seconds), current row included.
- **Minimum data:** `ma_7d_is_partial` is true until the coin has 7 full days of history.
- **Purpose:** the trend line. Price above the line means the coin is trading above its recent level.

### 4. Volatility (24h): `volatility_24h`
- **Formula:** `STDDEV_SAMP(return_15m)` over the trailing 24 hours (`RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW`). It's shown as a percentage and is not annualized.
- **Minimum data:** at least 48 non-null returns in the window, which is half a day. Otherwise null.
- **Purpose:** how much a coin is moving around. It lets you compare a calm BTC with a jumpy DOGE.

### 5. Market cap rank (hourly): `market_cap_rank_tracked`
- **Formula:**
  - First, take each coin's last observation in each UTC hour: `QUALIFY ROW_NUMBER() OVER (PARTITION BY coin_id, TIMESTAMP_TRUNC(observed_at, HOUR) ORDER BY observed_at DESC) = 1`.
  - Then rank: `RANK() OVER (PARTITION BY TIMESTAMP_TRUNC(observed_at, HOUR) ORDER BY market_cap DESC)`, with 1 = largest.
  - Coins with no market cap, or no observation in that hour, are not ranked.
- **Why hourly, not per run:** a run can have fewer than 10 rows. That happens when the API leaves a coin out, or when a coin's `last_updated` hasn't changed so the loader skips it. Ranking per run would then compare different sets of coins.
- **Purpose:** shows rank changes inside our set. CoinGecko's global `market_cap_rank` stays in raw for reference.

### 6. Anomaly flag (z-score): `z_score`, `is_anomaly`
- **Formula:**
  - `z = (return_15m - mean_7d) / stddev_7d`.
  - `mean_7d` and `stddev_7d` are the `AVG` and `STDDEV_SAMP` of `return_15m` over the trailing 7 days, **current row excluded** (`RANGE BETWEEN 604800 PRECEDING AND 1 PRECEDING`). Including the current row would hide the very move we want to catch.
  - `is_anomaly = ABS(z) >= 3`.
- **Minimum data:** at least 96 non-null returns (one day) in the window, and `stddev_7d > 0`. Otherwise `z_score` and `is_anomaly` are null, meaning "not enough data to judge". `false` always means checked and normal.
- **Purpose:** flags moves that are unusual for this coin. A 2% move is normal for DOGE but rare for BTC.
- **Tuning:** the threshold of 3 and the 7-day window are starting values. If real data shows too many or too few flags, we'll change them here first and log it in DECISIONS.md.

## Insights box (dashboard)

Every sentence is built in Python from the KPI columns above. No free text from a model and no numbers that weren't calculated. Example template: "`{name}` moved `{pct_change_24h}` in 24h, its largest move of the week."
