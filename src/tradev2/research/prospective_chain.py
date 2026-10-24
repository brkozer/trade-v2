"""Read-only integrity and coverage summary of the prospective candle and OI chains.

The collectors under ops/ write immutable chunks. This module independently
re-verifies them and states how far the fixed forward-day requirement remains. It
never collects, scores or repairs anything, and absent data stays unknown, not zero.

The forward-day gate counts only the newest uninterrupted run of feature timestamps
that have both a candle and an OI point, each first collected within one hour of
its interval close. Backfilled bars and recorded OI chain gaps therefore cannot
inflate coverage.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from tradev2.research.datasets import BAR_MS
from tradev2.research.prospective_alignment import first_eligible_open_ms

AVAILABILITY_BUFFER_MS = 5_000
DAY_MS = 86_400_000
REQUIRED_FORWARD_DAYS = 28
COLLECTOR_STALE_AFTER_MS = 3_600_000
CONTEMPORANEOUS_LAG_MS = 3_600_000
OI_RECOVERY_BOUND_POINTS = 200
EVIDENCE_ROLE = "PROSPECTIVE_POST004_UNSCORED"
Kind = Literal["bars", "oi"]
SOURCE_UNIVERSE_MANIFEST = Path("data/public/alpha_search_004/manifest.json")


@dataclass(frozen=True)
class Chunk:
    name: str
    first_ms: int
    last_ms: int
    safe_available_ms: int
    collected_ms: int
    symbols: tuple[str, ...]
    source_hash: str
    chain: dict[str, Any] | None = None

    @property
    def points(self) -> int:
        return (self.last_ms - self.first_ms) // BAR_MS + 1


def _iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def oi_chain_id(number: int) -> str:
    return f"OI_CHAIN_{number:03d}"


def _oi_prefix(number: int) -> str:
    return "prospective_oi_" if number == 1 else f"prospective_oi{number}_"


def load_chunk(path: Path, *, kind: Kind, chain: int = 1) -> Chunk:
    """Re-verify one immutable chunk exactly as its collector promised to write it."""
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    record: dict[str, Any] | None = None
    if kind == "bars":
        first, last = int(manifest["first_open_ms"]), int(manifest["last_open_ms"])
        name, dataset = f"prospective_bars_{first}_{last}", f"BYBIT_PUBLIC_FORWARD_{first}_{last}"
        payload_name, hash_key = "bars.json", "bars_sha256"
    else:
        first, last = int(manifest["first_timestamp_ms"]), int(manifest["last_timestamp_ms"])
        name = f"{_oi_prefix(chain)}{first}_{last}"
        dataset = (f"BYBIT_PUBLIC_OI_FORWARD_{first}_{last}" if chain == 1
                   else f"BYBIT_PUBLIC_OI_FORWARD{chain}_{first}_{last}")
        payload_name, hash_key = "oi.json", "oi_sha256"
        if chain >= 2:
            record = manifest.get("chain")
            if not isinstance(record, dict) or record.get("chain_id") != oi_chain_id(chain):
                raise ValueError(f"prospective oi chain identity mismatch: {path.name}")
    collected = _iso_ms(str(manifest["collected_at"]))
    if kind == "bars" and int(manifest.get("schema_version", 1)) < 2:
        expected_safe = collected + AVAILABILITY_BUFFER_MS  # legacy local-receipt rule
    else:
        expected_safe = (max(collected, int(manifest["latest_response_server_ms"]))
                         + AVAILABILITY_BUFFER_MS)
    stored_safe = manifest.get("safe_available_ms")
    if (path.name != name or manifest.get("dataset_id") != dataset
            or manifest.get("interval_ms") != BAR_MS
            or manifest.get("evidence_role") != EVIDENCE_ROLE
            or first % BAR_MS or last < first or (last - first) % BAR_MS
            or (stored_safe is None and kind == "oi")
            or (stored_safe is not None and int(stored_safe) != expected_safe)
            or expected_safe < last + BAR_MS):
        raise ValueError(f"prospective {kind} chunk manifest inconsistent: {path.name}")
    payload = (path / payload_name).read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest[hash_key]:
        raise ValueError(f"prospective {kind} payload hash drift: {path.name}")
    symbols = tuple(str(symbol) for symbol in manifest["symbols"])
    if len(set(symbols)) != len(symbols) or not symbols:
        raise ValueError(f"prospective {kind} universe invalid: {path.name}")
    rows = json.loads(payload.decode("utf-8"))["symbols"]
    expected = list(range(first, last + BAR_MS, BAR_MS))
    if set(rows) != set(symbols) or any(
            [int(row[0]) for row in rows[symbol]] != expected for symbol in symbols):
        raise ValueError(f"prospective {kind} payload coverage mismatch: {path.name}")
    return Chunk(path.name, first, last, expected_safe, collected, symbols,
                 str(manifest["source_universe_manifest_sha256"]), record)


def _contiguous(chunks: list[Chunk], label: str) -> list[Chunk]:
    for previous, current in zip(chunks, chunks[1:], strict=False):
        if current.first_ms != previous.last_ms + BAR_MS:
            raise ValueError(f"prospective {label} chain gap or overlap before {current.name}")
        if current.symbols != previous.symbols or current.source_hash != previous.source_hash:
            raise ValueError(f"prospective {label} chain universe changed at {current.name}")
    return chunks


def load_chain(root: Path, *, kind: Kind, chain: int = 1) -> list[Chunk]:
    """Load and verify one contiguous, single-universe chain; raise on any defect."""
    public = root / "data/public"
    if not public.is_dir():
        return []
    prefix = "prospective_bars_" if kind == "bars" else _oi_prefix(chain)
    chunks = sorted((load_chunk(path, kind=kind, chain=chain) for path in public.glob(f"{prefix}*")
                     if path.is_dir()), key=lambda chunk: chunk.first_ms)
    return _contiguous(chunks, kind if kind == "bars" else oi_chain_id(chain))


def oi_chain_numbers(root: Path) -> list[int]:
    public = root / "data/public"
    numbers: set[int] = set()
    if public.is_dir():
        for path in public.glob("prospective_oi*_*"):
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


def load_oi_chains(root: Path) -> list[tuple[int, list[Chunk]]]:
    """Every OI chain, each verified, with each successor's recorded gap checked."""
    chains: list[tuple[int, list[Chunk]]] = []
    for number in oi_chain_numbers(root):
        chunks = load_chain(root, kind="oi", chain=number)
        if number >= 2:
            previous = chains[-1][1]
            record = chunks[0].chain or {}
            predecessor, gap = record.get("predecessor") or {}, record.get("gap") or {}
            if (not previous or predecessor.get("chain_id") != oi_chain_id(number - 1)
                    or predecessor.get("last_chunk") != previous[-1].name
                    or predecessor.get("last_timestamp_ms") != previous[-1].last_ms
                    or gap.get("first_missing_ms") != previous[-1].last_ms + BAR_MS
                    or gap.get("last_missing_ms") != chunks[0].first_ms - BAR_MS
                    or gap.get("missing_points_per_symbol")
                    != (chunks[0].first_ms - previous[-1].last_ms) // BAR_MS - 1
                    or int(gap.get("missing_points_per_symbol", 0)) + 3 <= OI_RECOVERY_BOUND_POINTS
                    or gap.get("backfilled") is not False
                    or not str(gap.get("reason", "")).strip()
                    or any("predecessor" in (chunk.chain or {}) for chunk in chunks[1:])
                    or chunks[0].symbols != previous[-1].symbols):
                raise ValueError(f"{oi_chain_id(number)} genesis does not record its gap exactly")
        chains.append((number, chunks))
    return chains


