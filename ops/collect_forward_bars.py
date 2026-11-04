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

from tradev2.marketdata.clock import observe_public_clock
from tradev2.research.datasets import BAR_MS
from tradev2.venues.bybit_linear.public import PublicBybit

SAFETY_LAG_MS = 120_000
# A bar first collected more than this after its close is later-observed backfill.
CONTEMPORANEOUS_LAG_MS = 3_600_000
AVAILABILITY_BUFFER_MS = 5_000


class NotDueError(ValueError):
    """No newly closed, safety-lagged interval exists yet; nothing was written."""


def _write_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def safe_available_ms(manifest: dict[str, Any]) -> int:
    """Conservative availability bound, including pre-field v1 chunks.

    Schema 1 used local receipt only; schema 2 also waits for the latest exchange
    response time, matching the OI chain, because the host clock may lag the venue.
    """
    stored = manifest.get("safe_available_ms")
    collected = int(datetime.fromisoformat(manifest["collected_at"]).timestamp() * 1000)
    if int(manifest.get("schema_version", 1)) >= 2:
        collected = max(collected, int(manifest["latest_response_server_ms"]))
    expected = collected + AVAILABILITY_BUFFER_MS
    if stored is not None and int(stored) != expected:
        raise ValueError("prospective candle availability timestamp mismatch")
    return expected


def _next_open(root: Path, earliest: int, symbols: list[str], source_hash: str) -> int:
    next_open = earliest
    for path in sorted((root / "data/public").glob("prospective_bars_*")):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        first = manifest["first_open_ms"]
        last = manifest["last_open_ms"]
        if (path.name != f"prospective_bars_{first}_{last}"
                or manifest["dataset_id"] != f"BYBIT_PUBLIC_FORWARD_{first}_{last}"
                or manifest["interval_ms"] != BAR_MS
                or manifest["symbols"] != symbols
                or manifest["source_universe_manifest_sha256"] != source_hash
                or first != next_open or last < first or (last - first) % BAR_MS
                or safe_available_ms(manifest) < last + BAR_MS):
            raise ValueError(f"prior prospective candle chain is inconsistent: {path.name}")
        if hashlib.sha256((path / "bars.json").read_bytes()).hexdigest() != manifest["bars_sha256"]:
            raise ValueError(f"prior prospective candle hash drift: {path.name}")
        next_open = last + BAR_MS
    return next_open


def next_open(root: Path) -> int:
    source_path = root / "data/public/alpha_search_004/manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = json.loads((root / "research/results/ALPHA_SEARCH_004.json").read_text(encoding="utf-8"))
    finished_ms = int(datetime.fromisoformat(result["finished_at"]).timestamp() * 1000)
    earliest = (finished_ms // BAR_MS + 1) * BAR_MS
    return _next_open(root, earliest, source["symbols"],
                      hashlib.sha256(source_path.read_bytes()).hexdigest())


def collect(root: Path, client: PublicBybit, *, first_open_ms: int) -> dict[str, Any]:
    source_path = root / "data/public/alpha_search_004/manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = json.loads((root / "research/results/ALPHA_SEARCH_004.json").read_text(encoding="utf-8"))
    finished_ms = int(datetime.fromisoformat(result["finished_at"]).timestamp() * 1000)
    earliest = (finished_ms // BAR_MS + 1) * BAR_MS
    symbols: list[str] = source["symbols"]
    if len(symbols) != 20 or len(set(symbols)) != 20:
        raise ValueError("Search 004 fixed universe is missing or duplicated")
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if first_open_ms % BAR_MS or first_open_ms != _next_open(root, earliest, symbols, source_hash):
        raise ValueError("first bar must be the next nonoverlapping post-004 interval")
    # Preserve a target-local bracket around the public server timestamp.
    # Cross-clock event lag cannot be interpreted without a contemporaneous
    # offset bound; the host wall clock may not be synchronized.
    clock_probe = observe_public_clock(client)
    if clock_probe["status"] != "WALL_CLOCK_STABLE":
        raise ValueError("candle collection clock unstable during server-time request")
    server_ms = int(clock_probe["server_ms"])
    latest_response_server_ms = server_ms
    last_open_ms = ((server_ms - SAFETY_LAG_MS) // BAR_MS - 1) * BAR_MS
    if last_open_ms < first_open_ms:
        raise NotDueError("no safety-lagged, confirmed prospective bars yet")
    expected = list(range(first_open_ms, last_open_ms + BAR_MS, BAR_MS))
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
                    latest_response_server_ms = max(latest_response_server_ms,
                                                    int(candle.ingested_ms))
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
    collected_at = datetime.now(UTC)
    collected_ms = int(collected_at.timestamp() * 1000)
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "dataset_id": f"BYBIT_PUBLIC_FORWARD_{first_open_ms}_{last_open_ms}",
        "evidence_role": "PROSPECTIVE_POST004_UNSCORED",
        "source": "Bybit public V5 REST /v5/market/kline",
        "source_universe_manifest_sha256": source_hash,
        "selection": "fixed 20-symbol Search 004 universe; no post-outcome reranking",
        "observation_mode": ("BACKFILL_LATER_OBSERVED"
                             if collected_ms - (first_open_ms + BAR_MS) > CONTEMPORANEOUS_LAG_MS
                             else "CONTEMPORANEOUS"),
        "first_open_ms": first_open_ms,
        "last_open_ms": last_open_ms,
        "server_time_ms": server_ms,
        "clock_probe": clock_probe,
        "collected_at": collected_at.isoformat(),
        "latest_response_server_ms": latest_response_server_ms,
        "safe_available_ms": max(collected_ms, latest_response_server_ms) + AVAILABILITY_BUFFER_MS,
        "availability_buffer_ms": AVAILABILITY_BUFFER_MS,
        "bar_row_fields": ["open_ms", "open", "high", "low", "close", "volume",
                           "bybit_response_server_ms"],
        "interval_ms": BAR_MS,
        "bars_per_symbol": len(expected),
        "symbols": symbols,
        "bars_sha256": bar_hash,
        "limitations": ["candles do not establish order-book or trade-flow history",
                        "fixed universe was chosen using turnover observed for Search 004",
                        "this data is not a sealed holdout until a later preregistration says so",
                        "the bar row response time is not local ingestion; downstream decisions must not use this chunk before safe_available_ms"],
    }
    _write_new(target / "manifest.json", manifest)
    if hashlib.sha256((target / "bars.json").read_bytes()).hexdigest() != bar_hash:
        raise AssertionError("public candle read-back hash mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-open-ms", type=int)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Trade v2 checkout that holds data/public and research/results")
    args = parser.parse_args()
    root = args.root.resolve()
    first_open_ms = args.first_open_ms if args.first_open_ms is not None else next_open(root)
    client = PublicBybit()
    try:
        print(json.dumps(collect(root, client, first_open_ms=first_open_ms), indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
