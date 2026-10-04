"""Run: python tests/test_crypto_ingest.py  (or pytest)"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
from crypto_ingest import build_rows  # noqa: E402

COINS = ["bitcoin", "ethereum", "solana"]
RECORDS = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 62000, "market_cap": "bad",
     "market_cap_rank": 1, "total_volume": None, "last_updated": "2026-10-04T23:30:00.000Z"},
    {"id": "bitcoin", "current_price": 1, "last_updated": "2026-10-04T23:31:00.000Z"},  # repeat id
    {"id": "ethereum", "current_price": 2500.5, "last_updated": None},                # no timestamp
    {"id": "dogecoin", "current_price": 0.1, "last_updated": "2026-10-04T23:30:00.000Z"},  # not asked for
]


def test_build_rows():
    rows = build_rows(RECORDS, COINS, "run-1", "2026-10-04T23:30:05+00:00")
    assert [r["coin_id"] for r in rows] == ["bitcoin"]
    btc = rows[0]
    assert btc["current_price"] == 62000.0 and isinstance(btc["current_price"], float)
    assert btc["market_cap"] is None          # bad value -> None, not 0
    assert btc["total_volume"] is None
    assert btc["high_24h"] is None            # missing key -> None
    assert btc["market_cap_rank"] == 1
    assert btc["ingestion_id"] == "run-1"
    assert json.loads(btc["payload"])["symbol"] == "btc"


def test_empty_response():
    assert build_rows([], COINS, "run-2", "2026-10-04T23:45:05+00:00") == []


if __name__ == "__main__":
    test_build_rows()
    test_empty_response()
    print("ok")
