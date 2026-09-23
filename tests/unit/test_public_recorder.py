from pathlib import Path

import pytest

from tradev2.cli import _public_recorder_manifest
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import digest
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
    for index, (payload, source_ms, recorded_ms) in enumerate(
            ((first, source_first, 120), (second, source_second, 130))):
        journal.append(EvidenceEnvelope(event_id=str(index), run_id="recorder-test",
                                     kind="microstructure", recorded_ms=recorded_ms,
                                     source_ms=source_ms, source="public_fixture", payload=payload))
    journal.close()
    audit = inspect_recording(path, "recorder-test")
    assert audit["journal_reopened"] is True
    assert audit["journal_integrity"] == "VERIFIED"
    assert audit["provenance_clean"] is True
    assert (audit["books"], audit["trades"], audit["messages"]) == (1, 1, 2)
    assert audit["last_book_sequence"]["BTCUSDT"] == 2
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
