import json
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed

from tradev2.cli import _public_recorder_manifest
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import digest
from tradev2.marketdata import recorder
from tradev2.marketdata.integrity import OrderBook
from tradev2.marketdata.recorder import normalize_message
from tradev2.marketdata.recording_audit import inspect_recording


def test_public_recorder_manifest_names_subscription_not_shadow_config() -> None:
    root = Path(__file__).resolve().parents[2]
    symbols = ("XRPUSDT", "SOLUSDT", "DOGEUSDT")
    manifest = _public_recorder_manifest(root, symbols)
    assert manifest.universe == symbols
    assert manifest.config["symbols"] == list(symbols)
    assert manifest.config["profile"] == "public-recorder"
    assert manifest.candidate_id == "PUBLIC_RECORDER"
    assert manifest.initial_equity_source is None
    assert manifest.fee_provenance == "public market data only; no authenticated fee schedule"


def _manifest(*, universe: tuple[str, ...] = ("BTCUSDT",)) -> RunManifest:
    config = {"symbols": list(universe)}
    return RunManifest(run_id="recorder-test", git_sha="a" * 40, dirty=False,
        mode="shadow", started_ms=1, config=config, config_hash=digest(config),
        candidate_id="public-recorder", candidate_version="1", parameter_hash="c" * 64,
        venue="bybit_linear", universe=universe, universe_hash=digest(universe),
        fee_provenance="not applicable", dataset_identity=None,
        python_version="3.11", package_versions={}, initial_equity_source=None)


def test_recorder_normalizes_reopens_and_preserves_sequence(tmp_path) -> None:
    books = {"BTCUSDT": OrderBook("BTCUSDT")}
    snapshot = {"topic": "orderbook.50.BTCUSDT", "type": "snapshot", "ts": 100,
                "cts": 99, "data": {"s": "BTCUSDT", "u": 1, "seq": 2,
                                      "b": [["100", "2"]], "a": [["101", "3"]]}}
    trade = {"topic": "publicTrade.BTCUSDT", "ts": 110,
             "data": [{"s": "BTCUSDT", "i": "execution-1", "S": "Buy",
                       "p": "101", "v": "0.1", "T": 108}]}
    first, source_first = normalize_message(snapshot, books, 120)
    second, source_second = normalize_message(trade, books, 130)
    assert (first["update_id"], first["seq"], first["cts"]) == (1, 2, 99)
    assert (first["best_bid"], first["best_ask"]) == ("100", "101")
    assert second["trades"][0]["exchange_event_ms"] == 108
    path = tmp_path / "public.sqlite"
    journal = Journal(path)
    journal.register(_manifest())
    start_probe = {"phase": "start", "local_before_ms": 90, "server_ms": 105,
                   "local_after_ms": 100, "wall_elapsed_ms": 10,
                   "monotonic_elapsed_ms": 10, "server_minus_local_after_ms": 5,
                   "server_minus_local_before_ms": 15, "status": "WALL_CLOCK_STABLE"}
    journal.append(EvidenceEnvelope(event_id="clock-start", run_id="recorder-test",
        kind="clock_probe", recorded_ms=100, source_ms=105,
        source="bybit_public_rest", payload=start_probe))
    for index, (payload, source_ms, recorded_ms) in enumerate(
            ((first, source_first, 120), (second, source_second, 130))):
        journal.append(EvidenceEnvelope(event_id=str(index), run_id="recorder-test",
                                     kind="microstructure", recorded_ms=recorded_ms,
                                     source_ms=source_ms, source="public_fixture", payload=payload))
    end_probe = {**start_probe, "phase": "end", "local_before_ms": 130,
                 "local_after_ms": 135, "server_ms": 140, "wall_elapsed_ms": 5,
                 "monotonic_elapsed_ms": 5, "server_minus_local_before_ms": 10}
    journal.append(EvidenceEnvelope(event_id="clock-end", run_id="recorder-test",
        kind="clock_probe", recorded_ms=135, source_ms=140,
        source="bybit_public_rest", payload=end_probe))
    journal.append(EvidenceEnvelope(event_id="complete", run_id="recorder-test",
        kind="recorder_complete", recorded_ms=140, source="fixture",
        payload={"messages": 2, "books": 1, "trades": 1}))
    journal.close()
    audit = inspect_recording(path, "recorder-test")
    assert audit["journal_reopened"] is True
    assert audit["journal_integrity"] == "VERIFIED"
    assert audit["provenance_clean"] is True
    assert audit["completion_events"] == 1
    assert audit["source_failure_events"] == 0
    assert audit["clock_coverage"] == "START_END_OBSERVED"
    assert len(audit["clock_probes"]) == 2
    assert audit["clock_probe_failures"] == 0
    assert (audit["books"], audit["trades"], audit["messages"]) == (1, 1, 2)
    assert audit["last_book_sequence"]["BTCUSDT"] == 2
    assert audit["book_quality"]["BTCUSDT"] == {
        "books": 1, "max_ingestion_gap_ms": 0,
        "gaps_over_1s": 0, "gaps_over_5s": 0,
        "exchange_lag_over_5s": 0, "exchange_future_over_1s": 0,
        "exchange_ahead_of_local": 0,
        "min_exchange_lag_ms": 20, "max_exchange_lag_ms": 20,
    }
    regressed = {**snapshot, "type": "delta", "data": {**snapshot["data"], "u": 2, "seq": 1}}
    with pytest.raises(ValueError, match="out-of-order"):
        normalize_message(regressed, books, 140)


