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
  - `is_anomaly = ABS(z) >= z_threshold`. `z_threshold` is 3, read from the `crypto_metrics.anomaly_config` view ([sql/metrics/crypto_anomaly_config.sql](../sql/metrics/crypto_anomaly_config.sql)).
- **Minimum data:** at least 96 non-null returns (one day) in the window, and `stddev_7d > 0`. Otherwise `z_score` and `is_anomaly` are null, meaning "not enough data to judge". `false` always means checked and normal.
- **Purpose:** flags moves that are unusual for this coin. A 2% move is normal for DOGE but rare for BTC.
- **Tuning:**
  - Change the threshold in the config view only.
  - The 7-day window stays in the view's SQL, because BigQuery window frames only take fixed numbers, not variables.
  - Log every change in DECISIONS.md.

## Dashboard KPIs

Computed in Python from `crypto_metrics.prices`. "Latest" means each coin's newest observation, counting only coins seen within 60 minutes of the newest data. A coin that stopped updating, or was taken off the coin list, drops out instead of being counted as current. The reference time `t` is the newest `observed_at` across all coins, not the wall clock, so stale data still gives consistent numbers.

### 7. Total market cap: `total_market_cap`, `total_market_cap_change_24h`
- **Formula:** `total_market_cap` is the sum of each coin's latest `market_cap`. `total_market_cap_change_24h = total_market_cap / total_24h_ago - 1`, where `total_24h_ago` sums each coin's latest `market_cap` at or before `t - 24h`.
- **Minimum data:** the total is null if any coin's latest `market_cap` is missing, so it never shows a partial sum. The change is null if any coin's 24h-ago value is missing or more than 30 minutes older than the 24-hour mark, as in KPI 2. Comparing sums over different coin sets would be wrong.
- **Purpose:** the size of the tracked market, and its daily move.

### 8. Biggest gainer and loser (24h)
- **Formula:** among coins whose latest observation has a non-null `pct_change_24h`, the highest is the gainer and the lowest is the loser.
- **Minimum data:** null if no coin has a `pct_change_24h` yet.

### 9. Anomaly count (24h): `anomalies_24h`, `checked_24h`
- **Formula:** `anomalies_24h` counts rows with `is_anomaly = TRUE` and `observed_at > t - 24h`. `checked_24h` counts rows in the same window where `is_anomaly` is not null.
- **Minimum data:** if `checked_24h` is 0, the card shows "not enough data", not 0.

### Early history
Until a card has enough data, it shows "Collecting data, available around [time]", never blank or 0. The time is an estimate that assumes a run every 15 minutes from now on, and the latest-starting coin sets it:
- 24h metrics: 24 hours after the start of the current unbroken run of data (no gap over 30 minutes).
- Volatility: the newest observation plus 15 minutes for each of the 48 returns still missing in the 24h window.
- Anomaly checks: the same, counting toward 97 returns in the 7-day window (96 prior returns plus the current one).
- 7-day average: 7 days after the first observation.

### Staleness
- The dashboard shows a "data is stale" warning when `t` was more than 60 minutes old at the time the data was loaded. It's judged at load time, not on each view, because cached data is up to an hour old by design.

## Insights box (dashboard)

Every sentence is built in Python from the KPI columns above. No free text from a model, no numbers that weren't calculated, no hype words, and no buy or sell advice. Every sentence carries at least one real number. A move that rounds to zero says "moved less than 0.01%", never "rose 0.00%". A rule without enough data says nothing. Rules appear in this order, with `t` as defined above:

1. **Biggest mover:** the coin with the largest absolute `pct_change_24h` among the latest observations. "Solana rose 5.35% in 24 hours, the largest move of the 10 coins." Needs at least one coin with `pct_change_24h`.
2. **Latest unusual move:** the newest row with `is_anomaly = TRUE` and `observed_at > t - 24h`. "Latest unusual move: Dogecoin fell 3.26% in 15 minutes at 23:28 UTC (z-score -7.1, threshold 3)." If none are flagged but `checked_24h > 0`: "No unusual 15-minute moves in the last 24 hours, across 960 checks." Nothing if `checked_24h = 0`.
3. **Breadth:** only when 7 or more coins moved the same way over 24h (`pct_change_24h > 0` counts as up, `< 0` as down). "8 of 10 coins are up over 24 hours."
4. **Most volatile coin:** the highest latest `volatility_24h`. "Solana was the most volatile coin over 24 hours: its 15-minute returns had a standard deviation of 0.65%." Needs at least one coin with `volatility_24h`.
5. **7-day market cap trend:** `total_market_cap_change_7d`, computed as KPI 7 but with a 7-day lookback (each coin's market cap at or before `t - 7d`, at most 30 minutes before that mark, and every coin required). "The combined market cap of the 10 coins is up 3.2% over 7 days, at $2.36T." Nothing if any coin lacks a 7-day-ago value.
