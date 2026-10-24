"""Collect write-once, post-004 public open-interest observations.

The OI timestamp is an exchange field, not local feature availability. A full
additional interval and safety lag pass before query; every chunk becomes usable
only after its local collection receipt plus a clock buffer. No alpha is scored.

Chains: chain 1 is the original `prospective_oi_<first>_<last>` series. When a chain
cannot continue because its gap exceeds the bounded single-page recovery, an operator
may start the next chain (`prospective_oi<n>_<first>_<last>`) with an explicit reason.
Its genesis manifest records the predecessor's final point and the exact unobserved
gap. Gaps are never backfilled into a chain, and only the newest chain is extended.
"""

import argparse
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


def chain_id(number: int) -> str:
    return f"OI_CHAIN_{number:03d}"


def chain_prefix(number: int) -> str:
    return "prospective_oi_" if number == 1 else f"prospective_oi{number}_"


def dataset_prefix(number: int) -> str:
    return "BYBIT_PUBLIC_OI_FORWARD_" if number == 1 else f"BYBIT_PUBLIC_OI_FORWARD{number}_"


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


def chain_numbers(root: Path) -> list[int]:
    """Chain numbers present on disk; they must be exactly 1..N."""
    numbers: set[int] = set()
    for path in (root / "data/public").glob("prospective_oi*_*"):
        if not path.is_dir():
            continue
        suffix = path.name.split("_")[1][2:]
        if suffix == "":
            numbers.add(1)
        elif suffix.isdigit() and int(suffix) >= 2:
            numbers.add(int(suffix))
        else:
            raise ValueError(f"unrecognized prospective OI directory: {path.name}")
    ordered = sorted(numbers)
    if ordered and ordered != list(range(1, ordered[-1] + 1)):
        raise ValueError(f"prospective OI chains are not consecutive: {ordered}")
    return ordered


class ChainState:
    def __init__(self, number: int) -> None:
        self.number = number
        self.next_ms: int | None = None
        self.anchor: dict[str, list[str | int]] | None = None
        self.last_name: str | None = None
        self.last_sha256: str | None = None


def _validate_chain(root: Path, number: int, symbols: list[str], source_hash: str,
                    earliest: int, predecessor: ChainState | None) -> ChainState:
    state = ChainState(number)
    prefix, dataset = chain_prefix(number), dataset_prefix(number)
    for index, path in enumerate(sorted((root / "data/public").glob(f"{prefix}*"))):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        first = manifest["first_timestamp_ms"]
        last = manifest["last_timestamp_ms"]
        collected = int(datetime.fromisoformat(manifest["collected_at"]).timestamp() * 1000)
        if (path.name != f"{prefix}{first}_{last}"
                or manifest["dataset_id"] != f"{dataset}{first}_{last}"
                or manifest["interval_ms"] != BAR_MS
                or manifest["symbols"] != symbols
                or manifest["source_universe_manifest_sha256"] != source_hash
                or first < earliest or (state.next_ms is not None and first != state.next_ms)
                or last < first or (last - first) % BAR_MS
                or manifest["safe_available_ms"] != max(
                    collected, manifest["latest_response_server_ms"]) + AVAILABILITY_BUFFER_MS):
            raise ValueError(f"prospective OI chain inconsistent: {path.name}")
        if number >= 2:
            record = manifest.get("chain") or {}
            if record.get("chain_id") != chain_id(number):
                raise ValueError(f"prospective OI chain identity mismatch: {path.name}")
            if index == 0:
                _check_genesis(record, first, predecessor, path.name)
            elif "predecessor" in record or "gap" in record:
                raise ValueError(f"only a chain genesis may record a gap: {path.name}")
        if hashlib.sha256((path / "oi.json").read_bytes()).hexdigest() != manifest["oi_sha256"]:
            raise ValueError(f"prospective OI hash drift: {path.name}")
        stored = json.loads((path / "oi.json").read_text(encoding="utf-8"))["symbols"]
        if set(stored) != set(symbols):
            raise ValueError(f"prospective OI stored universe mismatch: {path.name}")
        state.anchor = {symbol: stored[symbol][-1] for symbol in symbols}
        if any(int(row[0]) != last for row in state.anchor.values()):
            raise ValueError(f"prospective OI stored final timestamp mismatch: {path.name}")
        state.next_ms = last + BAR_MS
        state.last_name = path.name
        state.last_sha256 = manifest["oi_sha256"]
    return state


