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
    assert body["runtime"]["freshness"] == "UNKNOWN"
    assert body["runtime"]["live"] == "LIVE_DISABLED"
    assert client.post("/api/v1/orders", json={}).status_code == 405
    assert client.get("/api/v1/workstation?mode=live").status_code == 422
    assert client.get("/api/v1/workstation?run_id=../secret").status_code == 422


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
    for route in ("runtime", "account", "positions", "orders", "trades", "symbols",
                  "opportunities", "decisions", "rejections", "experiments", "searches",
                  "candidates", "performance", "evidence-health", "system-health", "run-manifests"):
        assert client.get("/api/v1/" + route).status_code == 200
    assert client.get("/api/v1/not-a-route").status_code == 404
