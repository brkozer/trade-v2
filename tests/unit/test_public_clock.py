from pathlib import Path

import httpx
import pytest

from tradev2 import cli
from tradev2.evidence.journal import Journal, read_events
from tradev2.marketdata import clock


def test_public_clock_bracket_preserves_raw_times(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def server_time(self) -> int:
            return 2_100

    wall = iter((1_000_000_000, 1_200_000_000))
    mono = iter((5_000_000_000, 5_200_000_000))
    monkeypatch.setattr(clock.time, "time_ns", lambda: next(wall))
    monkeypatch.setattr(clock.time, "monotonic_ns", lambda: next(mono))
    probe = clock.observe_public_clock(Client())
    assert probe == {
        "local_before_ms": 1_000, "server_ms": 2_100, "local_after_ms": 1_200,
        "wall_elapsed_ms": 200, "monotonic_elapsed_ms": 200,
        "server_minus_local_after_ms": 900, "server_minus_local_before_ms": 1_100,
        "status": "WALL_CLOCK_STABLE",
    }


def test_public_clock_bracket_marks_wall_jump(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def server_time(self) -> int:
            return 2_100

    wall = iter((1_000_000_000, 800_000_000))
    mono = iter((5_000_000_000, 5_200_000_000))
    monkeypatch.setattr(clock.time, "time_ns", lambda: next(wall))
    monkeypatch.setattr(clock.time, "monotonic_ns", lambda: next(mono))
    assert clock.observe_public_clock(Client())["status"] == "WALL_CLOCK_UNSTABLE"


def test_recorder_clock_probe_failure_is_separate_from_feed_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 2

        def server_time(self) -> int:
            raise httpx.ConnectError("offline")

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "PublicBybit", FailingClient)
    path = tmp_path / "journal.sqlite"
    journal = Journal(path)
    manifest = cli._public_recorder_manifest(Path(__file__).resolve().parents[2], ("BTCUSDT",))
    journal.register(manifest)
    cli._record_public_clock_probe(journal, manifest.run_id, "start")
    journal.close()
    events = read_events(path, "clock_probe_failure")
    assert len(events) == 1
    assert events[0]["payload"] == {"phase": "start", "reason": "ConnectError"}
    assert read_events(path, "source_failure") == []


def test_recorder_clock_probe_requires_known_phase(tmp_path) -> None:
    journal = Journal(tmp_path / "journal.sqlite")
    with pytest.raises(ValueError, match="phase"):
        cli._record_public_clock_probe(journal, "run", "middle")
    journal.close()