def _check_genesis(record: dict[str, Any], first: int, predecessor: ChainState | None,
                   name: str) -> None:
    previous = record.get("predecessor") or {}
    gap = record.get("gap") or {}
    if (predecessor is None or predecessor.next_ms is None
            or previous.get("chain_id") != chain_id(predecessor.number)
            or previous.get("last_chunk") != predecessor.last_name
            or previous.get("oi_sha256") != predecessor.last_sha256
            or previous.get("last_timestamp_ms") != predecessor.next_ms - BAR_MS
            or gap.get("first_missing_ms") != predecessor.next_ms
            or gap.get("last_missing_ms") != first - BAR_MS
            or gap.get("missing_points_per_symbol") != (first - predecessor.next_ms) // BAR_MS
            # Same bound as collect(): continuing would need missing + 1 + anchor points.
            or int(gap.get("missing_points_per_symbol", 0)) + 3 <= MAX_POINTS_PER_REQUEST
            or gap.get("backfilled") is not False
            or not str(gap.get("reason", "")).strip()):
        raise ValueError(f"prospective OI chain genesis does not record its gap exactly: {name}")


def _positive_decimal(value: Any, *, field: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid OI {field}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"invalid OI {field}")
    return str(number)


def collect(root: Path, client: PublicBybit, *, first_timestamp_ms: int | None = None,
            new_chain_reason: str | None = None) -> dict[str, Any]:
    symbols, source_hash, earliest = _source(root)
    numbers = chain_numbers(root)
    states: dict[int, ChainState] = {}
    for number in numbers:
        states[number] = _validate_chain(root, number, symbols, source_hash, earliest,
                                         states.get(number - 1))
    current = states[numbers[-1]] if numbers else ChainState(1)
    probe = observe_public_clock(client)
    if probe["status"] != "WALL_CLOCK_STABLE":
        raise ValueError("OI collection clock unstable during server-time request")
    server_ms = int(probe["server_ms"])
    # Even if the exchange labels a point by interval *start*, it is closed.
    last = ((server_ms - BAR_MS - SAFETY_LAG_MS) // BAR_MS) * BAR_MS
    chain_record: dict[str, Any] | None = None
    if new_chain_reason is not None:
        if not numbers or current.next_ms is None:
            raise ValueError("a new OI chain needs an existing, verified predecessor chain")
        if first_timestamp_ms is not None or not new_chain_reason.strip():
            raise ValueError("a new OI chain needs a reason and starts at the latest closed point")
        if (last - current.next_ms) // BAR_MS + 2 <= MAX_POINTS_PER_REQUEST:
            raise ValueError("the current OI chain can still be extended; a new chain is not justified")
        number = current.number + 1
        first = last - BAR_MS
        anchor = None
        chain_record = {"chain_id": chain_id(number),
                        "predecessor": {"chain_id": chain_id(current.number),
                                        "last_chunk": current.last_name,
                                        "last_timestamp_ms": current.next_ms - BAR_MS,
                                        "oi_sha256": current.last_sha256},
                        "gap": {"first_missing_ms": current.next_ms,
                                "last_missing_ms": first - BAR_MS,
                                "missing_points_per_symbol": (first - current.next_ms) // BAR_MS,
                                "recovery_bound_points": MAX_POINTS_PER_REQUEST,
                                "backfilled": False, "reason": new_chain_reason.strip()}}
    else:
        number = current.number
        next_ms, anchor = current.next_ms, current.anchor
        if first_timestamp_ms is not None:
            first = first_timestamp_ms
        else:
            first = next_ms if next_ms is not None else last - BAR_MS
        if (first % BAR_MS or first < earliest or (next_ms is not None and first != next_ms)
                or last < first):
            raise ValueError("OI must start at the next nonoverlapping post-004 timestamp")
        if number >= 2:
            chain_record = {"chain_id": chain_id(number)}
    expected = list(range(first, last + BAR_MS, BAR_MS))
    required_points = len(expected) + (anchor is not None)
    if required_points > MAX_POINTS_PER_REQUEST:
        raise ValueError("OI gap exceeds bounded single-page recovery")
    observations: dict[str, list[list[str | int]]] = {}
    latest_response_server_ms = server_ms
    for symbol in symbols:
        body = client.get("/v5/market/open-interest", {
            "category": "linear", "symbol": symbol, "intervalTime": "15min",
            "endTime": last, "limit": required_points,
        })
        result = body["result"]
        if result.get("category") != "linear" or result.get("symbol") != symbol:
            raise ValueError(f"OI response identity mismatch: {symbol}")
        response_server_ms = int(body["time"])
        if response_server_ms < server_ms or response_server_ms < last:
            raise ValueError(f"OI response time inconsistent: {symbol}")
        latest_response_server_ms = max(latest_response_server_ms, response_server_ms)
        rows: dict[int, list[str | int]] = {}
        observed_anchor = False
        for raw in result["list"]:
            timestamp = int(raw["timestamp"])
            if anchor is not None and timestamp == first - BAR_MS:
                prior = anchor[symbol]
                if (observed_anchor or Decimal(str(raw["openInterest"])) != Decimal(str(prior[1]))
                        or Decimal(str(raw["singleOpenInterest"])) != Decimal(str(prior[2]))):
                    raise ValueError(f"OI historical revision: {symbol} {timestamp}")
                observed_anchor = True
                continue
            if timestamp not in expected or timestamp in rows:
                raise ValueError(f"OI duplicate or unexpected timestamp: {symbol} {timestamp}")
            rows[timestamp] = [timestamp,
                _positive_decimal(raw["openInterest"], field="total"),
                _positive_decimal(raw["singleOpenInterest"], field="single-side"),
                response_server_ms]
        if set(rows) != set(expected) or (anchor is not None and not observed_anchor):
            raise ValueError(f"OI timestamp gap: {symbol} {len(rows)}/{len(expected)}")
        observations[symbol] = [rows[timestamp] for timestamp in expected]
    target = root / "data/public" / f"{chain_prefix(number)}{first}_{last}"
    target.mkdir(parents=True, exist_ok=False)
    _write_new(target / "oi.json", {"symbols": observations})
    oi_hash = hashlib.sha256((target / "oi.json").read_bytes()).hexdigest()
    collected_at = datetime.now(UTC)
    collected_ms = int(collected_at.timestamp() * 1000)
    manifest: dict[str, Any] = {
        "schema_version": 1 if number == 1 else 2,
        "dataset_id": f"{dataset_prefix(number)}{first}_{last}",
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
    if chain_record is not None:
        manifest["chain"] = chain_record
    _write_new(target / "manifest.json", manifest)
    if hashlib.sha256((target / "oi.json").read_bytes()).hexdigest() != oi_hash:
        raise AssertionError("OI read-back hash mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Trade v2 checkout that holds data/public and research/results")
    parser.add_argument("--new-chain-reason",
                        help="start the next OI chain, recording the unrecoverable gap and this reason")
    args = parser.parse_args()
    client = PublicBybit()
    try:
        print(json.dumps(collect(args.root.resolve(), client,
                                 new_chain_reason=args.new_chain_reason), indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
