"""Run SQL test scripts in BigQuery. A failed ASSERT raises, so the process exits non-zero.

Run:  python tests/run_sql_tests.py sql/tests/crypto_data_tests.sql sql/tests/crypto_freshness_tests.sql
Env:  GOOGLE_APPLICATION_CREDENTIALS (path to the crypto-pipeline-sa key)
Each script gets @coins, the coin list from ingestion/crypto_coins.json.
"""
import json
import sys
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
coins = json.loads((ROOT / "ingestion" / "crypto_coins.json").read_text())["coins"]
client = bigquery.Client(project="crypto-analytics-pipeline-lc")
config = bigquery.QueryJobConfig(query_parameters=[bigquery.ArrayQueryParameter("coins", "STRING", coins)])
for path in sys.argv[1:]:
    client.query(Path(path).read_text(), job_config=config).result()
    print(f"passed: {path}")
