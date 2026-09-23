"""One-shot public-only acquisition for a post-003 research slice.

The raw REST responses and observed book are retained under ignored target-local data.
The manifest is content-addressed; rerunning never overwrites a completed dataset.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from tradev2.research.datasets import BAR_MS, FloatArray, Panel, sha256_file
from tradev2.venues.bybit_linear.public import PublicBybit

SEARCH_ID = "TRADEV2_ALPHA_SEARCH_004"
DATASET_ID = "BYBIT_PUBLIC_POST003_004"
PRIOR_LAST_OPEN_MS = 1_788_903_900_000
MIN_TURNOVER_USDT = Decimal("20000000")


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def collect(root: Path, *, max_symbols: int = 20) -> dict[str, Any]:
    target = root / "data/public/alpha_search_004"
    if target.exists():
        raise FileExistsError("Search 004 public dataset already exists; inspect, never overwrite")
    client = PublicBybit()
    try:
        server_ms = client.server_time()
        last_open = (server_ms // BAR_MS - 1) * BAR_MS
        first_open = PRIOR_LAST_OPEN_MS + BAR_MS
        if last_open - first_open < 10 * 86_400_000:
            raise ValueError("fewer than ten new public days since consumed search")
        instruments = client.instruments()
        tickers = client.get("/v5/market/tickers", {"category": "linear"})["result"]["list"]
        candidates = sorted((row for row in tickers
            if row["symbol"] in instruments
            and Decimal(row.get("turnover24h") or "0") >= MIN_TURNOVER_USDT),
            key=lambda row: (-Decimal(row["turnover24h"]), row["symbol"]))
        names = ["BTCUSDT", "ETHUSDT"]
        names += [row["symbol"] for row in candidates
                  if row["symbol"] not in names][:max_symbols - 2]
        if len(names) != max_symbols:
            raise ValueError("insufficient liquid trading instruments")
        funding_by_symbol: dict[str, list[tuple[int, Decimal]]] = {}
        for symbol in names:
            history = client.funding_history(symbol)
            times = [item.funding_ms for item in history if item.funding_ms is not None]
            while times and min(times) > first_open:
                older = client.funding_history(symbol,
                    end_ms=min(times) - 1)
                older_times = [item.funding_ms for item in older if item.funding_ms is not None]
                if not older_times or min(older_times) >= min(times):
                    raise ValueError(f"funding pagination stalled: {symbol}")
                history.extend(older)
                times.extend(older_times)
            funding_by_symbol[symbol] = sorted({(item.funding_ms, item.rate)
                for item in history if item.funding_ms is not None and item.rate is not None})
        last_settlement = min(values[-1][0] for values in funding_by_symbol.values())
        last_open = min(last_open, (last_settlement // BAR_MS - 1) * BAR_MS)
        if last_open - first_open < 10 * 86_400_000:
            raise ValueError("funding-covered fresh dataset shorter than ten days")
        raw: dict[str, Any] = {}
        arrays: list[FloatArray] = []
        economics: dict[str, Any] = {}
        for symbol in names:
            book = client.orderbook(symbol)
            if book.spread_bps is None or book.exchange_event_ms is None:
                raise ValueError(f"book/spread unavailable for {symbol}")
            rules = instruments[symbol]
            end = last_open + BAR_MS - 1
            rows: dict[int, list[str]] = {}
            while end >= first_open:
                response = client.get("/v5/market/kline", {"category": "linear",
                    "symbol": symbol, "interval": "15", "limit": 1000, "end": end})
                page = response["result"]["list"]
                if not page:
                    raise ValueError(f"kline pagination empty for {symbol}")
                for row in page:
                    ts = int(row[0])
                    if first_open <= ts <= last_open and ts + BAR_MS <= server_ms:
                        if ts in rows and rows[ts] != row:
                            raise ValueError(f"conflicting candle duplicate: {symbol} {ts}")
                        rows[ts] = row
                oldest = min(int(row[0]) for row in page)
                if oldest >= end:
                    raise ValueError(f"kline pagination stalled: {symbol}")
                end = oldest - 1
            expected = np.arange(first_open, last_open + BAR_MS, BAR_MS, dtype=np.int64)
            if len(rows) != len(expected) or set(rows) != set(expected.tolist()):
                raise ValueError(f"public 15m candle gap for {symbol}: {len(rows)}/{len(expected)}")
            ordered = [rows[int(ts)] for ts in expected]
            values = np.asarray([[float(row[i]) for i in range(1, 6)] for row in ordered],
                                dtype=np.float64)
            observations = [[when, str(rate)] for when, rate in funding_by_symbol[symbol]]
            stamps = funding_by_symbol[symbol]
            if len(stamps) < 2 or stamps[0][0] > first_open or stamps[-1][0] < last_open + BAR_MS:
                raise ValueError(f"settled funding does not span dataset for {symbol}")
            spread = str(book.spread_bps)
            economics[symbol] = {"maker_rate": "0.0002", "taker_rate": "0.00055",
                "spread_bps": spread, "qty_step": str(rules.qty_step),
                "min_qty": str(rules.min_qty), "min_notional": str(rules.min_notional),
                "max_qty": str(rules.max_qty), "funding": observations,
                "provenance": "2026-09-02 published VIP0 fees; current public book/rules; settled funding"}
            raw[symbol] = {"candles": ordered, "book": book.model_dump(mode="json"),
                "turnover24h": next((row["turnover24h"] for row in candidates
                    if row["symbol"] == symbol), None),
                "rules": rules.model_dump(mode="json"), "funding": observations}
            arrays.append(values)
        panel = Panel(tuple(names), expected, np.stack(arrays, axis=1),
                      {"source": "fresh_public_rest_post003"})
        target.mkdir(parents=True, exist_ok=False)
        _write_new(target / "raw.json", raw)
        _write_new(target / "economics.json", {"symbols": economics})
        np.savez_compressed(target / "candles_15m.npz", timestamps=panel.timestamps,
                            symbols=np.asarray(panel.symbols), values=panel.values)
        files = {name: sha256_file(target / name) for name in
                 ("raw.json", "economics.json", "candles_15m.npz")}
        manifest = {"schema_version": 1, "dataset_id": DATASET_ID, "search_id": SEARCH_ID,
            "source": "Bybit public V5 REST", "evidence_role": "NEW_POST003_RESEARCH_CONSUMED_ON_SEARCH",
            "collected_at": datetime.now(UTC).isoformat(), "server_time_ms": server_ms,
            "first_open_ms": first_open, "last_open_ms": last_open,
            "interval_ms": BAR_MS, "bars_per_symbol": len(expected), "symbols": names,
            "selection": {"turnover24h_min_usdt": str(MIN_TURNOVER_USDT),
                          "rank": "current turnover24h descending", "max_symbols": max_symbols,
                          "survivorship_bias": "current selection, not point-in-time universe"},
            "files_sha256": files, "raw_sha256": hashlib.sha256((target / "raw.json").read_bytes()).hexdigest(),
            "limitations": ["Current spread, rules and fee schedule are not historical time series",
                "REST book is a collection snapshot, not historical queue depth",
                "OHLCV volume is not aggressor-signed trade flow",
                "Funding uses settlement rates and entry-notional approximation"]}
        _write_new(target / "manifest.json", manifest)
        return manifest
    finally:
        client.close()


def load_fresh(root: Path) -> Panel:
    target = root / "data/public/alpha_search_004"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_id"] != DATASET_ID:
        raise ValueError("wrong Search 004 dataset")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(target / name) != digest:
            raise ValueError(f"Search 004 dataset hash drift: {name}")
    with np.load(target / "candles_15m.npz", allow_pickle=False) as archive:
        return Panel(tuple(str(item) for item in archive["symbols"]),
                     archive["timestamps"].astype(np.int64),
                     archive["values"].astype(np.float64), manifest)
