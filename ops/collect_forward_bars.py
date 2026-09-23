"""Collect immutable, post-004 public 15m candles for the fixed 004 universe.

This is prospective context for later beta attribution, not an alpha search or
an untouched holdout merely because it has not yet been scored.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradev2.research.datasets import BAR_MS
from tradev2.venues.bybit_linear.public import PublicBybit

SAFETY_LAG_MS = 120_000


def _write_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def collect(root: Path, client: PublicBybit, *, first_open_ms: int) -> dict[str, Any]:
    source_path = root / "data/public/alpha_search_004/manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = json.loads((root / "research/results/ALPHA_SEARCH_004.json").read_text(encoding="utf-8"))
    finished_ms = int(datetime.fromisoformat(result["finished_at"]).timestamp() * 1000)
    earliest = (finished_ms // BAR_MS + 1) * BAR_MS
    if first_open_ms % BAR_MS or first_open_ms < earliest:
        raise ValueError("first bar must open strictly after Search 004 finished")
    server_ms = client.server_time()
    last_open_ms = ((server_ms - SAFETY_LAG_MS) // BAR_MS - 1) * BAR_MS
    if last_open_ms < first_open_ms:
        raise ValueError("no safety-lagged, confirmed prospective bars yet")
    expected = list(range(first_open_ms, last_open_ms + BAR_MS, BAR_MS))
    symbols = source["symbols"]
    if len(symbols) != 20 or len(set(symbols)) != 20:
        raise ValueError("Search 004 fixed universe is missing or duplicated")
    bars: dict[str, Any] = {}
    for symbol in symbols:
        by_start: dict[int, list[str | int]] = {}
        end = last_open_ms + BAR_MS - 1
        while end >= first_open_ms:
            page = client.candles(symbol, limit=200, end_ms=end)
            if not page:
                raise ValueError(f"public candle history ended early: {symbol}")
            for candle in page:
                opened = candle.start_ms
                if first_open_ms <= opened <= last_open_ms:
                    if (candle.symbol != symbol or candle.interval_ms != BAR_MS
                            or candle.ingested_ms is None):
                        raise ValueError(f"candle identity or ingestion time missing: {symbol} {opened}")
                    if not candle.confirmed or opened + BAR_MS > server_ms - SAFETY_LAG_MS:
                        raise ValueError(f"unconfirmed candle: {symbol} {opened}")
                    if (candle.low <= 0 or candle.open <= 0 or candle.close <= 0
                            or candle.high < max(candle.open, candle.close)
                            or candle.low > min(candle.open, candle.close)
                            or candle.volume < 0):
                        raise ValueError(f"invalid OHLCV: {symbol} {opened}")
                    row: list[str | int] = [opened, str(candle.open), str(candle.high),
                                            str(candle.low), str(candle.close),
                                            str(candle.volume), candle.ingested_ms]
                    if opened in by_start and by_start[opened][:6] != row[:6]:
                        raise ValueError(f"conflicting candle: {symbol} {opened}")
                    by_start[opened] = row
            oldest = min(candle.start_ms for candle in page)
            if oldest > end:
                raise ValueError(f"candle pagination failed: {symbol}")
            end = oldest - 1
        if set(by_start) != set(expected):
            raise ValueError(f"prospective candle gap: {symbol} {len(by_start)}/{len(expected)}")
        bars[symbol] = [by_start[opened] for opened in expected]
    target = root / "data/public" / f"prospective_bars_{first_open_ms}_{last_open_ms}"
    target.mkdir(parents=True, exist_ok=False)
    _write_new(target / "bars.json", {"symbols": bars})
    bar_hash = hashlib.sha256((target / "bars.json").read_bytes()).hexdigest()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": f"BYBIT_PUBLIC_FORWARD_{first_open_ms}_{last_open_ms}",
        "evidence_role": "PROSPECTIVE_POST004_UNSCORED",
        "source": "Bybit public V5 REST /v5/market/kline",
        "source_universe_manifest_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "selection": "fixed 20-symbol Search 004 universe; no post-outcome reranking",
        "first_open_ms": first_open_ms,
        "last_open_ms": last_open_ms,
        "server_time_ms": server_ms,
        "collected_at": datetime.now(UTC).isoformat(),
        "interval_ms": BAR_MS,
        "bars_per_symbol": len(expected),
        "symbols": symbols,
        "bars_sha256": bar_hash,
        "limitations": ["candles do not establish order-book or trade-flow history",
                        "fixed universe was chosen using turnover observed for Search 004",
                        "this data is not a sealed holdout until a later preregistration says so"],
    }
    _write_new(target / "manifest.json", manifest)
    if hashlib.sha256((target / "bars.json").read_bytes()).hexdigest() != bar_hash:
        raise AssertionError("public candle read-back hash mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-open-ms", type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = PublicBybit()
    try:
        print(json.dumps(collect(root, client, first_open_ms=args.first_open_ms), indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
