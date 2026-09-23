"""Collect write-once, post-004 public open-interest observations.

The OI timestamp is an exchange field, not local feature availability. A full
additional interval and safety lag pass before query; every chunk becomes usable
only after its local collection receipt plus a clock buffer. No alpha is scored.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from tradev2.marketdata.clock import observe_public_clock
from tradev2.research.datasets import BAR_MS
from tradev2.venues.bybit_linear.public import PublicBybit

SAFETY_LAG_MS = 120_000
AVAILABILITY_BUFFER_MS = 5_000
MAX_POINTS_PER_REQUEST = 200


def _write_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _source(root: Path) -> tuple[list[str], str, int]:
    source_path = root / "data/public/alpha_search_004/manifest.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    symbols: list[str] = source["symbols"]
    if len(symbols) != 20 or len(set(symbols)) != 20:
        raise ValueError("fixed Search 004 universe is missing or duplicated")
    result = json.loads((root / "research/results/ALPHA_SEARCH_004.json").read_text(encoding="utf-8"))
    finished_ms = int(datetime.fromisoformat(result["finished_at"]).timestamp() * 1000)
    earliest = (finished_ms // BAR_MS + 1) * BAR_MS
    return symbols, hashlib.sha256(source_path.read_bytes()).hexdigest(), earliest


def _next_timestamp(root: Path, symbols: list[str], source_hash: str,
                    earliest: int) -> int | None:
    next_ms: int | None = None
    for path in sorted((root / "data/public").glob("prospective_oi_*")):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        first = manifest["first_timestamp_ms"]
        last = manifest["last_timestamp_ms"]
        collected = int(datetime.fromisoformat(manifest["collected_at"]).timestamp() * 1000)
        if (path.name != f"prospective_oi_{first}_{last}"
                or manifest["dataset_id"] != f"BYBIT_PUBLIC_OI_FORWARD_{first}_{last}"
                or manifest["interval_ms"] != BAR_MS
                or manifest["symbols"] != symbols
                or manifest["source_universe_manifest_sha256"] != source_hash
                or first < earliest or (next_ms is not None and first != next_ms)
                or last < first or (last - first) % BAR_MS
                or manifest["safe_available_ms"] != max(
                    collected, manifest["latest_response_server_ms"]) + AVAILABILITY_BUFFER_MS):
            raise ValueError(f"prospective OI chain inconsistent: {path.name}")
        if hashlib.sha256((path / "oi.json").read_bytes()).hexdigest() != manifest["oi_sha256"]:
            raise ValueError(f"prospective OI hash drift: {path.name}")
        next_ms = last + BAR_MS
    return next_ms


def _positive_decimal(value: Any, *, field: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid OI {field}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"invalid OI {field}")
    return str(number)


def collect(root: Path, client: PublicBybit, *, first_timestamp_ms: int | None = None) -> dict[str, Any]:
    symbols, source_hash, earliest = _source(root)
    next_ms = _next_timestamp(root, symbols, source_hash, earliest)
    probe = observe_public_clock(client)
    if probe["status"] != "WALL_CLOCK_STABLE":
        raise ValueError("OI collection clock unstable during server-time request")
    server_ms = int(probe["server_ms"])
    # Even if the exchange labels a point by interval *start*, it is closed.
    last = ((server_ms - BAR_MS - SAFETY_LAG_MS) // BAR_MS) * BAR_MS
    first = first_timestamp_ms
    if first is None:
        first = next_ms if next_ms is not None else last - BAR_MS
    if (first % BAR_MS or first < earliest or (next_ms is not None and first != next_ms)
            or last < first):
        raise ValueError("OI must start at the next nonoverlapping post-004 timestamp")
    expected = list(range(first, last + BAR_MS, BAR_MS))
    if len(expected) > MAX_POINTS_PER_REQUEST:
        raise ValueError("OI gap exceeds bounded single-page recovery")
    observations: dict[str, list[list[str | int]]] = {}
    latest_response_server_ms = server_ms
    for symbol in symbols:
        body = client.get("/v5/market/open-interest", {
            "category": "linear", "symbol": symbol, "intervalTime": "15min",
            "endTime": last, "limit": len(expected),
        })
        result = body["result"]
        if result.get("category") != "linear" or result.get("symbol") != symbol:
            raise ValueError(f"OI response identity mismatch: {symbol}")
        response_server_ms = int(body["time"])
        if response_server_ms < server_ms or response_server_ms < last:
            raise ValueError(f"OI response time inconsistent: {symbol}")
        latest_response_server_ms = max(latest_response_server_ms, response_server_ms)
        rows: dict[int, list[str | int]] = {}
        for raw in result["list"]:
            timestamp = int(raw["timestamp"])
            if timestamp not in expected or timestamp in rows:
                raise ValueError(f"OI duplicate or unexpected timestamp: {symbol} {timestamp}")
            rows[timestamp] = [timestamp,
                _positive_decimal(raw["openInterest"], field="total"),
                _positive_decimal(raw["singleOpenInterest"], field="single-side"),
                response_server_ms]
        if set(rows) != set(expected):
            raise ValueError(f"OI timestamp gap: {symbol} {len(rows)}/{len(expected)}")
        observations[symbol] = [rows[timestamp] for timestamp in expected]
    target = root / "data/public" / f"prospective_oi_{first}_{last}"
    target.mkdir(parents=True, exist_ok=False)
    _write_new(target / "oi.json", {"symbols": observations})
    oi_hash = hashlib.sha256((target / "oi.json").read_bytes()).hexdigest()
    collected_at = datetime.now(UTC)
    collected_ms = int(collected_at.timestamp() * 1000)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": f"BYBIT_PUBLIC_OI_FORWARD_{first}_{last}",
        "evidence_role": "PROSPECTIVE_POST004_UNSCORED",
        "source": "Bybit public V5 REST /v5/market/open-interest",
        "source_universe_manifest_sha256": source_hash,
        "first_timestamp_ms": first,
        "last_timestamp_ms": last,
        "interval_ms": BAR_MS,
        "symbols": symbols,
        "points_per_symbol": len(expected),
        "oi_row_fields": ["exchange_timestamp_ms", "both_sides_quantity",
                          "single_side_quantity", "bybit_response_server_ms"],
        "clock_probe": probe,
        "latest_response_server_ms": latest_response_server_ms,
        "collected_at": collected_at.isoformat(),
        "safe_available_ms": max(collected_ms, latest_response_server_ms) + AVAILABILITY_BUFFER_MS,
        "availability_buffer_ms": AVAILABILITY_BUFFER_MS,
        "oi_sha256": oi_hash,
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": [
            "OI timestamp is not a local receipt or proof of first publication time",
            "historical OI outcomes are consumed discovery data, not a fresh holdout",
            "both-sides OI quantity is denominated in each symbol's base unit",
            "no trade signal may use this chunk before safe_available_ms",
        ],
    }
    _write_new(target / "manifest.json", manifest)
    if hashlib.sha256((target / "oi.json").read_bytes()).hexdigest() != oi_hash:
        raise AssertionError("OI read-back hash mismatch")
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    client = PublicBybit()
    try:
        print(json.dumps(collect(root, client), indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
