import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ops.collect_forward_oi import collect
from tradev2.research.datasets import BAR_MS
from tradev2.venues.bybit_linear.public import PublicBybit

FIRST = int(datetime(2026, 9, 23, 10, tzinfo=UTC).timestamp() * 1000)


def _root(tmp_path: Path) -> tuple[Path, list[str]]:
    source = tmp_path / "data/public/alpha_search_004"
    source.mkdir(parents=True)
    symbols = [f"S{index}USDT" for index in range(20)]
    (source / "manifest.json").write_text(json.dumps({"symbols": symbols}), encoding="utf-8")
    result = tmp_path / "research/results"
    result.mkdir(parents=True)
    (result / "ALPHA_SEARCH_004.json").write_text(json.dumps({
        "finished_at": "2026-09-23T09:45:16+00:00"}), encoding="utf-8")
    return tmp_path, symbols


def _client(*, server_ms: int, missing: str | None = None,
            invalid: str | None = None, wrong_identity: str | None = None,
            stale_response: str | None = None, revised_anchor: str | None = None) -> MagicMock:
    client = MagicMock(spec=PublicBybit)
    client.server_time.return_value = server_ms

    def get(path: str, params: dict[str, str | int]) -> dict:
        assert path == "/v5/market/open-interest"
        assert params["category"] == "linear" and params["intervalTime"] == "15min"
        end = int(params["endTime"])
        times = [end - i * BAR_MS for i in range(int(params["limit"]))]
        if params["symbol"] == missing:
            times = times[:-1]
        rows = [{"timestamp": str(t), "openInterest": "20.5",
                 "singleOpenInterest": "10.25"} for t in times]
        if params["symbol"] == invalid:
            rows[0]["openInterest"] = "NaN"
        if params["symbol"] == revised_anchor:
            rows[-1]["openInterest"] = "21.0"
        return {"time": server_ms - 1 if params["symbol"] == stale_response else server_ms + 10,
                "result": {"category": "linear",
                           "symbol": "WRONGUSDT" if params["symbol"] == wrong_identity
                           else params["symbol"], "list": rows}}

    client.get.side_effect = get
    return client


def test_collects_contiguous_write_once_oi(tmp_path: Path) -> None:
    root, symbols = _root(tmp_path)
    client = _client(server_ms=FIRST + 2 * BAR_MS + 120_000)
    manifest = collect(root, client)
    target = root / "data/public" / f"prospective_oi_{FIRST}_{FIRST + BAR_MS}"
    assert manifest["symbols"] == symbols
    assert manifest["first_timestamp_ms"] == FIRST
    assert manifest["last_timestamp_ms"] == FIRST + BAR_MS
    assert manifest["points_per_symbol"] == 2
    assert manifest["safe_available_ms"] >= FIRST + 2 * BAR_MS
    assert manifest["safe_available_ms"] >= manifest["latest_response_server_ms"] + 5_000
    assert manifest["clock_probe"]["server_ms"] == FIRST + 2 * BAR_MS + 120_000
    assert manifest["collector_sha256"] == hashlib.sha256(
        (Path(__file__).resolve().parents[2] / "ops/collect_forward_oi.py").read_bytes()).hexdigest()
    assert hashlib.sha256((target / "oi.json").read_bytes()).hexdigest() == manifest["oi_sha256"]
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, client, first_timestamp_ms=FIRST)
    second = collect(root, _client(server_ms=FIRST + 4 * BAR_MS + 120_000))
    assert second["first_timestamp_ms"] == FIRST + 2 * BAR_MS
    assert second["last_timestamp_ms"] == FIRST + 3 * BAR_MS


def test_rejects_gap_invalid_quantity_and_hash_drift(tmp_path: Path) -> None:
    root, symbols = _root(tmp_path)
    server = FIRST + 2 * BAR_MS + 120_000
    with pytest.raises(ValueError, match="timestamp gap"):
        collect(root, _client(server_ms=server, missing=symbols[-1]))
    with pytest.raises(ValueError, match="invalid OI"):
        collect(root, _client(server_ms=server, invalid=symbols[-1]))
    with pytest.raises(ValueError, match="identity mismatch"):
        collect(root, _client(server_ms=server, wrong_identity=symbols[-1]))
    with pytest.raises(ValueError, match="response time inconsistent"):
        collect(root, _client(server_ms=server, stale_response=symbols[-1]))
    assert not list((root / "data/public").glob("prospective_oi_*"))
    collect(root, _client(server_ms=server))
    prior = root / "data/public" / f"prospective_oi_{FIRST}_{FIRST + BAR_MS}" / "oi.json"
    prior.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash drift"):
        collect(root, _client(server_ms=server + 2 * BAR_MS))


def test_rejects_nonprospective_start(tmp_path: Path) -> None:
    root, _ = _root(tmp_path)
    with pytest.raises(ValueError, match="post-004"):
        collect(root, _client(server_ms=FIRST + 2 * BAR_MS + 120_000),
                first_timestamp_ms=FIRST - BAR_MS)


def test_rejects_historical_oi_revision_without_mutating_prior_chunk(tmp_path: Path) -> None:
    root, symbols = _root(tmp_path)
    collect(root, _client(server_ms=FIRST + 2 * BAR_MS + 120_000))
    prior = root / "data/public" / f"prospective_oi_{FIRST}_{FIRST + BAR_MS}" / "oi.json"
    prior_hash = hashlib.sha256(prior.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="historical revision"):
        collect(root, _client(server_ms=FIRST + 4 * BAR_MS + 120_000,
                              revised_anchor=symbols[-1]))
    assert hashlib.sha256(prior.read_bytes()).hexdigest() == prior_hash
    assert len(list((root / "data/public").glob("prospective_oi_*"))) == 1