def _section(chunks: list[Chunk]) -> dict[str, Any] | None:
    if not chunks:
        return None
    points = sum(chunk.points for chunk in chunks)
    return {"chunks": len(chunks), "symbols": len(chunks[0].symbols),
            "points_per_symbol": points,
            "first_ms": chunks[0].first_ms, "last_ms": chunks[-1].last_ms,
            "first_utc": _utc(chunks[0].first_ms),
            "last_close_utc": _utc(chunks[-1].last_ms + BAR_MS),
            "last_collected_at": _utc(chunks[-1].collected_ms),
            "coverage_hours": round(points * BAR_MS / 3_600_000, 2),
            "contiguous": True, "hash_verified": True}


def _availability(chunks: list[Chunk]) -> dict[int, int]:
    return {timestamp: chunk.safe_available_ms for chunk in chunks
            for timestamp in range(chunk.first_ms, chunk.last_ms + BAR_MS, BAR_MS)}


def _contemporaneous(safe: dict[int, int]) -> set[int]:
    return {timestamp for timestamp, available in safe.items()
            if available - (timestamp + BAR_MS) <= CONTEMPORANEOUS_LAG_MS}


def _latest_run(timestamps: set[int]) -> tuple[int, int, int] | None:
    """(first, last, length) of the newest run of consecutive 15-minute timestamps."""
    if not timestamps:
        return None
    ordered = sorted(timestamps)
    end = start = ordered[-1]
    while start - BAR_MS in timestamps:
        start -= BAR_MS
    return start, end, (end - start) // BAR_MS + 1