def test_readback_rejects_event_outside_manifest_universe(tmp_path) -> None:
    path = tmp_path / "misstated.sqlite"
    journal = Journal(path)
    journal.register(_manifest(universe=("ETHUSDT",)))
    journal.append(EvidenceEnvelope(event_id="mismatched", run_id="recorder-test",
        kind="microstructure", recorded_ms=120, source_ms=100, source="fixture",
        payload={"schema_version": 1, "ingested_ms": 120,
                 "exchange_event_ms": 100, "symbol": "BTCUSDT",
                 "kind": "orderbook", "update_id": 1, "seq": 2, "cts": 99,
                 "best_bid": "100", "best_ask": "101"}))
    journal.close()
    with pytest.raises(ValueError, match="outside manifest universe"):
        inspect_recording(path, "recorder-test")


def test_readback_reports_delayed_books_and_ingestion_gaps(tmp_path) -> None:
    path = tmp_path / "lag.sqlite"
    journal = Journal(path)
    journal.register(_manifest())
    for index, (ingested, source) in enumerate(((120, 100), (7_120, 120))):
        journal.append(EvidenceEnvelope(event_id=str(index), run_id="recorder-test",
            kind="microstructure", recorded_ms=ingested, source_ms=source,
            source="fixture", payload={"schema_version": 1, "ingested_ms": ingested,
                "exchange_event_ms": source, "symbol": "BTCUSDT", "kind": "orderbook",
                "update_id": index + 1, "seq": index + 2, "cts": source,
                "best_bid": "100", "best_ask": "101"}))
    journal.append(EvidenceEnvelope(event_id="complete", run_id="recorder-test",
        kind="recorder_complete", recorded_ms=7_130, source="fixture",
        payload={"messages": 2, "books": 2, "trades": 0}))
    journal.close()
    quality = inspect_recording(path, "recorder-test")["book_quality"]["BTCUSDT"]
    assert quality["books"] == 2
    assert quality["max_ingestion_gap_ms"] == 7_000
    assert quality["gaps_over_1s"] == quality["gaps_over_5s"] == 1
    assert quality["exchange_lag_over_5s"] == 1
    assert quality["exchange_ahead_of_local"] == 0
    assert quality["min_exchange_lag_ms"] == 20
    assert quality["max_exchange_lag_ms"] == 7_000


def test_readback_exposes_subsecond_cross_clock_inversion(tmp_path) -> None:
    path = tmp_path / "clock-skew.sqlite"
    journal = Journal(path)
    journal.register(_manifest())
    journal.append(EvidenceEnvelope(event_id="ahead", run_id="recorder-test",
        kind="microstructure", recorded_ms=120, source_ms=820, source="fixture",
        payload={"schema_version": 1, "ingested_ms": 120,
                 "exchange_event_ms": 820, "symbol": "BTCUSDT", "kind": "orderbook",
                 "update_id": 1, "seq": 2, "cts": 819,
                 "best_bid": "100", "best_ask": "101"}))
    journal.append(EvidenceEnvelope(event_id="complete", run_id="recorder-test",
        kind="recorder_complete", recorded_ms=140, source="fixture",
        payload={"messages": 1, "books": 1, "trades": 0}))
    journal.close()
    quality = inspect_recording(path, "recorder-test")["book_quality"]["BTCUSDT"]
    assert quality["exchange_ahead_of_local"] == 1
    assert quality["exchange_future_over_1s"] == 0
    assert quality["min_exchange_lag_ms"] == quality["max_exchange_lag_ms"] == -700


