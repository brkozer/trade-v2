import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.manifests import canonical
from tradev2.evidence.migrations import migrate

GENESIS = "0" * 64
REGISTRATION_KIND = "run_registered"
CHECKPOINT_KIND = "checkpoint"
REQUIRED_TRIGGERS = frozenset({"events_immutable_update", "events_immutable_delete",
                               "runs_immutable_update", "runs_immutable_delete"})
CHECKPOINT_TRIGGERS = frozenset({"checkpoints_immutable_update", "checkpoints_immutable_delete"})


def open_reader(path: Path) -> sqlite3.Connection:
    # mode=ro reads WAL. immutable=1 is expressly forbidden for safety observations.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        migrate(self.connection)

    def close(self) -> None:
        self.connection.close()

    def register(self, manifest: RunManifest) -> None:
        """Insert the manifest and bind its hash into the event chain in one transaction."""
        body = canonical(manifest.model_dump(mode="json"))
        existing = self.connection.execute(
            "SELECT manifest FROM runs WHERE run_id=?", (manifest.run_id,)).fetchone()
        if existing is not None:
            if existing[0] != body:
                raise ValueError("run_id already refers to a different manifest")
            return
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("INSERT INTO runs VALUES (?,?)", (manifest.run_id, body))
            self._append_locked(EvidenceEnvelope(
                event_id=f"{manifest.run_id}:registered", run_id=manifest.run_id,
                kind=REGISTRATION_KIND, recorded_ms=max(0, manifest.started_ms), source="journal",
                payload={"manifest_sha256": _sha256(body)}))

    def _append_locked(self, event: EvidenceEnvelope) -> bool:
        """Append inside an already open write transaction."""
        body = canonical(event.model_dump(mode="json"))
        existing = self.connection.execute(
            "SELECT body FROM events WHERE event_id=?", (event.event_id,)).fetchone()
        if existing is not None:
            if existing[0] != body:
                raise ValueError("event id collision with different evidence")
            return False
        last = self.connection.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = str(last[0]) if last else GENESIS
        event_hash = _sha256(previous + body)
        self.connection.execute(
            "INSERT INTO events(event_id,run_id,kind,recorded_ms,source_ms,body,"
            "previous_hash,event_hash) VALUES (?,?,?,?,?,?,?,?)",
            (event.event_id, event.run_id, event.kind, event.recorded_ms,
             event.source_ms, body, previous, event_hash))
        return True

    def append(self, event: EvidenceEnvelope) -> bool:
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            return self._append_locked(event)

    def checkpoint(self, checkpoint_id: str, run_id: str, recorded_ms: int,
                   state: dict[str, Any]) -> None:
        """Store a checkpoint and a chained event carrying its body hash atomically."""
        body = canonical(state)
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("INSERT INTO checkpoints VALUES (?,?,?,?)",
                                    (checkpoint_id, run_id, recorded_ms, body))
            self._append_locked(EvidenceEnvelope(
                event_id=f"checkpoint:{checkpoint_id}", run_id=run_id, kind=CHECKPOINT_KIND,
                recorded_ms=recorded_ms, source="journal",
                payload={"checkpoint_id": checkpoint_id, "body_sha256": _sha256(body)}))

    def verify(self) -> bool:
        return verify_connection(self.connection)

    def backup(self, destination: Path) -> str:
        if self.connection.in_transaction:
            raise ValueError("commit or rollback pending transaction before backup")
        if destination.exists():
            raise FileExistsError(destination)
        if not self.verify():
            raise ValueError("source journal integrity failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            self.connection.backup(target)
            # A backup is a self-contained file: no WAL sidecars are needed to read it.
            target.execute("PRAGMA journal_mode=DELETE")
            if not verify_connection(target):
                raise ValueError("backup integrity failed")
        finally:
            target.close()
        return hashlib.sha256(destination.read_bytes()).hexdigest()


def verify_connection(connection: sqlite3.Connection) -> bool:
    """Local tamper evidence; not an external notarization.

    Checks page integrity, immutability triggers, the hash chain, that indexed columns
    agree with each hashed body, that no tail of the chain was removed, and that every
    chained manifest and checkpoint binding still matches its row.
    """
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        return False
    tables = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    triggers = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")}
    required = REQUIRED_TRIGGERS | (CHECKPOINT_TRIGGERS if "checkpoints" in tables else frozenset())
    if not required <= triggers:
        return False
    previous = GENESIS
    last_sequence = 0
    for sequence, body, previous_hash, event_hash in connection.execute(
        "SELECT sequence,body,previous_hash,event_hash FROM events ORDER BY sequence"):
        if previous_hash != previous or _sha256(previous + body) != event_hash:
            return False
        previous = event_hash
        last_sequence = int(sequence)
    mismatched = connection.execute(
        "SELECT count(*) FROM events WHERE json_extract(body,'$.event_id') IS NOT event_id "
        "OR json_extract(body,'$.run_id') IS NOT run_id OR json_extract(body,'$.kind') IS NOT kind "
        "OR json_extract(body,'$.recorded_ms') IS NOT recorded_ms "
        "OR json_extract(body,'$.source_ms') IS NOT source_ms").fetchone()[0]
    if mismatched:
        return False
    anchor = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone() if (
        "sqlite_sequence" in tables) else None
    if (anchor[0] if anchor is not None else 0) != last_sequence:
        return False
    for run_id, digest in connection.execute(
            "SELECT run_id, json_extract(body,'$.payload.manifest_sha256') FROM events WHERE kind=?",
            (REGISTRATION_KIND,)):
        row = connection.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None or _sha256(str(row[0])) != digest:
            return False
    if "checkpoints" in tables:
        for run_id, checkpoint_id, digest in connection.execute(
                "SELECT run_id, json_extract(body,'$.payload.checkpoint_id'), "
                "json_extract(body,'$.payload.body_sha256') FROM events WHERE kind=?",
                (CHECKPOINT_KIND,)):
            row = connection.execute("SELECT run_id, body FROM checkpoints WHERE checkpoint_id=?",
                                     (checkpoint_id,)).fetchone()
            if row is None or row[0] != run_id or _sha256(str(row[1])) != digest:
                return False
    return True


def bound_checkpoint(connection: sqlite3.Connection,
                     run_id: str) -> tuple[str, dict[str, Any], int] | None:
    """Latest checkpoint by insertion order whose body hash is bound into the chain.

    Returns (checkpoint_id, state, sequence of its chained binding event), or None when
    the latest checkpoint is absent or unbound (for example a legacy journal).
    """
    latest = connection.execute(
        "SELECT checkpoint_id, body FROM checkpoints WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
        (run_id,)).fetchone()
    if latest is None:
        return None
    binding = connection.execute(
        "SELECT sequence, json_extract(body,'$.payload.body_sha256') FROM events "
        "WHERE event_id=? AND kind=? AND run_id=?",
        (f"checkpoint:{latest[0]}", CHECKPOINT_KIND, run_id)).fetchone()
    if binding is None or binding[1] != _sha256(str(latest[1])):
        return None
    return str(latest[0]), json.loads(latest[1]), int(binding[0])


def events_after(connection: sqlite3.Connection, sequence: int) -> list[dict[str, Any]]:
    return [json.loads(row[0]) for row in connection.execute(
        "SELECT body FROM events WHERE sequence>? ORDER BY sequence", (sequence,))]


def read_kinds(connection: sqlite3.Connection, kinds: tuple[str, ...],
               limit: int = 1000) -> dict[str, list[dict[str, Any]]]:
    """Newest-first events per kind from one already verified connection and snapshot."""
    bounded = max(1, min(limit, 10000))
    result: dict[str, list[dict[str, Any]]] = {}
    for kind in kinds:
        rows = connection.execute(
            "SELECT body FROM events WHERE kind=? ORDER BY sequence DESC LIMIT ?", (kind, bounded))
        result[kind] = [json.loads(row[0]) for row in rows]
    return result


def latest_activity_ms(path: Path) -> int:
    """Recorded time of the newest journaled event.

    File modification times are not recency: WAL commits leave the main file untouched
    until checkpoint, and an open file's timestamp may lag on Windows. The file time is
    only a fallback for an empty or unreadable journal.
    """
    try:
        connection = open_reader(path)
        try:
            row = connection.execute(
                "SELECT recorded_ms FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        row = None
    return int(row[0]) if row is not None else path.stat().st_mtime_ns // 1_000_000


def read_events(path: Path, kind: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    connection = open_reader(path)
    try:
        sql = "SELECT body FROM events"
        params: list[str | int] = []
        if kind is not None:
            sql += " WHERE kind=?"
            params.append(kind)
        sql += " ORDER BY sequence DESC LIMIT ?"
        params.append(max(1, min(limit, 10000)))
        return [json.loads(row[0]) for row in connection.execute(sql, params)]
    finally:
        connection.close()


def restore_backup(source: Path, destination: Path, expected_sha256: str) -> None:
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("backup checksum mismatch")
    if destination.exists():
        raise FileExistsError(destination)
    reader = open_reader(source)
    try:
        if not verify_connection(reader):
            raise ValueError("backup evidence chain invalid")
        destination.parent.mkdir(parents=True, exist_ok=True)
        writer = sqlite3.connect(destination)
        try:
            reader.backup(writer)
        finally:
            writer.close()
    finally:
        reader.close()
