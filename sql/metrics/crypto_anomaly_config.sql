-- Tunable anomaly settings. Change the value here, redeploy, and log it in docs/DECISIONS.md.
-- The anomaly view cross-joins this one-row view, and the dashboard reads it to label the threshold.
CREATE OR REPLACE VIEW `crypto-analytics-pipeline-lc.crypto_metrics.anomaly_config` AS
SELECT 3.0 AS z_threshold;
