import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ops.collect_forward_bars import collect, next_open, safe_available_ms
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
    assert next_open(root) == FIRST
    manifest = collect(root, client, first_open_ms=FIRST)
    target = root / "data/public" / f"prospective_bars_{FIRST}_{FIRST}"
    assert manifest["symbols"] == symbols
    assert manifest["bars_per_symbol"] == 1
    assert manifest["evidence_role"] == "PROSPECTIVE_POST004_UNSCORED"
    assert manifest["bar_row_fields"][-1] == "bybit_response_server_ms"
    probe = manifest["clock_probe"]
    assert probe["server_ms"] == manifest["server_time_ms"]
    assert probe["server_minus_local_after_ms"] == probe["server_ms"] - probe["local_after_ms"]
    assert probe["server_minus_local_before_ms"] == probe["server_ms"] - probe["local_before_ms"]
    assert probe["monotonic_elapsed_ms"] >= 0
    assert safe_available_ms(manifest) == manifest["safe_available_ms"]
    assert safe_available_ms(manifest) >= FIRST + BAR_MS
    legacy = {key: value for key, value in manifest.items() if key != "safe_available_ms"}
    assert safe_available_ms(legacy) == manifest["safe_available_ms"]
    assert hashlib.sha256((target / "bars.json").read_bytes()).hexdigest() == manifest["bars_sha256"]
    assert next_open(root) == FIRST + BAR_MS
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, client, first_open_ms=FIRST)
    with pytest.raises(ValueError, match="nonoverlapping"):
        collect(root, client, first_open_ms=FIRST + 2 * BAR_MS)
    next_manifest = collect(root, _client(opened=FIRST + BAR_MS),
                            first_open_ms=FIRST + BAR_MS)
    assert next_manifest["first_open_ms"] == FIRST + BAR_MS
    assert next_open(root) == FIRST + 2 * BAR_MS


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



def test_availability_waits_for_the_later_of_receipt_and_exchange_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ops.collect_forward_bars as bars_module

    root, _ = _root(tmp_path)
    frozen = datetime(2026, 9, 23, 10, 17, tzinfo=UTC)

    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen

    monkeypatch.setattr(bars_module, "datetime", FrozenClock)
    client = _client()
    manifest = collect(root, client, first_open_ms=FIRST)
    frozen_ms = int(frozen.timestamp() * 1000)
    latest = manifest["latest_response_server_ms"]
    assert manifest["schema_version"] == 2
    assert latest == FIRST + BAR_MS + 120_000
    assert manifest["safe_available_ms"] == max(frozen_ms, latest) + 5_000
    assert safe_available_ms(manifest) == manifest["safe_available_ms"]
    with pytest.raises(ValueError, match="mismatch"):
        safe_available_ms({**manifest, "safe_available_ms": manifest["safe_available_ms"] - 1})
    # A host clock behind the exchange cannot make the chunk available early.
    early = datetime(2026, 9, 23, 10, 16, tzinfo=UTC)
    assert safe_available_ms({**manifest, "collected_at": early.isoformat(),
                              "safe_available_ms": latest + 5_000}) == latest + 5_000
