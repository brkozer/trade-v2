import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ops.collect_forward_bars import collect as collect_bars
from ops.collect_forward_oi import collect as collect_oi
from tradev2.domain.market import Candle
from tradev2.research.datasets import BAR_MS
from tradev2.research.prospective_chain import (
    AVAILABILITY_BUFFER_MS,
    REQUIRED_FORWARD_DAYS,
    load_chain,
    summarize_prospective_evidence,
)
from tradev2.venues.bybit_linear.public import PublicBybit

FIRST = int(datetime(2026, 9, 23, 10, tzinfo=UTC).timestamp() * 1000)
SYMBOLS = [f"S{index}USDT" for index in range(20)]
SECOND = 1_000


def _root(tmp_path: Path, *, source_manifest: bool = True) -> Path:
    public = tmp_path / "data/public"
    public.mkdir(parents=True)
    if source_manifest:
        source = public / "alpha_search_004"
        source.mkdir()
        (source / "manifest.json").write_text(json.dumps({"symbols": SYMBOLS}), encoding="utf-8")
    result = tmp_path / "research/results"
    result.mkdir(parents=True)
    (result / "ALPHA_SEARCH_004.json").write_text(json.dumps({
        "finished_at": "2026-09-23T09:45:16+00:00"}), encoding="utf-8")
    return tmp_path


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_hash(root: Path) -> str | None:
    manifest = root / "data/public/alpha_search_004/manifest.json"
    return hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def write_bars_chunk(root: Path, first: int, last: int, *, collected_ms: int,
                     symbols: list[str] = SYMBOLS, store_safe: bool = True,
                     source_hash: str | None = None) -> Path:
    assert collected_ms % SECOND == 0, "whole seconds keep the ISO round trip exact"
    target = root / "data/public" / f"prospective_bars_{first}_{last}"
    target.mkdir(parents=True)
    rows = {symbol: [[opened, "100", "101", "99", "100.5", "10", collected_ms - SECOND]
                     for opened in range(first, last + BAR_MS, BAR_MS)] for symbol in symbols}
    _write(target / "bars.json", {"symbols": rows})
    manifest: dict[str, Any] = {
        "schema_version": 1, "dataset_id": f"BYBIT_PUBLIC_FORWARD_{first}_{last}",
        "evidence_role": "PROSPECTIVE_POST004_UNSCORED",
        "source_universe_manifest_sha256": source_hash or _source_hash(root) or "unknown",
        "first_open_ms": first, "last_open_ms": last, "interval_ms": BAR_MS,
        "symbols": list(symbols), "bars_per_symbol": (last - first) // BAR_MS + 1,
        "collected_at": _iso(collected_ms),
        "bars_sha256": hashlib.sha256((target / "bars.json").read_bytes()).hexdigest()}
    if store_safe:
        manifest["safe_available_ms"] = collected_ms + AVAILABILITY_BUFFER_MS
    _write(target / "manifest.json", manifest)
    return target


def write_oi_chunk(root: Path, first: int, last: int, *, collected_ms: int,
                   response_ms: int | None = None, store_safe: bool = True) -> Path:
    assert collected_ms % SECOND == 0
    response = response_ms if response_ms is not None else collected_ms - SECOND
    target = root / "data/public" / f"prospective_oi_{first}_{last}"
    target.mkdir(parents=True)
    rows = {symbol: [[stamp, "20.5", "10.25", response]
                     for stamp in range(first, last + BAR_MS, BAR_MS)] for symbol in SYMBOLS}
    _write(target / "oi.json", {"symbols": rows})
    manifest: dict[str, Any] = {
        "schema_version": 1, "dataset_id": f"BYBIT_PUBLIC_OI_FORWARD_{first}_{last}",
        "evidence_role": "PROSPECTIVE_POST004_UNSCORED",
        "source_universe_manifest_sha256": _source_hash(root) or "unknown",
        "first_timestamp_ms": first, "last_timestamp_ms": last, "interval_ms": BAR_MS,
        "symbols": SYMBOLS, "points_per_symbol": (last - first) // BAR_MS + 1,
        "latest_response_server_ms": response, "collected_at": _iso(collected_ms),
        "oi_sha256": hashlib.sha256((target / "oi.json").read_bytes()).hexdigest()}
    if store_safe:
        manifest["safe_available_ms"] = max(collected_ms, response) + AVAILABILITY_BUFFER_MS
    _write(target / "manifest.json", manifest)
    return target


def _bars_client(server_ms: int, first: int, last: int) -> MagicMock:
    client = MagicMock(spec=PublicBybit)
    client.server_time.return_value = server_ms

    def candles(symbol: str, *, limit: int, end_ms: int) -> list[Candle]:
        return [Candle(symbol=symbol, start_ms=opened, interval_ms=BAR_MS,
                       open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
                       close=Decimal("100.5"), volume=Decimal("10"), confirmed=True,
                       ingested_ms=server_ms) for opened in range(last, first - BAR_MS, -BAR_MS)]

    client.candles.side_effect = candles
    return client


