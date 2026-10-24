"""Add independently downloaded BTC/ETH public 15m bars to reused discovery data.

Only target-local ignored data is written. No authenticated endpoint or source
repository path is used. An existing target dataset is never overwritten.
"""

import argparse
import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from tradev2.research.datasets import BAR_MS, FloatArray, json_write, load_panel, sha256_file
from tradev2.venues.bybit_linear.public import PublicBybit

SYMBOLS = ("BTCUSDT", "ETHUSDT")


def _candles(client: PublicBybit, symbol: str, first_ms: int, last_ms: int) -> list[list[str]]:
    by_start: dict[int, list[str]] = {}
    end = last_ms
    while end >= first_ms:
        body = client.get("/v5/market/kline", {"category": "linear", "symbol": symbol,
                                               "interval": "15", "end": end, "limit": 1000})
        page = body["result"]["list"]
        if not page:
            raise ValueError(f"{symbol} public candle history ended early")
        for row in page:
            opened = int(row[0])
            if first_ms <= opened <= last_ms:
                if opened in by_start and by_start[opened] != row:
                    raise ValueError("historical candle response changed within download")
                by_start[opened] = row
        oldest = min(int(row[0]) for row in page)
        if oldest > end:
            raise ValueError("candle pagination failed to advance")
        end = oldest - 1
        time.sleep(.12)
    ordered = [by_start[timestamp] for timestamp in range(first_ms, last_ms + BAR_MS, BAR_MS)]
    if len(ordered) != (last_ms - first_ms) // BAR_MS + 1:
        raise ValueError("public candle range incomplete")
    return ordered


def _funding(client: PublicBybit, symbol: str, first_ms: int, last_ms: int) -> list[dict[str, str]]:
    observations: dict[int, dict[str, str]] = {}
    end = last_ms + 86_400_000
    while end >= first_ms - 86_400_000:
        body = client.get("/v5/market/funding/history", {"category": "linear",
                                                      "symbol": symbol, "endTime": end,
                                                      "limit": 200})
        page = body["result"]["list"]
        if not page:
            raise ValueError(f"{symbol} public funding history ended early")
        for row in page:
            timestamp = int(row["fundingRateTimestamp"])
            if first_ms - 86_400_000 <= timestamp <= last_ms + 86_400_000:
                observations[timestamp] = row
        oldest = min(int(row["fundingRateTimestamp"]) for row in page)
        if oldest > end:
            raise ValueError("funding pagination failed to advance")
        end = oldest - 1
        time.sleep(.12)
    ordered = [observations[key] for key in sorted(observations)]
    if not ordered or int(ordered[0]["fundingRateTimestamp"]) > first_ms:
        raise ValueError("no settled funding before first candle")
    if int(ordered[-1]["fundingRateTimestamp"]) < last_ms:
        raise ValueError("no settled funding after last candle")
    return ordered


def build(root: Path, source: Path, target: Path) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError("public research dataset is immutable once created")
    panel = load_panel(source)
    original_economics = json.loads((source / "economics.json").read_text(encoding="utf-8"))
    first, last = int(panel.timestamps[0]), int(panel.timestamps[-1])
    retrieved: dict[str, dict[str, Any]] = {}
    client = PublicBybit()
    try:
        for symbol in SYMBOLS:
            print(f"fetching public {symbol} 15m candles and settled funding", flush=True)
            candles = _candles(client, symbol, first, last)
            funding = _funding(client, symbol, first, last)
            instrument = client.get("/v5/market/instruments-info", {"category": "linear",
                                                                    "symbol": symbol})["result"]["list"][0]
            if instrument["symbol"] != symbol or instrument["status"] != "Trading":
                raise ValueError("unexpected public instrument identity")
            book = client.orderbook(symbol)
            if book.spread_bps is None:
                raise ValueError("current public spread unavailable; no zero fallback")
            retrieved[symbol] = {"candles": candles, "funding": funding,
                                 "instrument": instrument, "observed_spread_bps": str(book.spread_bps),
                                 "book_event_ms": book.exchange_event_ms}
    finally:
        client.close()
    arrays: dict[str, FloatArray] = {symbol: panel.values[:, index, :]
                                     for index, symbol in enumerate(panel.symbols)}
    economics = deepcopy(original_economics)
    manifest = deepcopy(panel.manifest)
    target.mkdir(parents=True)
    for symbol in SYMBOLS:
        evidence = retrieved[symbol]
        json_write(target / f"{symbol}_public_raw.json", evidence)
        rows = evidence["candles"]
        values = np.asarray([[float(row[index]) for index in (1, 2, 3, 4, 5)]
                             for row in rows], dtype=np.float64)
        arrays[symbol] = values
        instrument = evidence["instrument"]
        lot = instrument["lotSizeFilter"]
        spread = max(3., float(evidence["observed_spread_bps"]))
        economics["symbols"][symbol] = {
            "maker_rate": .0002, "taker_rate": .00055, "spread_bps": spread,
            "spread_observed_median_bps": None,
            "qty_step": lot["qtyStep"], "min_qty": lot["minOrderQty"],
            "min_notional": lot["minNotionalValue"], "max_qty": lot["maxOrderQty"],
            "funding": [[int(row["fundingRateTimestamp"]), float(row["fundingRate"])]
                        for row in evidence["funding"]],
            "instrument": instrument,
            "provenance": "public point-in-time candles/funding; conservative UNVERIFIED fee proxy; current spread/rules"}
        manifest["sources"].append({"symbol": symbol, "endpoint": "Bybit public V5 REST",
                                    "raw_sha256": sha256_file(target / f"{symbol}_public_raw.json"),
                                    "bars": len(rows), "funding_observations": len(evidence["funding"])})
    symbols = tuple(sorted(arrays))
    values = np.stack([arrays[symbol] for symbol in symbols], axis=1)
    np.savez_compressed(target / "candles_15m.npz", timestamps=panel.timestamps,
                        symbols=np.asarray(symbols), values=values)
    economics["limitations"].append(
        "BTC/ETH fees are conservative explicit proxies, not measured account-specific history")
    economics["limitations"].append(
        "BTC/ETH spread is max(3bps, one current snapshot); not historical L2 spread")
    json_write(target / "economics.json", economics)
    manifest.update({"dataset_id": "BYBIT_PUBLIC_REUSED_39_OHLCV_210D",
                     "symbols": list(symbols), "sha256": sha256_file(target / "candles_15m.npz"),
                     "dataset_parent_sha256": panel.manifest["sha256"],
                     "new_public_symbols": list(SYMBOLS),
                     "evidence_role": "REUSED_HISTORICAL_DISCOVERY",
                     "prior_consumption": "Original 37-symbol data consumed in legacy and initial campaigns; BTC/ETH historical download is not a fresh holdout",
                     "untouched_holdout": False})
    json_write(target / "manifest.json", manifest)
    verified = load_panel(target)
    if verified.symbols != symbols or not np.array_equal(verified.values, values):
        raise AssertionError("new public panel did not survive read-back")
    return {"dataset_id": manifest["dataset_id"], "symbols": len(symbols),
            "bars_per_symbol": len(panel.timestamps), "sha256": manifest["sha256"],
            "economics_sha256": sha256_file(target / "economics.json")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    print(json.dumps(build(root, root / "data/public/initial_campaign",
                           root / "data/public/completion_campaign"), indent=2))


if __name__ == "__main__":
    main()