def _alignment(candle_safe: dict[int, int], oi_safe: dict[int, int],
               last_open: int | None) -> dict[str, Any] | None:
    if not candle_safe or not oi_safe or last_open is None:
        return None
    matched = sorted(set(candle_safe) & set(oi_safe))
    executable = sum(
        1 for timestamp in matched
        if first_eligible_open_ms(candle_open_ms=timestamp,
                                  candle_safe_available_ms=candle_safe[timestamp],
                                  oi_timestamp_ms=timestamp,
                                  oi_safe_available_ms=oi_safe[timestamp]) <= last_open)
    return {"matched_feature_timestamps": len(matched),
            "executable_feature_timestamps": executable,
            "rule": "first bar open strictly after candle close and both safe_available_ms bounds"}


def _source_universe_verified(root: Path, chunks: list[Chunk]) -> bool | None:
    manifest = root / SOURCE_UNIVERSE_MANIFEST
    if not chunks or not manifest.is_file():
        return None
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return all(chunk.source_hash == digest for chunk in chunks)


def _unknown(base: dict[str, Any], status: str, error: str | None, required: int,
             stale_after_ms: int) -> dict[str, Any]:
    return {**base, "status": status, "error": error,
            "candles": None, "open_interest": None, "oi_chains": [], "alignment": None,
            "gate": {"required_forward_days": required, "covered_days": None,
                     "remaining_days": None, "forward_days_satisfied": None},
            "collector": {"last_collected_at": None, "age_ms": None, "state": "UNKNOWN",
                          "stale_after_ms": stale_after_ms},
            "source_universe_verified": None}


def summarize_prospective_evidence(root: Path, *, now_ms: int,
                                   required_forward_days: int = REQUIRED_FORWARD_DAYS,
                                   stale_after_ms: int = COLLECTOR_STALE_AFTER_MS) -> dict[str, Any]:
    """Describe the prospective chains and the unmet forward-day gate without scoring."""
    base: dict[str, Any] = {"schema_version": 2, "generated_ms": now_ms,
                            "evidence_role": EVIDENCE_ROLE, "scored": False,
                            "authority": "NONE; no search, candidate or promotion is implied"}
    try:
        bars = load_chain(root, kind="bars")
        oi_chains = load_oi_chains(root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _unknown(base, "CHAIN_INTEGRITY_FAILED", f"{type(exc).__name__}: {exc}",
                        required_forward_days, stale_after_ms)
    oi_all = [chunk for _, chunks in oi_chains for chunk in chunks]
    if not bars and not oi_all:
        return _unknown(base, "NO_PROSPECTIVE_DATA", None, required_forward_days, stale_after_ms)
    candle_safe = _availability(bars)
    oi_safe = _availability(oi_all)
    contemporaneous_bars = _contemporaneous(candle_safe)
    joint = contemporaneous_bars & _contemporaneous(oi_safe)
    run = _latest_run(joint)
    covered_days = round(run[2] * BAR_MS / DAY_MS, 2) if run is not None else 0.0
    satisfied = covered_days >= required_forward_days
    last_collected = max(chunk.collected_ms for chunk in (*bars, *oi_all))
    age = now_ms - last_collected
    candles = _section(bars)
    if candles is not None:
        candles["contemporaneous_points_per_symbol"] = len(contemporaneous_bars)
        candles["backfilled_points_per_symbol"] = len(candle_safe) - len(contemporaneous_bars)
    current_number, current_chunks = oi_chains[-1] if oi_chains else (None, [])
    open_interest = _section(current_chunks)
    if open_interest is not None:
        open_interest["chain_id"] = oi_chain_id(current_number) if current_number else None
    chains = [{"chain_id": oi_chain_id(number), **(_section(chunks) or {}),
               "gap_before": (chunks[0].chain or {}).get("gap") if number >= 2 else None}
              for number, chunks in oi_chains]
    return {**base,
            "status": "FORWARD_WINDOW_REACHED_UNSCORED" if satisfied else "WAITING_FOR_DATA",
            "error": None,
            "candles": candles, "open_interest": open_interest, "oi_chains": chains,
            "alignment": _alignment(candle_safe, oi_safe, bars[-1].last_ms if bars else None),
            "gate": {"required_forward_days": required_forward_days,
                     "covered_days": covered_days,
                     "remaining_days": round(max(0.0, required_forward_days - covered_days), 2),
                     "forward_days_satisfied": satisfied,
                     "basis": ("newest uninterrupted run of joint candle and OI timestamps, each "
                               "first collected within one hour of its interval close"),
                     "run_first_utc": _utc(run[0]) if run is not None else None,
                     "run_last_close_utc": _utc(run[1] + BAR_MS) if run is not None else None,
                     "note": ("Forward days alone authorize nothing: a new preregistration, "
                              "independently dated training and chronological validation, and "
                              "completed execution bars for every scored outcome are also required.")},
            "collector": {"last_collected_at": _utc(last_collected), "age_ms": age,
                          "state": "RECENT" if 0 <= age <= stale_after_ms else "STALE",
                          "stale_after_ms": stale_after_ms},
            "source_universe_verified": _source_universe_verified(root, [*bars, *oi_all])}