def _oi_client(server_ms: int) -> MagicMock:
    client = MagicMock(spec=PublicBybit)
    client.server_time.return_value = server_ms

    def get(path: str, params: dict[str, str | int]) -> dict[str, Any]:
        end = int(params["endTime"])
        rows = [{"timestamp": str(end - index * BAR_MS), "openInterest": "20.5",
                 "singleOpenInterest": "10.25"} for index in range(int(params["limit"]))]
        return {"time": server_ms + 10, "result": {"category": "linear",
                                                   "symbol": params["symbol"], "list": rows}}

    client.get.side_effect = get
    return client


def test_absent_data_stays_unknown_not_zero(tmp_path: Path) -> None:
    summary = summarize_prospective_evidence(tmp_path, now_ms=FIRST)
    assert summary["status"] == "NO_PROSPECTIVE_DATA"
    assert summary["candles"] is None and summary["open_interest"] is None
    assert summary["gate"]["covered_days"] is None and summary["gate"]["remaining_days"] is None
    assert summary["gate"]["forward_days_satisfied"] is None
    assert summary["collector"]["state"] == "UNKNOWN"
    assert summary["scored"] is False
    root = _root(tmp_path / "empty")
    assert summarize_prospective_evidence(root, now_ms=FIRST)["status"] == "NO_PROSPECTIVE_DATA"


def test_real_collector_chunks_are_accepted(tmp_path: Path) -> None:
    root = _root(tmp_path)
    collect_bars(root, _bars_client(FIRST + BAR_MS + 120_000, FIRST, FIRST), first_open_ms=FIRST)
    collect_oi(root, _oi_client(FIRST + 2 * BAR_MS + 120_000))
    now = time.time_ns() // 1_000_000
    summary = summarize_prospective_evidence(root, now_ms=now)
    assert summary["status"] == "WAITING_FOR_DATA"
    assert summary["candles"]["chunks"] == 1 and summary["candles"]["points_per_symbol"] == 1
    assert summary["open_interest"]["chunks"] == 1 and summary["open_interest"]["points_per_symbol"] == 2
    assert summary["candles"]["hash_verified"] and summary["open_interest"]["contiguous"]
    assert summary["alignment"]["matched_feature_timestamps"] == 1
    # The chunk was collected now, so no execution bar after its availability exists yet.
    assert summary["alignment"]["executable_feature_timestamps"] == 0
    assert summary["collector"]["state"] == "RECENT"
    assert summary["source_universe_verified"] is True
    assert summary["gate"]["required_forward_days"] == REQUIRED_FORWARD_DAYS
    assert summary["gate"]["forward_days_satisfied"] is False


def test_synthetic_chain_coverage_alignment_and_staleness(tmp_path: Path) -> None:
    root = _root(tmp_path)
    write_bars_chunk(root, FIRST, FIRST + 3 * BAR_MS, collected_ms=FIRST + 4 * BAR_MS + 10 * SECOND,
                     store_safe=False)
    write_bars_chunk(root, FIRST + 4 * BAR_MS, FIRST + 5 * BAR_MS,
                     collected_ms=FIRST + 6 * BAR_MS + 10 * SECOND)
    write_oi_chunk(root, FIRST + BAR_MS, FIRST + 2 * BAR_MS,
                   collected_ms=FIRST + 3 * BAR_MS + 20 * SECOND,
                   response_ms=FIRST + 3 * BAR_MS + 15 * SECOND)
    now = FIRST + 6 * BAR_MS + 30 * SECOND
    summary = summarize_prospective_evidence(root, now_ms=now)
    assert summary["status"] == "WAITING_FOR_DATA"
    candles = summary["candles"]
    assert candles["chunks"] == 2 and candles["points_per_symbol"] == 6
    assert candles["coverage_hours"] == 1.5
    assert candles["first_utc"] == "2026-09-23T10:00:00+00:00"
    assert candles["last_close_utc"] == "2026-09-23T11:30:00+00:00"
    assert summary["open_interest"]["points_per_symbol"] == 2
    assert summary["alignment"] == {"matched_feature_timestamps": 2,
                                    "executable_feature_timestamps": 2,
                                    "rule": summary["alignment"]["rule"]}
    assert summary["gate"]["covered_days"] == 0.06
    assert summary["gate"]["remaining_days"] == 27.94
    assert summary["gate"]["forward_days_satisfied"] is False
    assert summary["collector"]["age_ms"] == 20 * SECOND
    assert summary["collector"]["state"] == "RECENT"
    stale = summarize_prospective_evidence(root, now_ms=now + 3_600_000)
    assert stale["collector"]["state"] == "STALE"
    reached = summarize_prospective_evidence(root, now_ms=now, required_forward_days=0)
    assert reached["status"] == "FORWARD_WINDOW_REACHED_UNSCORED"
    assert reached["gate"]["forward_days_satisfied"] is True and reached["scored"] is False


