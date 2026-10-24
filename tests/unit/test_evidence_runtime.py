import json
import sqlite3

import pytest

from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal, open_reader, read_events, restore_backup
from tradev2.evidence.migrations import MIGRATIONS, migrate
from tradev2.runtime.authority import AccountAuthority
from tradev2.runtime.health import evaluate_health
from tradev2.runtime.startup import REQUIRED, startup_gate


def manifest():
    return RunManifest(run_id="test", git_sha="a"*40, dirty=False, mode="paper", started_ms=1,
        config={}, config_hash="b"*64, candidate_id="reference", candidate_version="1",
        parameter_hash="c"*64, venue="bybit_linear", universe=("BTCUSDT",),
        universe_hash="d"*64, fee_provenance="fixture", dataset_identity="fixture",
        python_version="3.11", package_versions={}, initial_equity_source="simulation")


def event(event_id="event1", **kwargs):
    return EvidenceEnvelope(event_id=event_id, run_id="test", kind="runtime", recorded_ms=10,
                            source="fixture", payload=kwargs)


def test_journal_idempotence_immutability_and_backup(tmp_path):
    journal = Journal(tmp_path / "test.sqlite")
    journal.register(manifest())
    journal.register(manifest())
    assert journal.append(event())
    assert not journal.append(event())
    with pytest.raises(ValueError, match="collision"):
        journal.append(event(changed=True))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        journal.connection.execute("DELETE FROM events")
    with pytest.raises(ValueError, match="pending transaction"):
        journal.backup(tmp_path / "blocked.sqlite")
    journal.connection.rollback()
    assert journal.verify()
    backup = tmp_path / "backup.sqlite"
    checksum = journal.backup(backup)
    journal.close()
    destination = tmp_path / "restored.sqlite"
    restore_backup(backup, destination, checksum)
    assert len(read_events(destination, "runtime")) == 1
    assert [row["kind"] for row in read_events(destination)] == ["runtime", "run_registered"]
    # The backup is self-contained: no WAL sidecars are needed beside it.
    assert not (tmp_path / "backup.sqlite-wal").exists()
    with pytest.raises(FileExistsError):
        restore_backup(backup, destination, checksum)


def test_migration_upgrade_and_future_schema_refusal(tmp_path):
    connection = sqlite3.connect(tmp_path / "old.sqlite")
    connection.executescript(MIGRATIONS[1] + "PRAGMA user_version=1;")
    migrate(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    connection.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="newer"):
        migrate(connection)
    connection.close()


def test_wal_reader_cannot_miss_pending_halt(tmp_path):
    path = tmp_path / "wal.sqlite"
    journal = Journal(path)
    journal.register(manifest())
    journal.append(event(pending_halt=False))
    journal.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # This reproduces the exact unsafe reader pattern from legacy history.
    unsafe = sqlite3.connect(path.as_uri() + "?immutable=1", uri=True)
    journal.append(event("event2", pending_halt=True))
    historical = json.loads(unsafe.execute(
        "SELECT body FROM events ORDER BY sequence DESC LIMIT 1").fetchone()[0])
    assert historical["payload"]["pending_halt"] is False
    reader = open_reader(path)
    current = json.loads(reader.execute(
        "SELECT body FROM events ORDER BY sequence DESC LIMIT 1").fetchone()[0])
    assert current["payload"]["pending_halt"] is True
    assert evaluate_health(now_ms=20, engine_alive=True, heartbeat_ms=10, source_ms=10,
        readable=True, previous_halt=current["payload"]["pending_halt"]).safety == "ENTRY_BLOCKED"
    unsafe.close()
    reader.close()
    journal.close()


@pytest.mark.parametrize("alive,heartbeat,source,readable", [
    (False, 99999, 99999, True), (None, 99999, 99999, True),
    (True, 1, 99999, True), (True, 99999, 1, True),
    (True, 99999, None, True), (True, 99999, 99999, False),
    (True, 99999, 100001, True),
])
def test_historical_evidence_is_never_current_safe(alive, heartbeat, source, readable):
    health = evaluate_health(now_ms=100000, engine_alive=alive, heartbeat_ms=heartbeat,
                             source_ms=source, readable=readable, previous_halt=False)
    assert health.safety == "ENTRY_BLOCKED"


def test_unreadable_evidence_preserves_halt():
    health = evaluate_health(now_ms=100, engine_alive=None, heartbeat_ms=None,
                             source_ms=None, readable=False, previous_halt=True)
    assert health.pending_halt


def test_account_authority_unique_across_config_paths(tmp_path):
    first = AccountAuthority(tmp_path, "bybit_testnet", "canonical-account")
    second = AccountAuthority(tmp_path, "bybit_testnet", "canonical-account")
    first.acquire()
    try:
        with pytest.raises(PermissionError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


@pytest.mark.parametrize("omitted", sorted(REQUIRED))
def test_every_startup_guard_is_required(omitted):
    checks = dict.fromkeys(REQUIRED, True)
    checks[omitted] = None
    assert startup_gate(checks).status == "ENTRY_BLOCKED"
