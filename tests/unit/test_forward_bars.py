import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ops.collect_forward_bars import collect
from tradev2.domain.market import Candle
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


def _client(*, missing: str | None = None, confirmed: bool = True,
            opened: int = FIRST) -> MagicMock:
    client = MagicMock(spec=PublicBybit)
    client.server_time.return_value = opened + BAR_MS + 120_000

    def candles(symbol: str, *, limit: int, end_ms: int) -> list[Candle]:
        assert limit == 200
        assert end_ms == opened + BAR_MS - 1
        if symbol == missing:
            return []
        return [Candle(symbol=symbol, start_ms=opened, interval_ms=BAR_MS,
                       open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
                       close=Decimal("100.5"), volume=Decimal("10"),
                       confirmed=confirmed, ingested_ms=opened + BAR_MS + 120_000)]

    client.candles.side_effect = candles
    return client


def test_collects_immutable_fixed_universe(tmp_path: Path) -> None:
    root, symbols = _root(tmp_path)
    client = _client()
    manifest = collect(root, client, first_open_ms=FIRST)
    target = root / "data/public" / f"prospective_bars_{FIRST}_{FIRST}"
    assert manifest["symbols"] == symbols
    assert manifest["bars_per_symbol"] == 1
    assert manifest["evidence_role"] == "PROSPECTIVE_POST004_UNSCORED"
    assert hashlib.sha256((target / "bars.json").read_bytes()).hexdigest() == manifest["bars_sha256"]
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, client, first_open_ms=FIRST)
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, client, first_open_ms=FIRST + 2 * BAR_MS)
    next_manifest = collect(root, _client(opened=FIRST + BAR_MS),
                            first_open_ms=FIRST + BAR_MS)
    assert next_manifest["first_open_ms"] == FIRST + BAR_MS


def test_rejects_prior_hash_drift(tmp_path: Path) -> None:
    root, _ = _root(tmp_path)
    collect(root, _client(), first_open_ms=FIRST)
    prior = root / "data/public" / f"prospective_bars_{FIRST}_{FIRST}" / "bars.json"
    prior.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash drift"):
        collect(root, _client(opened=FIRST + BAR_MS), first_open_ms=FIRST + BAR_MS)


def test_rejects_consumed_or_incomplete_evidence_before_writing(tmp_path: Path) -> None:
    root, symbols = _root(tmp_path)
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, _client(), first_open_ms=FIRST - BAR_MS)
    with pytest.raises(ValueError, match="history ended early"):
        collect(root, _client(missing=symbols[-1]), first_open_ms=FIRST)
    with pytest.raises(ValueError, match="unconfirmed"):
        collect(root, _client(confirmed=False), first_open_ms=FIRST)
    assert not list((root / "data/public").glob("prospective_bars_*"))
