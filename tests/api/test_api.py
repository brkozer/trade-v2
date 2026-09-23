import time
from pathlib import Path

from fastapi.testclient import TestClient

from tradev2.api.server import create_app
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal


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
                  "search-runs", "research-results"):
        assert client.get("/api/v1/" + route).status_code == 200
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
    assert len(body["searches"]) == 3
    assert len(body["experiments"]) == 112
    assert all(row["ci"] is None and row["status"] == "DESCRIPTIVE_ONLY"
               for row in body["experiments"])
    assert len(client.get("/api/v1/candidates?search_id=TRADEV2_FINAL_ALPHA_003").json()["data"]) == 14
    assert len(client.get("/api/v1/experiments?search_id=TRADEV2_FINAL_ALPHA_003").json()["data"]) == 112
    detail = client.get("/api/v1/candidates/trend_persistence?search_id=TRADEV2_FINAL_ALPHA_003")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "REJECTED"
    assert client.post("/api/v1/experiments", json={}).status_code == 405


def test_search004_is_sealed_and_does_not_replace_003() -> None:
    root = Path(__file__).resolve().parents[2]
    client = TestClient(create_app(root))
    latest = client.get("/api/v1/workstation").json()
    assert latest["campaign"]["search_id"] == "TRADEV2_ALPHA_SEARCH_004"
    assert latest["campaign"]["trial_count"] == 12
    assert latest["campaign"]["evaluation_count"] == 108
    assert len(latest["campaign"]["families"]) == 24
    assert latest["campaign"]["promoted_candidates"] == []
    assert len(client.get("/api/v1/experiments").json()["data"]) == 108
    assert client.get("/api/v1/workstation?search_id=TRADEV2_FINAL_ALPHA_003").json()[
        "campaign"]["search_id"] == "TRADEV2_FINAL_ALPHA_003"