@pytest.mark.parametrize("completion_count", [0, 2])
def test_readback_requires_exactly_one_completion(tmp_path, completion_count: int) -> None:
    path = tmp_path / "completion.sqlite"
    journal = Journal(path)
    journal.register(_manifest())
    journal.append(EvidenceEnvelope(event_id="book", run_id="recorder-test",
        kind="microstructure", recorded_ms=120, source_ms=100, source="fixture",
        payload={"schema_version": 1, "ingested_ms": 120,
                 "exchange_event_ms": 100, "symbol": "BTCUSDT",
                 "kind": "orderbook", "update_id": 1, "seq": 2, "cts": 99,
                 "best_bid": "100", "best_ask": "101"}))
    for index in range(completion_count):
        journal.append(EvidenceEnvelope(event_id=f"complete-{index}", run_id="recorder-test",
            kind="recorder_complete", recorded_ms=140 + index, source="fixture",
            payload={"messages": 1, "books": 1, "trades": 0}))
    journal.close()
    with pytest.raises(ValueError, match="exactly one completion"):
        inspect_recording(path, "recorder-test")


def test_readback_rejects_false_completion_counts(tmp_path) -> None:
    path = tmp_path / "false-count.sqlite"
    journal = Journal(path)
    journal.register(_manifest())
    journal.append(EvidenceEnvelope(event_id="book", run_id="recorder-test",
        kind="microstructure", recorded_ms=120, source_ms=100, source="fixture",
        payload={"schema_version": 1, "ingested_ms": 120,
                 "exchange_event_ms": 100, "symbol": "BTCUSDT",
                 "kind": "orderbook", "update_id": 1, "seq": 2, "cts": 99,
                 "best_bid": "100", "best_ask": "101"}))
    journal.append(EvidenceEnvelope(event_id="complete", run_id="recorder-test",
        kind="recorder_complete", recorded_ms=140, source="fixture",
        payload={"messages": 2, "books": 1, "trades": 0}))
    journal.close()
    with pytest.raises(ValueError, match="completion counts disagree"):
        inspect_recording(path, "recorder-test")


def test_websocket_close_is_recorded_and_retry_bounded(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClosedConnection:
        def __enter__(self):
            raise ConnectionClosed(None, None)

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(recorder, "connect", lambda *_args, **_kwargs: ClosedConnection())
    journal = Journal(tmp_path / "closed.sqlite")
    journal.register(_manifest())
    with pytest.raises(RuntimeError, match="retry budget exhausted"):
        recorder.record_public(journal, "recorder-test", ("BTCUSDT",), 1)
    assert journal.connection.execute(
        "SELECT count(*) FROM events WHERE kind='source_failure'").fetchone()[0] == 3
    journal.close()



@pytest.mark.parametrize("frame", ["not json", "42", "[1, 2]"])
def test_malformed_frame_is_one_failure_inside_the_retry_budget(
    tmp_path, monkeypatch: pytest.MonkeyPatch, frame: str,
) -> None:
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _payload):
            return None

        def recv(self, timeout):
            return frame

    monkeypatch.setattr(recorder, "connect", lambda *_args, **_kwargs: Socket())
    journal = Journal(tmp_path / "malformed.sqlite")
    journal.register(_manifest())
    with pytest.raises(RuntimeError, match="retry budget exhausted"):
        recorder.record_public(journal, "recorder-test", ("BTCUSDT",), 5)
    rows = [json.loads(row[0])["payload"] for row in journal.connection.execute(
        "SELECT body FROM events WHERE kind='source_failure'")]
    journal.close()
    # One journaled failure per malformed frame, each counted once against the budget.
    assert len(rows) == 3
    assert all(row["status"] == "RESEED_REQUIRED" for row in rows)
