"""Read-back acceptance of a closed prospective public recording."""

import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from tradev2.domain.evidence import RunManifest
from tradev2.evidence.journal import open_reader, verify_connection
from tradev2.evidence.manifests import digest


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
        run = RunManifest.model_validate_json(manifest[0])
        if (not run.universe or list(run.universe) != run.config.get("symbols")
                or run.universe_hash != digest(run.universe)
                or run.config_hash != digest(run.config)):
            raise ValueError("recorder manifest universe or config provenance mismatch")
        expected_symbols = set(run.universe)
        observed_symbols: set[str] = set()
        counts: dict[str, int] = defaultdict(int)
        last_seq: dict[str, int] = {}
        last_book_ingested: dict[str, int] = {}
        book_quality: dict[str, dict[str, int]] = {}
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
            if not isinstance(symbol, str) or symbol not in expected_symbols:
                raise ValueError("recording symbol outside manifest universe")
            observed_symbols.add(symbol)
            first_ms = min(first_ms, event["recorded_ms"]) if first_ms is not None else event["recorded_ms"]
            last_ms = max(last_ms, event["recorded_ms"]) if last_ms is not None else event["recorded_ms"]
            kind = payload.get("kind")
            if kind == "orderbook":
                if not isinstance(source_ms, int):
                    raise ValueError("book exchange event timestamp missing")
                if payload.get("update_id") is None or payload.get("seq") is None or payload.get("cts") is None:
                    raise ValueError("book update/sequence/matching time missing")
                sequence = int(payload["seq"])
                if symbol in last_seq and sequence <= last_seq[symbol]:
                    raise ValueError("book sequence regressed in persisted evidence")
                last_seq[symbol] = sequence
                if payload.get("best_bid") is None or payload.get("best_ask") is None:
                    raise ValueError("book top of book missing")
                quality = book_quality.setdefault(symbol, {
                    "books": 0, "max_ingestion_gap_ms": 0,
                    "gaps_over_1s": 0, "gaps_over_5s": 0,
                    "exchange_lag_over_5s": 0, "exchange_future_over_1s": 0,
                    "exchange_ahead_of_local": 0,
                    "min_exchange_lag_ms": 1_000_000_000,
                    "max_exchange_lag_ms": -1_000_000_000,
                })
                ingested_ms = int(event["recorded_ms"])
                if symbol in last_book_ingested:
                    gap = ingested_ms - last_book_ingested[symbol]
                    quality["max_ingestion_gap_ms"] = max(quality["max_ingestion_gap_ms"], gap)
                    quality["gaps_over_1s"] += gap > 1_000
                    quality["gaps_over_5s"] += gap > 5_000
                last_book_ingested[symbol] = ingested_ms
                lag = ingested_ms - source_ms
                quality["exchange_lag_over_5s"] += lag > 5_000
                quality["exchange_future_over_1s"] += lag < -1_000
                quality["exchange_ahead_of_local"] += lag < 0
                quality["min_exchange_lag_ms"] = min(quality["min_exchange_lag_ms"], lag)
                quality["max_exchange_lag_ms"] = max(quality["max_exchange_lag_ms"], lag)
                quality["books"] += 1
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
        if observed_symbols != expected_symbols:
            raise ValueError("recording did not observe every manifest symbol")
        completion_rows = connection.execute(
            "SELECT body FROM events WHERE run_id=? AND kind='recorder_complete'", (run_id,)
        ).fetchall()
        if len(completion_rows) != 1:
            raise ValueError("recording needs exactly one completion event")
        completed = json.loads(completion_rows[0][0])["payload"]
        if any(completed.get(key) != counts[key] for key in ("messages", "books", "trades")):
            raise ValueError("recording completion counts disagree with read-back")
        source_failures = connection.execute(
            "SELECT count(*) FROM events WHERE run_id=? AND kind='source_failure'", (run_id,)
        ).fetchone()[0]
        clock_probes: list[dict[str, Any]] = []
        for row in connection.execute(
            "SELECT body FROM events WHERE run_id=? AND kind='clock_probe' ORDER BY sequence", (run_id,)
        ):
            probe_event = json.loads(row[0])
            probe = probe_event["payload"]
            if (probe.get("phase") not in {"start", "end"}
                    or probe.get("server_ms") != probe_event["source_ms"]
                    or probe.get("local_after_ms") != probe_event["recorded_ms"]
                    or probe.get("server_minus_local_after_ms")
                       != probe["server_ms"] - probe["local_after_ms"]
                    or probe.get("server_minus_local_before_ms")
                       != probe["server_ms"] - probe["local_before_ms"]):
                raise ValueError("clock probe provenance mismatch")
            clock_probes.append(probe)
        clock_probe_failures = connection.execute(
            "SELECT count(*) FROM events WHERE run_id=? AND kind='clock_probe_failure'", (run_id,)
        ).fetchone()[0]
        return {"run_id": run_id, "journal_reopened": True,
                "journal_integrity": "VERIFIED", "manifest_sha256": hashlib.sha256(
                    manifest[0].encode()).hexdigest(), "schema_version": 1,
                "manifest_dirty": run.dirty, "provenance_clean": not run.dirty,
                "completion_events": 1, "source_failure_events": source_failures,
                "uninterrupted_feed": source_failures == 0,
                "clock_probes": clock_probes, "clock_probe_failures": clock_probe_failures,
                "clock_coverage": "START_END_OBSERVED" if [p["phase"] for p in clock_probes]
                                  == ["start", "end"] and clock_probe_failures == 0
                                  and all(p.get("status") == "WALL_CLOCK_STABLE" for p in clock_probes)
                                  else "INCOMPLETE",
                "first_ingested_ms": first_ms, "last_ingested_ms": last_ms,
                "last_book_sequence": last_seq, "book_quality": book_quality,
                **counts}
    except sqlite3.Error as exc:
        raise ValueError("recorder database unreadable") from exc
    finally:
        connection.close()
