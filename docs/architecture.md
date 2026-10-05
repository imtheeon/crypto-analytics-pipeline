# Architecture

```mermaid
flowchart LR
    CG["CoinGecko API<br/>/coins/markets<br/>10 coins, 1 call"]
    GA["GitHub Actions<br/>every 15 min<br/>(Phase 3)"]
    PY["ingestion/<br/>crypto_ingest.py<br/>retry + backoff"]
    subgraph BQ["BigQuery · crypto-analytics-pipeline-lc · US"]
        RAW[("crypto_raw.prices<br/>append-only")]
        CLEAN[("crypto_clean.prices<br/>view, deduped")]
        MET[("crypto_metrics.*<br/>SQL views")]
    end
    T{{"data tests<br/>dupes · nulls · stale"}}
    DASH["dashboard/<br/>Streamlit + Plotly<br/>60s refresh<br/>(Phase 4)"]

    GA -->|runs| PY
    CG -->|JSON| PY
    PY -->|load job| RAW
    RAW --> CLEAN --> MET
    T -. checks .-> CLEAN
    MET -->|read only| DASH
```

- Logic lives in SQL. The dashboard only reads `crypto_metrics` views.
- Auth: local runs and Actions both use the `crypto-pipeline-sa` service account.
  - Locally, the key file is at `%USERPROFILE%\.gcp\crypto-pipeline-sa.json` and `GOOGLE_APPLICATION_CREDENTIALS` points to it.
  - In Actions, the key comes from the `CRYPTO_GCP_KEY` secret.
