"""Read-only integrity and coverage summary of the prospective candle and OI chains.

The collectors under ops/ write immutable chunks. This module only re-verifies
them and states how far the fixed forward-day requirement remains. It never
collects, scores or repairs anything, and absent data stays unknown, not zero.
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

    @property
    def points(self) -> int:
        return (self.last_ms - self.first_ms) // BAR_MS + 1


def _iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def load_chunk(path: Path, *, kind: Kind) -> Chunk:
    """Re-verify one immutable chunk exactly as its collector promised to write it."""
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if kind == "bars":
        first, last = int(manifest["first_open_ms"]), int(manifest["last_open_ms"])
        name, dataset = f"prospective_bars_{first}_{last}", f"BYBIT_PUBLIC_FORWARD_{first}_{last}"
        payload_name, hash_key = "bars.json", "bars_sha256"
    else:
        first, last = int(manifest["first_timestamp_ms"]), int(manifest["last_timestamp_ms"])
        name, dataset = f"prospective_oi_{first}_{last}", f"BYBIT_PUBLIC_OI_FORWARD_{first}_{last}"
        payload_name, hash_key = "oi.json", "oi_sha256"
    collected = _iso_ms(str(manifest["collected_at"]))
    if kind == "bars":
        expected_safe = collected + AVAILABILITY_BUFFER_MS
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
                 str(manifest["source_universe_manifest_sha256"]))


def load_chain(root: Path, *, kind: Kind) -> list[Chunk]:
    """Load and verify a contiguous, single-universe chain; raise on any defect."""
    public = root / "data/public"
    prefix = "prospective_bars_" if kind == "bars" else "prospective_oi_"
    if not public.is_dir():
        return []
    chunks = sorted((load_chunk(path, kind=kind) for path in public.glob(f"{prefix}*")
                     if path.is_dir()), key=lambda chunk: chunk.first_ms)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        if current.first_ms != previous.last_ms + BAR_MS:
            raise ValueError(f"prospective {kind} chain gap or overlap before {current.name}")
        if current.symbols != previous.symbols or current.source_hash != previous.source_hash:
            raise ValueError(f"prospective {kind} chain universe changed at {current.name}")
    return chunks


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


def _alignment(bars: list[Chunk], oi: list[Chunk]) -> dict[str, Any] | None:
    if not bars or not oi:
        return None
    candle_safe, oi_safe = _availability(bars), _availability(oi)
    matched = sorted(set(candle_safe) & set(oi_safe))
    last_open = bars[-1].last_ms
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


def summarize_prospective_evidence(root: Path, *, now_ms: int,
                                   required_forward_days: int = REQUIRED_FORWARD_DAYS,
                                   stale_after_ms: int = COLLECTOR_STALE_AFTER_MS) -> dict[str, Any]:
    """Describe the prospective chains and the unmet forward-day gate without scoring."""
    base: dict[str, Any] = {"schema_version": 1, "generated_ms": now_ms,
                            "evidence_role": EVIDENCE_ROLE, "scored": False,
                            "authority": "NONE; no search, candidate or promotion is implied"}
    try:
        bars = load_chain(root, kind="bars")
        oi = load_chain(root, kind="oi")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {**base, "status": "CHAIN_INTEGRITY_FAILED", "error": f"{type(exc).__name__}: {exc}",
                "candles": None, "open_interest": None, "alignment": None,
                "gate": {"required_forward_days": required_forward_days, "covered_days": None,
                         "remaining_days": None, "forward_days_satisfied": None},
                "collector": {"last_collected_at": None, "age_ms": None, "state": "UNKNOWN",
                              "stale_after_ms": stale_after_ms},
                "source_universe_verified": None}
    if not bars and not oi:
        return {**base, "status": "NO_PROSPECTIVE_DATA", "error": None,
                "candles": None, "open_interest": None, "alignment": None,
                "gate": {"required_forward_days": required_forward_days, "covered_days": None,
                         "remaining_days": None, "forward_days_satisfied": None},
                "collector": {"last_collected_at": None, "age_ms": None, "state": "UNKNOWN",
                              "stale_after_ms": stale_after_ms},
                "source_universe_verified": None}
    covered_days = (round(sum(chunk.points for chunk in bars) * BAR_MS / DAY_MS, 2)
                    if bars else None)
    satisfied = covered_days is not None and covered_days >= required_forward_days
    last_collected = max(chunk.collected_ms for chunk in (*bars, *oi))
    age = now_ms - last_collected
    return {**base,
            "status": "FORWARD_WINDOW_REACHED_UNSCORED" if satisfied else "WAITING_FOR_DATA",
            "error": None,
            "candles": _section(bars), "open_interest": _section(oi),
            "alignment": _alignment(bars, oi),
            "gate": {"required_forward_days": required_forward_days,
                     "covered_days": covered_days,
                     "remaining_days": (None if covered_days is None
                                        else round(max(0.0, required_forward_days - covered_days), 2)),
                     "forward_days_satisfied": satisfied,
                     "note": ("Forward days alone authorize nothing: a new preregistration, "
                              "independently dated training and chronological validation, and "
                              "completed execution bars for every scored outcome are also required.")},
            "collector": {"last_collected_at": _utc(last_collected), "age_ms": age,
                          "state": "RECENT" if 0 <= age <= stale_after_ms else "STALE",
                          "stale_after_ms": stale_after_ms},
            "source_universe_verified": _source_universe_verified(root, [*bars, *oi])}
