import sqlite3

SCHEMA_VERSION = 2
MIGRATIONS = {
    1: """
    CREATE TABLE runs(run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
    CREATE TABLE events(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE NOT NULL,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        kind TEXT NOT NULL,
        recorded_ms INTEGER NOT NULL,
        source_ms INTEGER,
        body TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL
    );
    CREATE INDEX events_kind_time ON events(kind, recorded_ms);
    CREATE TRIGGER events_immutable_update BEFORE UPDATE ON events
      BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END;
    CREATE TRIGGER events_immutable_delete BEFORE DELETE ON events
      BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END;
    CREATE TRIGGER runs_immutable_update BEFORE UPDATE ON runs
      BEGIN SELECT RAISE(ABORT, 'immutable manifest'); END;
    CREATE TRIGGER runs_immutable_delete BEFORE DELETE ON runs
      BEGIN SELECT RAISE(ABORT, 'immutable manifest'); END;
    """,
    2: """
    CREATE TABLE checkpoints(
      checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
      recorded_ms INTEGER NOT NULL, body TEXT NOT NULL
    );
    CREATE TRIGGER checkpoints_immutable_update BEFORE UPDATE ON checkpoints
      BEGIN SELECT RAISE(ABORT, 'immutable checkpoint'); END;
    CREATE TRIGGER checkpoints_immutable_delete BEFORE DELETE ON checkpoints
      BEGIN SELECT RAISE(ABORT, 'immutable checkpoint'); END;
    """,
}


def migrate(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise ValueError("journal schema is newer than this software")
    for target in range(version + 1, SCHEMA_VERSION + 1):
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + MIGRATIONS[target]
                + f"\nPRAGMA user_version={target};\nCOMMIT;")
        except sqlite3.DatabaseError:
            connection.rollback()
            raise

