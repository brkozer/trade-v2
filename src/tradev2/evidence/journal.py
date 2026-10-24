import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.manifests import canonical
from tradev2.evidence.migrations import migrate


def open_reader(path: Path) -> sqlite3.Connection:
    # mode=ro reads WAL. immutable=1 is expressly forbidden for safety observations.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


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
        body = canonical(manifest.model_dump(mode="json"))
        existing = self.connection.execute(
            "SELECT manifest FROM runs WHERE run_id=?", (manifest.run_id,)).fetchone()
        if existing is not None:
            if existing[0] != body:
                raise ValueError("run_id already refers to a different manifest")
            return
        with self.connection:
            self.connection.execute("INSERT INTO runs VALUES (?,?)", (manifest.run_id, body))

    def append(self, event: EvidenceEnvelope) -> bool:
        body = canonical(event.model_dump(mode="json"))
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute(
                "SELECT body FROM events WHERE event_id=?", (event.event_id,)).fetchone()
            if existing is not None:
                if existing[0] != body:
                    raise ValueError("event id collision with different evidence")
                return False
            last = self.connection.execute(
                "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = str(last[0]) if last else "0" * 64
            event_hash = hashlib.sha256((previous + body).encode()).hexdigest()
            self.connection.execute(
                "INSERT INTO events(event_id,run_id,kind,recorded_ms,source_ms,body,"
                "previous_hash,event_hash) VALUES (?,?,?,?,?,?,?,?)",
                (event.event_id, event.run_id, event.kind, event.recorded_ms,
                 event.source_ms, body, previous, event_hash))
        return True

    def checkpoint(self, checkpoint_id: str, run_id: str, recorded_ms: int,
                   state: dict[str, Any]) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO checkpoints VALUES (?,?,?,?)",
                                    (checkpoint_id, run_id, recorded_ms, canonical(state)))

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
            if not verify_connection(target):
                raise ValueError("backup integrity failed")
        finally:
            target.close()
        return hashlib.sha256(destination.read_bytes()).hexdigest()


def verify_connection(connection: sqlite3.Connection) -> bool:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        return False
    previous = "0" * 64
    for body, previous_hash, event_hash in connection.execute(
        "SELECT body,previous_hash,event_hash FROM events ORDER BY sequence"):
        if previous_hash != previous:
            return False
        if hashlib.sha256((previous + body).encode()).hexdigest() != event_hash:
            return False
        previous = event_hash
    return True


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


def latest_activity_ns(path: Path) -> int:
    """WAL commits change the -wal sidecar, not the main file, until checkpoint/close."""
    stamps = [path.stat().st_mtime_ns]
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.is_file():
            stamps.append(sidecar.stat().st_mtime_ns)
    return max(stamps)


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
