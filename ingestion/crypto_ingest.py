"""Fetch CoinGecko market snapshots for the coins in crypto_coins.json.

Run:  python ingestion/crypto_ingest.py
Env:  CRYPTO_COINGECKO_API_KEY (CoinGecko Demo key)
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://api.coingecko.com/api/v3/coins/markets"
CONFIG_PATH = Path(__file__).with_name("crypto_coins.json")
FLOAT_FIELDS = ["current_price", "market_cap", "total_volume", "high_24h", "low_24h",
                "price_change_percentage_24h"]

log = logging.getLogger("crypto_ingest")


def load_config():
    return json.loads(CONFIG_PATH.read_text())


def fetch_markets(coins, vs_currency, api_key):
    """One call for all coins. Retries 429 and 5xx with exponential backoff, honouring Retry-After."""
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    resp = session.get(
        API_URL,
        params={"vs_currency": vs_currency, "ids": ",".join(coins), "per_page": 250},
        headers={"x-cg-demo-api-key": api_key, "accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected a list from CoinGecko, got {type(data).__name__}")
    return data


def _to_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def build_rows(records, coins, ingestion_id, ingested_at):
    """Map API records to crypto_raw.prices rows.

    Drops records for coins we didn't ask for, records missing id or last_updated,
    and repeat ids within one response. Bad numbers become None, never 0.
    """
    wanted = set(coins)
    rows, seen = [], set()
    for rec in records:
        coin_id, last_updated = rec.get("id"), rec.get("last_updated")
        if coin_id not in wanted or coin_id in seen:
            continue
        if not last_updated:
            log.warning("Skipping %s: no last_updated", coin_id)
            continue
        seen.add(coin_id)
        row = {
            "ingestion_id": ingestion_id,
            "ingested_at": ingested_at,
            "coin_id": coin_id,
            "symbol": rec.get("symbol"),
            "name": rec.get("name"),
            "market_cap_rank": _to_int(rec.get("market_cap_rank")),
            "last_updated": last_updated,
            "payload": json.dumps(rec),
        }
        row.update({f: _to_float(rec.get(f)) for f in FLOAT_FIELDS})
        rows.append(row)
    missing = wanted - seen
    if missing:
        log.warning("No usable data for: %s", ", ".join(sorted(missing)))
    return rows


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_key = os.environ.get("CRYPTO_COINGECKO_API_KEY")
    if not api_key:
        sys.exit("CRYPTO_COINGECKO_API_KEY is not set")
    cfg = load_config()
    records = fetch_markets(cfg["coins"], cfg["vs_currency"], api_key)
    rows = build_rows(records, cfg["coins"], str(uuid.uuid4()),
                      datetime.now(timezone.utc).isoformat())
    log.info("Fetched %d records, built %d rows", len(records), len(rows))
    def fmt(v, places):
        return "n/a" if v is None else f"{v:,.{places}f}"
    for r in rows:
        print(f"{r['coin_id']:<13} ${fmt(r['current_price'], 4):>13}  cap ${fmt(r['market_cap'], 0):>18}"
              f"  vol ${fmt(r['total_volume'], 0):>16}  {r['last_updated']}")
    return rows


if __name__ == "__main__":
    main()
