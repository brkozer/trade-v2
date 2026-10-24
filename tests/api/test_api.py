import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from tradev2.api.server import create_app
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal

SEALED_SEARCH_COUNT = 8


def register(journal: Journal) -> None:
    journal.register(RunManifest(run_id="run1", git_sha="test", dirty=False, mode="paper",
                                 started_ms=0, config={}, config_hash="test", candidate_id="reference",
                                 candidate_version="1", parameter_hash="test", venue="bybit",
                                 universe=("BTCUSDT",), universe_hash="test", fee_provenance="test",
                                 dataset_identity=None, python_version="3.11", package_versions={},
                                 initial_equity_source=None))


def test_unknown_does_not_become_zero(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/workstation")
    assert response.status_code == 200
    body = response.json()
    assert body["account"] is None
    assert body["runtime"]["status"] == "NOT_RUNNING"
    assert body["system"]["public_market"] == "UNKNOWN"
    assert body["runtime"]["freshness"] == "UNKNOWN"
    assert body["runtime"]["live"] == "LIVE_DISABLED"
    assert body["prospective"]["status"] == "NO_PROSPECTIVE_DATA"
    assert body["prospective"]["candles"] is None
    assert body["prospective"]["gate"]["covered_days"] is None
    assert body["searches"] == [] and body["candidates"] == []
    assert client.post("/api/v1/orders", json={}).status_code == 405
    assert client.get("/api/v1/workstation?mode=live").status_code == 422
    assert client.get("/api/v1/workstation?run_id=../secret").status_code == 422
    assert client.get("/api/v1/workstation?search_id=UNKNOWN").status_code == 404


def test_stale_runtime_never_advertises_freshness(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "runtime/paper/run1/journal.sqlite")
    register(journal)
    journal.append(EvidenceEnvelope(event_id="e1", run_id="run1", kind="runtime",
                                   recorded_ms=time.time_ns() // 1_000_000 - 60_000,
                                   source="simulation", payload={"status": "SAFE"}))
    journal.close()
    body = TestClient(create_app(tmp_path)).get("/api/v1/workstation").json()
    assert body["runtime"]["freshness"] == "STALE"
    assert body["evidence"]["integrity"] == "VERIFIED"


def test_corrupt_evidence_fails_closed(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "runtime/paper/run1/journal.sqlite")
    register(journal)
    journal.append(EvidenceEnvelope(event_id="e1", run_id="run1", kind="runtime",
                                   recorded_ms=1, source="simulation", payload={"status": "SAFE"}))
    # Simulate an externally damaged file, deliberately bypassing the write guard in this fixture.
    journal.connection.execute("DROP TRIGGER events_immutable_update")
    journal.connection.execute("UPDATE events SET event_hash='broken'")
    journal.connection.commit()
    journal.close()
    body = TestClient(create_app(tmp_path)).get("/api/v1/workstation").json()
    assert body["runtime"]["status"] == "UNKNOWN"
    assert body["evidence"]["integrity"] == "FAILED"


def test_read_routes(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/health").json() == {
        "status": "AVAILABLE", "live": "LIVE_DISABLED"}
    for route in ("runtime", "account", "positions", "orders", "fills", "trades", "symbols",
                  "opportunities", "decisions", "rejections", "experiments", "searches",
                  "candidates", "performance", "evidence-health", "system-health", "run-manifests",
                  "system-info", "reconciliation", "recorder-status", "accounting",
                  "search-runs", "research-results", "prospective-evidence"):
        assert client.get("/api/v1/" + route).status_code == 200
    assert client.get("/api/v1/prospective-evidence").json()["data"]["status"] == "NO_PROSPECTIVE_DATA"
    assert client.get("/api/v1/candidates/missing").status_code == 404
    assert client.get("/api/v1/not-a-route").status_code == 404


def test_completed_research_and_paired_stress_are_read_only() -> None:
    root = Path(__file__).resolve().parents[2]
    client = TestClient(create_app(root))
    body = client.get("/api/v1/workstation?search_id=TRADEV2_FINAL_ALPHA_003").json()
    assert body["campaign"]["search_id"] == "TRADEV2_FINAL_ALPHA_003"
    assert len(body["campaign"]["families"]) == 14
    assert body["campaign"]["search_budget"]["configurations"] == 28
    assert body["campaign"]["search_budget"]["selection_evaluations"] == 112
    assert body["campaign"]["search_budget"]["total_replays"] == 336
    assert sum(row["status"] == "REJECTED" for row in body["campaign"]["families"]) == 14
    assert body["campaign"]["promoted_candidates"] == []
    assert len(body["searches"]) >= SEALED_SEARCH_COUNT
    assert len(body["candidates"]) == 14
    assert len(body["experiments"]) == 112
    assert all(row["ci"] is None and row["status"] == "DESCRIPTIVE_ONLY"
               for row in body["experiments"])
    assert len(client.get("/api/v1/candidates?search_id=TRADEV2_FINAL_ALPHA_003").json()["data"]) == 14
    assert len(client.get("/api/v1/experiments?search_id=TRADEV2_FINAL_ALPHA_003").json()["data"]) == 112
    detail = client.get("/api/v1/candidates/trend_persistence?search_id=TRADEV2_FINAL_ALPHA_003")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "REJECTED"
    assert client.post("/api/v1/experiments", json={}).status_code == 405


def test_latest_sealed_search_is_active_and_earlier_searches_remain_inspectable() -> None:
    root = Path(__file__).resolve().parents[2]
    client = TestClient(create_app(root))
    latest = client.get("/api/v1/workstation").json()
    searches = latest["searches"]
    assert [row["search_id"] for row in searches][:SEALED_SEARCH_COUNT] == [
        "TRADEV2_INITIAL_ALPHA_001", "TRADEV2_FINAL_ALPHA_003", "TRADEV2_ALPHA_SEARCH_004",
        "TRADEV2_DISCOVERY_005", "TRADEV2_DISCOVERY_006", "TRADEV2_DISCOVERY_007",
        "TRADEV2_DISCOVERY_008", "TRADEV2_DISCOVERY_009"]
    assert all(row["promoted"] == 0 and row["complete"] is True for row in searches)
    assert latest["campaign"]["search_id"] == searches[-1]["search_id"]
    assert latest["campaign"]["evidence_role"] == "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
    assert latest["campaign"]["frozen_candidate"] is None
    assert len(latest["candidates"]) == latest["campaign"]["trial_count"]
    assert len(latest["experiments"]) == latest["campaign"]["evaluation_count"]
    assert all(row["status"] == "DISCOVERY_GATES_FAILED" for row in latest["candidates"])
    body = client.get("/api/v1/workstation?search_id=TRADEV2_ALPHA_SEARCH_004").json()
    assert body["campaign"]["search_id"] == "TRADEV2_ALPHA_SEARCH_004"
    assert body["campaign"]["trial_count"] == 12
    assert body["campaign"]["evaluation_count"] == 108
    assert len(body["campaign"]["families"]) == 24
    assert body["campaign"]["promoted_candidates"] == []
    assert len(body["candidates"]) == 24
    assert len(client.get("/api/v1/experiments?search_id=TRADEV2_ALPHA_SEARCH_004").json()["data"]) == 108
    assert client.get("/api/v1/workstation?search_id=TRADEV2_FINAL_ALPHA_003").json()[
        "campaign"]["search_id"] == "TRADEV2_FINAL_ALPHA_003"


def test_discovery_candidate_detail_exposes_frozen_configurations() -> None:
    root = Path(__file__).resolve().parents[2]
    client = TestClient(create_app(root))
    detail = client.get("/api/v1/candidates/cross_sectional_idiosyncratic_max_effect"
                        "?search_id=TRADEV2_DISCOVERY_009")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["search_id"] == "TRADEV2_DISCOVERY_009"
    assert [row["label"] for row in data["configurations"]] == ["lookback=1344", "lookback=2688"]
    carry = client.get("/api/v1/candidates/funding_settlement_carry?search_id=TRADEV2_DISCOVERY_005")
    assert carry.status_code == 200
    assert carry.json()["data"]["forward_trades"] == 72
    assert carry.json()["data"]["status"] == "REJECTED_DISCOVERY_ONLY"
    assert client.get("/api/v1/candidates/funding_settlement_carry"
                      "?search_id=TRADEV2_DISCOVERY_009").status_code == 404


def test_unsealed_or_tampered_research_is_reported_not_served(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    results = tmp_path / "research/results"
    manifests = tmp_path / "research/manifests"
    results.mkdir(parents=True)
    manifests.mkdir(parents=True)
    shutil.copy(repo / "research/results/DISCOVERY_SEARCH_008.json", results / "DISCOVERY_SEARCH_008.json")
    client = TestClient(create_app(tmp_path))
    body = client.get("/api/v1/workstation").json()
    assert body["searches"] == [] and body["campaign"] is None
    evidence = body["evidence"]
    assert evidence["research_errors"] == ["CAMPAIGN_INTEGRITY_FAILED:DISCOVERY_SEARCH_008.json"]
    assert evidence["research_integrity"] == "FAILED"
    # A research seal failure is not a journal failure; no journal exists here.
    assert evidence["integrity"] == "UNKNOWN" and evidence["errors"] == []
    envelope = client.get("/api/v1/candidates").json()
    assert envelope["integrity"]["research"] == "FAILED" and envelope["data"] == []
    assert client.get("/api/v1/workstation?search_id=TRADEV2_DISCOVERY_008").status_code == 404
    shutil.copy(repo / "research/manifests/alpha_search_completion_008.json",
                manifests / "alpha_search_completion_008.json")
    body = client.get("/api/v1/workstation").json()
    assert [row["search_id"] for row in body["searches"]] == ["TRADEV2_DISCOVERY_008"]
    assert body["evidence"]["research_errors"] == []
    assert body["evidence"]["research_integrity"] == "VERIFIED"
    tampered = (results / "DISCOVERY_SEARCH_008.json").read_bytes().replace(b"-441.", b"+441.", 1)
    (results / "DISCOVERY_SEARCH_008.json").write_bytes(tampered)
    body = client.get("/api/v1/workstation").json()
    assert body["searches"] == []
    assert "CAMPAIGN_INTEGRITY_FAILED:DISCOVERY_SEARCH_008.json" in body["evidence"]["research_errors"]


def _manifest(run_id: str, *, mode: str = "paper", config: dict | None = None) -> RunManifest:
    return RunManifest(run_id=run_id, git_sha="test", dirty=False, mode=mode, started_ms=0,
                       config=config or {}, config_hash="test", candidate_id="reference",
                       candidate_version="1", parameter_hash="test", venue="bybit",
                       universe=("BTCUSDT",), universe_hash="test", fee_provenance="test",
                       dataset_identity=None, python_version="3.11", package_versions={},
                       initial_equity_source=None)


def test_unknown_run_id_is_not_found_rather_than_not_running(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "runtime/paper/run1/journal.sqlite")
    register(journal)
    journal.close()
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/workstation?run_id=run1").status_code == 200
    assert client.get("/api/v1/workstation?run_id=missing").status_code == 404
    assert client.get("/api/v1/account?run_id=missing").status_code == 404


def test_partially_unreadable_journal_is_not_served(tmp_path: Path, monkeypatch) -> None:
    import tradev2.api.server as server

    journal = Journal(tmp_path / "runtime/paper/run1/journal.sqlite")
    register(journal)
    journal.append(EvidenceEnvelope(event_id="e1", run_id="run1", kind="runtime",
                                   recorded_ms=time.time_ns() // 1_000_000, source="simulation",
                                   payload={"status": "RUNNING", "candidate_id": "reference"}))
    journal.append(EvidenceEnvelope(event_id="e2", run_id="run1", kind="account",
                                   recorded_ms=1, source="simulation", payload={"equity": "10000"}))
    journal.close()

    def broken(connection, kinds, limit=1000):
        raise server.sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server, "read_kinds", broken)
    body = TestClient(create_app(tmp_path)).get("/api/v1/workstation").json()
    assert body["evidence"]["errors"] == ["JOURNAL_UNAVAILABLE"]
    assert body["runtime"]["status"] == "UNKNOWN" and body["runtime"]["candidate_id"] is None
    assert body["account"] is None and body["manifests"] == []
    assert all(events == [] for events in body["events"].values())


def test_wal_activity_selects_the_run_still_writing(tmp_path: Path) -> None:
    import os

    older = Journal(tmp_path / "runtime/paper/older/journal.sqlite")
    older.register(_manifest("older"))
    newer = Journal(tmp_path / "runtime/paper/newer/journal.sqlite")
    newer.register(_manifest("newer"))
    newer.close()
    older.append(EvidenceEnvelope(event_id="late", run_id="older", kind="runtime",
                                 recorded_ms=time.time_ns() // 1_000_000, source="simulation",
                                 payload={"status": "RUNNING"}))
    assert (tmp_path / "runtime/paper/older/journal.sqlite-wal").is_file()
    # The open run's main file has not been checkpointed since creation.
    os.utime(tmp_path / "runtime/paper/older/journal.sqlite", ns=(1, 1))
    try:
        body = TestClient(create_app(tmp_path)).get("/api/v1/workstation").json()
    finally:
        older.close()
    assert body["runtime"]["run_id"] == "older"


def test_recorder_status_separates_integrity_from_acceptance(tmp_path: Path) -> None:
    from tradev2.api.server import _recording_status

    assert _recording_status(tmp_path)["status"] == "UNKNOWN"
    path = tmp_path / "runtime/recorder/open-run/journal.sqlite"
    journal = Journal(path)
    journal.register(_manifest("open-run", mode="shadow", config={"symbols": ["BTCUSDT"]}))
    journal.close()
    status = _recording_status(tmp_path)
    assert status["status"] == "NOT_COMPLETED" and status["run_id"] == "open-run"
    assert status["messages"] is None
    broken = Journal(path)
    broken.append(EvidenceEnvelope(event_id="done", run_id="open-run", kind="recorder_complete",
                                   recorded_ms=1, source="fixture",
                                   payload={"messages": 0, "books": 0, "trades": 0}))
    status = _recording_status(tmp_path)
    assert status["status"] == "UNACCEPTED" and "provenance mismatch" in status["reason"]
    broken.connection.execute("DROP TRIGGER events_immutable_update")
    broken.connection.execute("UPDATE events SET event_hash='broken'")
    broken.connection.commit()
    broken.close()
    assert _recording_status(tmp_path)["status"] == "INTEGRITY_FAILED"
