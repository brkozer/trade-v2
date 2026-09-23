import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from tradev2.alpha.factors import registry, signals
from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import Candle, OrderBookSnapshot
from tradev2.evidence.manifests import create_manifest
from tradev2.research.datasets import Panel
from tradev2.runtime.candidates import load_candidate
from tradev2.runtime.coordinator import SimulationRuntime
from tradev2.strategies.reference import reference_entry, wilder_rsi

ROOT = Path(__file__).resolve().parents[2]
FACTOR_ID = "FINAL_trend_persistence_96_0.025"
SHORT_ID = "FINAL_short_reversal_4_0.012"


def bars(count: int, *, falling: bool, step: Decimal = Decimal("0.1")) -> list[Candle]:
    last = 1_800_000_000_000
    result = []
    for index in range(count):
        close = Decimal("100") + Decimal(index) * step * (-1 if falling else 1)
        result.append(Candle(symbol="BTCUSDT", start_ms=last + index * 900_000,
                             interval_ms=900_000, open=close, high=close, low=close,
                             close=close, volume=Decimal("10"), confirmed=True))
    return result


def decision(storage: Path, mode: Mode, candidate_id: str, *, falling: bool,
             step: Decimal = Decimal("0.1")) -> tuple[dict, object]:
    config = RuntimeConfig(mode=mode, symbols=("BTCUSDT",),
                           profile=f"parity-{mode.value}-{candidate_id[:8]}",
                           candidate_id=candidate_id,
                           fixture_mode=candidate_id != "REFERENCE_CANDIDATE_001")
    with patch("tradev2.runtime.coordinator.create_manifest",
               side_effect=lambda _root, cfg, params: create_manifest(ROOT, cfg, params)):
        runtime = SimulationRuntime(storage, config)
    try:
        history = bars(runtime.candidate.required_bars, falling=falling, step=step)
        final = history[-1]
        timestamp = final.close_ms + 2
        book = OrderBookSnapshot(symbol="BTCUSDT", bids=((final.close, Decimal("100")),),
            asks=((final.close + Decimal("0.01"), Decimal("100")),),
            exchange_event_ms=timestamp - 1, ingested_ms=timestamp)
        rules = InstrumentRules(symbol="BTCUSDT", qty_step=Decimal("0.001"),
            min_qty=Decimal("0.001"), min_notional=Decimal("5"),
            tick_size=Decimal("0.01"), max_qty=Decimal("100"))
        signal = runtime.candidate.signals({"BTCUSDT": history}, {})["BTCUSDT"]
        runtime.evaluate(history, book, rules, timestamp, signal, 1)
        row = runtime.journal.connection.execute(
            "SELECT body FROM events WHERE kind='decision' ORDER BY sequence DESC LIMIT 1").fetchone()
        assert row is not None
        payload = json.loads(row[0])["payload"]
        orders = tuple(order.intent for order in runtime.broker.orders.values())
        assert len(orders) == 1
        return payload, orders[0]
    finally:
        runtime.close()


@pytest.mark.parametrize("candidate_id,falling", [
    ("REFERENCE_CANDIDATE_001", True), (FACTOR_ID, False)])
def test_paper_shadow_share_candidate_signal_risk_and_order_plan(
    tmp_path: Path, candidate_id: str, falling: bool,
) -> None:
    paper, paper_intent = decision(tmp_path, Mode.PAPER, candidate_id, falling=falling)
    shadow, shadow_intent = decision(tmp_path, Mode.SHADOW, candidate_id, falling=falling)
    for field in ("candidate_id", "candidate_family", "candidate_stage", "features",
                  "signal", "side", "candidate_rank", "reason", "decision", "risk",
                  "spread_bps", "maker_fee", "taker_fee", "candle_close_ms"):
        assert paper[field] == shadow[field], field
    for field in ("symbol", "side", "quantity", "reference_price", "stop_price"):
        assert getattr(paper_intent, field) == getattr(shadow_intent, field), field
    assert paper["candidate_stage"] == "TEST_FIXTURE"
    assert paper["decision"] == "TRADE"
    history = bars(64 if candidate_id == "REFERENCE_CANDIDATE_001" else 250,
                   falling=falling)
    if candidate_id == "REFERENCE_CANDIDATE_001":
        closes = [float(bar.close) for bar in history]
        expected = reference_entry(closes, history[-1].start_ms)
        assert paper["signal"] == expected
        assert paper["features"]["rsi"] == wilder_rsi(closes, 14)
    else:
        spec = next(item for item in registry() if item.candidate_id == candidate_id)
        panel = Panel(symbols=("BTCUSDT",),
                      timestamps=np.asarray([bar.start_ms for bar in history], dtype=np.int64),
                      values=np.asarray([[[float(bar.open), float(bar.high), float(bar.low),
                                           float(bar.close), float(bar.volume)]] for bar in history]),
                      manifest={"source": "parity_replay"})
        replay_score = float(signals(panel, spec, {})[-1, 0])
        assert paper["features"]["factor_score"] == replay_score
        assert paper["side"] == ("Buy" if replay_score > 0 else "Sell")


def test_generic_factor_short_path_is_owned_and_protected(tmp_path: Path) -> None:
    payload, intent = decision(tmp_path, Mode.PAPER, SHORT_ID, falling=False, step=Decimal("2"))
    assert payload["side"] == "Sell"
    assert intent.side == "Sell"
    assert intent.stop_price > intent.reference_price
    assert payload["candidate_stage"] == "TEST_FIXTURE"


def test_rejected_factor_cannot_run_without_explicit_fixture_mode() -> None:
    with pytest.raises(PermissionError, match="lacks frozen"):
        load_candidate(ROOT, RuntimeConfig(mode=Mode.SHADOW, candidate_id=FACTOR_ID))
    with pytest.raises(ValueError, match="unknown candidate"):
        load_candidate(ROOT, RuntimeConfig(mode=Mode.PAPER, candidate_id="UNLISTED"))
