import io
import json
import tarfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import portalocker
import pytest

from ops.collection_round import run_round
from ops.pull_prospective import merge_chunks, tree_digest, unpack
from tradev2.domain.market import Candle
from tradev2.research.datasets import BAR_MS
from tradev2.research.prospective_chain import summarize_prospective_evidence
from tradev2.venues.bybit_linear.public import PublicBybit

FIRST = int(datetime(2026, 9, 23, 10, tzinfo=UTC).timestamp() * 1000)
SYMBOLS = [f"S{index}USDT" for index in range(20)]


def _root(tmp_path: Path) -> Path:
    source = tmp_path / "data/public/alpha_search_004"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(json.dumps({"symbols": SYMBOLS}), encoding="utf-8")
    result = tmp_path / "research/results"
    result.mkdir(parents=True)
    (result / "ALPHA_SEARCH_004.json").write_text(json.dumps({
        "finished_at": "2026-09-23T09:45:16+00:00"}), encoding="utf-8")
    return tmp_path


def _client(server_ms: int, *, oi_error: bool = False) -> MagicMock:
    client = MagicMock(spec=PublicBybit)
    client.server_time.return_value = server_ms

    def candles(symbol: str, *, limit: int, end_ms: int) -> list[Candle]:
        top = (end_ms // BAR_MS) * BAR_MS
        return [Candle(symbol=symbol, start_ms=top - index * BAR_MS, interval_ms=BAR_MS,
                       open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
                       close=Decimal("100"), volume=Decimal("5"), confirmed=True,
                       ingested_ms=server_ms) for index in range(limit)]

    def get(path: str, params: dict[str, Any]) -> dict[str, Any]:
        if oi_error:
            raise httpx.ConnectError("unreachable")
        end = int(params["endTime"])
        rows = [{"timestamp": str(end - index * BAR_MS), "openInterest": "20.5",
                 "singleOpenInterest": "10.25"} for index in range(int(params["limit"]))]
        return {"time": server_ms + 10, "result": {"category": "linear",
                                                   "symbol": params["symbol"], "list": rows}}

    client.candles.side_effect = candles
    client.get.side_effect = get
    return client


def _status(root: Path) -> dict[str, Any]:
    return json.loads((root / "runtime/collector/status.json").read_text(encoding="utf-8"))


def test_rounds_collect_then_report_not_due_without_counting_failures(tmp_path: Path) -> None:
    root = _root(tmp_path)
    server = FIRST + 2 * BAR_MS + 130_000
    first = run_round(root, client_factory=lambda: _client(server), min_free_gb=0, commit="abc")
    assert first["outcome"] == "OK"
    assert {name: item["result"] for name, item in first["sources"].items()} == {
        "candles": "COLLECTED", "open_interest": "COLLECTED"}
    second = run_round(root, client_factory=lambda: _client(server), min_free_gb=0, commit="abc")
    assert second["outcome"] == "OK"
    assert {item["result"] for item in second["sources"].values()} == {"NOT_DUE"}
    status = _status(root)
    assert (status["rounds"], status["rounds_failed"], status["consecutive_failures"]) == (2, 0, 0)
    assert status["code_commit"] == "abc"
    lines = (root / "runtime/collector/rounds.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    summary = summarize_prospective_evidence(root, now_ms=server)
    assert summary["status"] == "WAITING_FOR_DATA" and summary["error"] is None


def test_failures_are_counted_and_an_unrecoverable_oi_gap_asks_for_a_successor(tmp_path: Path) -> None:
    root = _root(tmp_path)
    run_round(root, client_factory=lambda: _client(FIRST + 2 * BAR_MS + 130_000), min_free_gb=0)
    failed = run_round(root, client_factory=lambda: _client(FIRST + 4 * BAR_MS + 130_000,
                                                            oi_error=True), min_free_gb=0)
    assert failed["outcome"] == "FAILED"
    assert failed["sources"]["candles"]["result"] == "COLLECTED"
    assert failed["sources"]["open_interest"]["result"] == "FAILED"
    assert _status(root)["consecutive_failures"] == 1
    late = run_round(root, client_factory=lambda: _client(FIRST + 400 * BAR_MS + 130_000),
                     min_free_gb=0)
    assert late["outcome"] == "FAILED"
    assert "--new-chain-reason" in late["sources"]["open_interest"]["action_required"]
    assert _status(root)["consecutive_failures"] == 2
    recovered = run_round(root, client_factory=lambda: _client(FIRST + 400 * BAR_MS + 130_000),
                          min_free_gb=0)
    assert recovered["outcome"] == "FAILED"  # the gap never heals by itself
    assert not list((root / "data/public").glob("prospective_oi2_*"))


def test_stop_request_lock_and_disk_floor_write_nothing(tmp_path: Path) -> None:
    root = _root(tmp_path)
    state = root / "runtime/collector"
    state.mkdir(parents=True)
    (state / "stop.request").write_text("stop\n", encoding="utf-8")
    stopped = run_round(root, client_factory=lambda: _client(FIRST + 2 * BAR_MS + 130_000),
                        min_free_gb=0)
    assert stopped["outcome"] == "STOPPED_BY_REQUEST"
    assert _status(root)["rounds"] == 0
    (state / "stop.request").unlink()
    with portalocker.Lock(str(state / "round.lock"), mode="a", timeout=0, fail_when_locked=True):
        skipped = run_round(root, client_factory=lambda: _client(FIRST + 2 * BAR_MS + 130_000),
                            min_free_gb=0)
    assert skipped["outcome"] == "SKIPPED_ROUND_IN_PROGRESS"
    floor = run_round(root, client_factory=lambda: _client(FIRST + 2 * BAR_MS + 130_000),
                      min_free_gb=10 ** 9)
    assert floor["outcome"] == "FAILED" and "free disk" in floor["error"]
    assert not list((root / "data/public").glob("prospective_*"))


def test_pull_adds_only_absent_chunks_and_refuses_divergent_ones(tmp_path: Path) -> None:
    remote = _root(tmp_path / "remote")
    run_round(remote, client_factory=lambda: _client(FIRST + 2 * BAR_MS + 130_000), min_free_gb=0)
    local = _root(tmp_path / "local")
    first = merge_chunks(remote / "data/public", local / "data/public")
    assert sorted(first["added"]) == sorted(
        path.name for path in (remote / "data/public").glob("prospective_*"))
    run_round(remote, client_factory=lambda: _client(FIRST + 4 * BAR_MS + 130_000), min_free_gb=0)
    second = merge_chunks(remote / "data/public", local / "data/public")
    assert len(second["added"]) == 2 and second["identical"] == 2
    assert summarize_prospective_evidence(local, now_ms=FIRST + 5 * BAR_MS)["error"] is None
    changed = next((remote / "data/public").glob("prospective_bars_*"))
    before = {path.name: tree_digest(path) for path in (local / "data/public").glob("prospective_*")}
    (changed / "bars.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="differ"):
        merge_chunks(remote / "data/public", local / "data/public")
    assert {path.name: tree_digest(path)
            for path in (local / "data/public").glob("prospective_*")} == before


@pytest.mark.parametrize("name", ["../escape/manifest.json", "other_dir/file.json"])
def test_pull_rejects_unexpected_or_escaping_archive_members(tmp_path: Path, name: str) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as bundle:
        payload = b"{}"
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))
    with pytest.raises((ValueError, tarfile.TarError)):
        unpack(buffer.getvalue(), tmp_path / "staging")
    assert not (tmp_path / "escape").exists()
