"""Read-back acceptance of a closed prospective public recording."""

import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from tradev2.evidence.journal import open_reader, verify_connection


def inspect_recording(path: Path, run_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = open_reader(path)
    try:
        if not verify_connection(connection):
            raise ValueError("recording journal integrity failed")
        manifest = connection.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if manifest is None:
            raise ValueError("recorder run manifest missing")
        counts: dict[str, int] = defaultdict(int)
        last_seq: dict[str, int] = {}
        first_ms: int | None = None
        last_ms: int | None = None
        for row in connection.execute("SELECT body FROM events WHERE run_id=? AND kind='microstructure' ORDER BY sequence", (run_id,)):
            event = json.loads(row[0])
            payload = event["payload"]
            if payload.get("schema_version") != 1 or payload.get("ingested_ms") != event["recorded_ms"]:
                raise ValueError("recording schema or ingestion timestamp mismatch")
            source_ms = payload.get("exchange_event_ms")
            if source_ms != event["source_ms"]:
                raise ValueError("exchange timestamp not preserved")
            symbol = payload.get("symbol")
            if not isinstance(symbol, str):
                raise ValueError("recording symbol missing")
            first_ms = min(first_ms, event["recorded_ms"]) if first_ms is not None else event["recorded_ms"]
            last_ms = max(last_ms, event["recorded_ms"]) if last_ms is not None else event["recorded_ms"]
            kind = payload.get("kind")
            if kind == "orderbook":
                if payload.get("update_id") is None or payload.get("seq") is None or payload.get("cts") is None:
                    raise ValueError("book update/sequence/matching time missing")
                sequence = int(payload["seq"])
                if symbol in last_seq and sequence <= last_seq[symbol]:
                    raise ValueError("book sequence regressed in persisted evidence")
                last_seq[symbol] = sequence
                if payload.get("best_bid") is None or payload.get("best_ask") is None:
                    raise ValueError("book top of book missing")
                counts["books"] += 1
            elif kind == "public_trade":
                trades = payload.get("trades")
                if not isinstance(trades, list) or not trades:
                    raise ValueError("trade batch empty")
                for trade in trades:
                    if trade.get("symbol") != symbol or trade.get("exchange_event_ms") is None:
                        raise ValueError("trade timestamp or symbol missing")
                counts["trades"] += len(trades)
            else:
                raise ValueError("unknown recorded event kind")
            counts["messages"] += 1
        return {"run_id": run_id, "journal_reopened": True,
                "journal_integrity": "VERIFIED", "manifest_sha256": hashlib.sha256(
                    manifest[0].encode()).hexdigest(), "schema_version": 1,
                "first_ingested_ms": first_ms, "last_ingested_ms": last_ms,
                "last_book_sequence": last_seq, **counts}
    except sqlite3.Error as exc:
        raise ValueError("recorder database unreadable") from exc
    finally:
        connection.close()