def test_unavailable_execution_bar_is_not_counted(tmp_path: Path) -> None:
    root = _root(tmp_path)
    # Candle chunk collected long after its close: the first eligible open lies beyond the chain.
    write_bars_chunk(root, FIRST, FIRST + BAR_MS, collected_ms=FIRST + 9 * BAR_MS)
    write_oi_chunk(root, FIRST, FIRST + BAR_MS, collected_ms=FIRST + 3 * BAR_MS)
    summary = summarize_prospective_evidence(root, now_ms=FIRST + 10 * BAR_MS)
    assert summary["alignment"]["matched_feature_timestamps"] == 2
    assert summary["alignment"]["executable_feature_timestamps"] == 0


def test_tampered_payload_fails_closed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    target = write_bars_chunk(root, FIRST, FIRST, collected_ms=FIRST + 2 * BAR_MS)
    payload = json.loads((target / "bars.json").read_text(encoding="utf-8"))
    payload["symbols"][SYMBOLS[0]][0][4] = "250"
    _write(target / "bars.json", payload)
    summary = summarize_prospective_evidence(root, now_ms=FIRST + 3 * BAR_MS)
    assert summary["status"] == "CHAIN_INTEGRITY_FAILED"
    assert "hash drift" in summary["error"]
    assert summary["candles"] is None and summary["gate"]["covered_days"] is None
    assert summary["collector"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("defect", ["gap", "overlap", "universe", "safe_mismatch",
                                    "oi_without_safe", "payload_timestamps", "name"])
def test_chain_defects_fail_closed(tmp_path: Path, defect: str) -> None:
    root = _root(tmp_path)
    write_bars_chunk(root, FIRST, FIRST, collected_ms=FIRST + 2 * BAR_MS)
    if defect == "gap":
        write_bars_chunk(root, FIRST + 2 * BAR_MS, FIRST + 2 * BAR_MS, collected_ms=FIRST + 4 * BAR_MS)
        expected = "gap or overlap"
    elif defect == "overlap":
        write_bars_chunk(root, FIRST, FIRST + BAR_MS, collected_ms=FIRST + 4 * BAR_MS)
        (root / "data/public" / f"prospective_bars_{FIRST}_{FIRST + BAR_MS}").rename(
            root / "data/public" / f"prospective_bars_{FIRST}_{FIRST + BAR_MS}x")
        expected = "manifest inconsistent"
    elif defect == "universe":
        write_bars_chunk(root, FIRST + BAR_MS, FIRST + BAR_MS, collected_ms=FIRST + 4 * BAR_MS,
                         symbols=SYMBOLS[:19] + ["OTHERUSDT"])
        expected = "universe changed"
    elif defect == "safe_mismatch":
        target = root / "data/public" / f"prospective_bars_{FIRST}_{FIRST}"
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        manifest["safe_available_ms"] -= 1
        _write(target / "manifest.json", manifest)
        expected = "manifest inconsistent"
    elif defect == "oi_without_safe":
        write_oi_chunk(root, FIRST, FIRST, collected_ms=FIRST + 2 * BAR_MS, store_safe=False)
        expected = "manifest inconsistent"
    elif defect == "payload_timestamps":
        target = write_oi_chunk(root, FIRST, FIRST + BAR_MS, collected_ms=FIRST + 3 * BAR_MS)
        payload = json.loads((target / "oi.json").read_text(encoding="utf-8"))
        payload["symbols"][SYMBOLS[3]][1][0] = FIRST + 2 * BAR_MS
        _write(target / "oi.json", payload)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        manifest["oi_sha256"] = hashlib.sha256((target / "oi.json").read_bytes()).hexdigest()
        _write(target / "manifest.json", manifest)
        expected = "coverage mismatch"
    else:
        (root / "data/public" / f"prospective_bars_{FIRST}_{FIRST}").rename(
            root / "data/public" / f"prospective_bars_{FIRST}_{FIRST + BAR_MS}")
        expected = "manifest inconsistent"
    summary = summarize_prospective_evidence(root, now_ms=FIRST + 5 * BAR_MS)
    assert summary["status"] == "CHAIN_INTEGRITY_FAILED"
    assert expected in summary["error"]
    with pytest.raises(ValueError):
        load_chain(root, kind="bars")
        load_chain(root, kind="oi")


def test_source_universe_mismatch_is_reported_not_assumed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    write_bars_chunk(root, FIRST, FIRST, collected_ms=FIRST + 2 * BAR_MS, source_hash="0" * 64)
    assert summarize_prospective_evidence(root, now_ms=FIRST + 3 * BAR_MS)[
        "source_universe_verified"] is False
    unknown_root = _root(tmp_path / "nosource", source_manifest=False)
    write_bars_chunk(unknown_root, FIRST, FIRST, collected_ms=FIRST + 2 * BAR_MS, source_hash="1" * 64)
    assert summarize_prospective_evidence(unknown_root, now_ms=FIRST + 3 * BAR_MS)[
        "source_universe_verified"] is None
