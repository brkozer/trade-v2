"""Adversarial regression tests for simulation runtime controls and evidence binding."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from pydantic import ValidationError

from tradev2.alpha.candidates import candidate_grid, decisions
from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import Candle, OrderBookSnapshot
from tradev2.domain.orders import OrderIntent, OrderStatus
from tradev2.evidence.journal import Journal, bound_checkpoint, verify_connection
from tradev2.evidence.manifests import create_manifest
from tradev2.paper.broker import FUNDING_CONVENTION, PaperBroker
from tradev2.research.datasets import BAR_MS, Panel
from tradev2.runtime.candidates import ReferencePolicy
from tradev2.runtime.coordinator import SimulationRuntime
from tradev2.strategies.reference import REFERENCE_PARAMS, wilder_rsi

ROOT = Path(__file__).resolve().parents[2]
START = 1_800_000_000_000 - (1_800_000_000_000 % BAR_MS)


def rules() -> InstrumentRules:
    return InstrumentRules(symbol="BTCUSDT", qty_step=Decimal("0.001"), min_qty=Decimal("0.001"),
                           min_notional=Decimal("5"), tick_size=Decimal("0.01"),
                           max_qty=Decimal("100"))


def candles(closes: list[float]) -> list[Candle]:
    return [Candle(symbol="BTCUSDT", start_ms=START + index * BAR_MS, interval_ms=BAR_MS,
                   open=Decimal(str(close)), high=Decimal(str(close)), low=Decimal(str(close)),
                   close=Decimal(str(close)), volume=Decimal("10"), confirmed=True)
            for index, close in enumerate(closes)]


def book(event_ms: int, bid: str, ask: str, size: str = "100") -> OrderBookSnapshot:
    return OrderBookSnapshot(symbol="BTCUSDT", bids=((Decimal(bid), Decimal(size)),),
                             asks=((Decimal(ask), Decimal(size)),), exchange_event_ms=event_ms,
                             ingested_ms=event_ms + 1)


def runtime(storage: Path, **updates: object) -> SimulationRuntime:
    config = RuntimeConfig(mode=Mode.PAPER, symbols=("BTCUSDT",), profile="controls",
                           **updates)  # type: ignore[arg-type]
    with patch("tradev2.runtime.coordinator.create_manifest",
               side_effect=lambda _root, cfg, params: create_manifest(ROOT, cfg, params)):
        return SimulationRuntime(storage, config)


def zigzag(count: int) -> list[float]:
    """Non-monotone closes ending in a sharp drop, so different RSI periods disagree."""
    closes = [100.0]
    for index in range(1, count - 6):
        closes.append(closes[-1] + (0.7 if index % 3 else -1.1))
    for _ in range(6):
        closes.append(closes[-1] - 2.5)
    return closes


def test_reference_strength_matches_research_ranking_value() -> None:
    closes = zigzag(260)
    policy = ReferencePolicy()
    window = candles(closes)[-policy.required_bars:]
    signal = policy.signals({"BTCUSDT": window}, {})["BTCUSDT"]
    rsi = wilder_rsi([float(bar.close) for bar in window], REFERENCE_PARAMS.entry_period)
    assert signal.active and signal.features["rsi"] == rsi
    assert wilder_rsi(closes, 14) != pytest.approx(rsi)
    assert signal.strength == pytest.approx((100 - rsi) / 100)
    reference = next(item for item in candidate_grid() if item.reference is not None
                     and item.candidate_id == REFERENCE_PARAMS.candidate_id)
    values = np.asarray([[[close, close, close, close, 10.0]] for close in closes])
    panel = Panel(("BTCUSDT",), np.arange(len(closes), dtype=np.int64) * BAR_MS + START, values, {})
    research_strength = float(decisions(panel, reference)[0][-1, 0])
    # Wilder smoothing from different seeds converges; 64 bars of period 4 agree closely.
    assert research_strength == pytest.approx(signal.strength, abs=1e-6)


def test_risk_halt_latches_cancels_resting_entries_and_survives_resume(tmp_path: Path) -> None:
    first = runtime(tmp_path)
    try:
        resting = OrderIntent(owner_id=first.manifest.run_id, decision_id="resting",
                              symbol="BTCUSDT", side="Buy", quantity=Decimal("0.1"),
                              reference_price=Decimal("100"), stop_price=Decimal("98"),
                              available_ms=1)
        first.broker.submit(resting, rules())
        history = candles(zigzag(80))
        final = history[-1]
        now = final.close_ms + 5
        # A loss beyond the daily limit since the day's first observation forces HALT.
        first._roll_day(now)
        first.broker.cash -= Decimal("60")
        signal = first.candidate.signals({"BTCUSDT": history}, {})["BTCUSDT"]
        first.broker.orders.clear()
        first.evaluate(history, book(now - 1, str(final.close), str(final.close + Decimal("0.01"))),
                       rules(), now, signal, 1)
        assert first.pending_halt is True and first.halt_reason == "ACCOUNT_LIMIT"
        first.broker.submit(resting.model_copy(update={"decision_id": "late"}), rules())
        first._latch_halt("ACCOUNT_LIMIT")  # already latched: idempotent, no second cancel
        assert any(order.unresolved for order in first.broker.orders.values())
        first.pending_halt = False
        first._latch_halt("ACCOUNT_LIMIT")
        assert all(not order.unresolved for order in first.broker.orders.values())
        assert all(order.status == OrderStatus.CANCELLED for order in first.broker.orders.values())
        run_id = first.manifest.run_id
    finally:
        first.close()
    resumed = SimulationRuntime(tmp_path, first.config, resume=run_id)
    try:
        assert resumed.pending_halt is True and resumed.halt_reason == "ACCOUNT_LIMIT"
        later = candles(zigzag(81))
        final = later[-1]
        now = final.close_ms + 5
        resumed.evaluate(later, book(now - 1, str(final.close), str(final.close + Decimal("0.01"))),
                         rules(), now, resumed.candidate.signals({"BTCUSDT": later}, {})["BTCUSDT"], 1)
        row = resumed.journal.connection.execute(
            "SELECT body FROM events WHERE kind='decision' ORDER BY sequence DESC LIMIT 1").fetchone()
        assert json.loads(row[0])["payload"]["reason"] == "HALT_LATCHED"
    finally:
        resumed.close()


def test_daily_loss_uses_the_day_baseline_not_cumulative_cash(tmp_path: Path) -> None:
    current = runtime(tmp_path)
    try:
        intent = OrderIntent(owner_id=current.manifest.run_id, decision_id="d", symbol="BTCUSDT",
                             side="Buy", quantity=Decimal("1"), reference_price=Decimal("100"),
                             stop_price=Decimal("98"), available_ms=1)
        day = 20_000 * 86_400_000
        # Up 10% before the day began; losing 4% intraday stays within the 5% daily limit.
        current.broker.cash += Decimal("100")
        current._roll_day(day)
        current.broker.cash -= Decimal("40")
        assert current._risk(intent, rules(), day + 1)["action"] != "HALT"
        # 7% down on the day halts although the run is still up 3% cumulatively.
        current.broker.cash -= Decimal("30")
        halted = current._risk(intent, rules(), day + 2)
        assert (halted["action"], halted["reason"]) == ("HALT", "ACCOUNT_LIMIT")
        # The next UTC day starts a new baseline from the equity then observed.
        assert current._risk(intent, rules(), day + 86_400_000)["action"] != "HALT"
        assert current.day_baseline == (day // 86_400_000 + 1, Decimal("1030"))
    finally:
        current.close()


def test_time_stop_counts_from_the_entry_bar_like_the_replay(tmp_path: Path) -> None:
    # A factor fixture exits on holding time alone (the reference RSI exit would fire on flat bars).
    current = runtime(tmp_path, candidate_id="FINAL_trend_persistence_96_0.025", fixture_mode=True)
    try:
        broker = current.broker
        intent = OrderIntent(owner_id=current.manifest.run_id, decision_id="t", symbol="BTCUSDT",
                             side="Buy", quantity=Decimal("0.1"), reference_price=Decimal("100"),
                             stop_price=Decimal("90"), available_ms=START + 10)
        broker.submit(intent, rules())
        fill_ms = START + 60_000  # inside bar 0, after its open
        broker.observe(book(fill_ms, "99.98", "99.99"), fill_ms + 1)
        assert broker.positions["BTCUSDT"].opened_ms == fill_ms
        bars_needed = int(current.candidate.parameters()["holding_bars"])
        flat = [100.0] * (current.candidate.required_bars + bars_needed)
        history = candles(flat)
        # Re-anchor so bar 0 of the position is the entry bar at START.
        shift = len(history) - bars_needed
        history = [bar.model_copy(update={"start_ms": bar.start_ms - shift * BAR_MS})
                   for bar in history]
        closing = history[-1]
        assert closing.close_ms == START + bars_needed * BAR_MS
        now = closing.close_ms + 5
        current.evaluate(history, book(now - 1, "100", "100.01"), rules(), now,
                         current.candidate.signals({"BTCUSDT": history}, {})["BTCUSDT"], 1)
        assert "BTCUSDT" not in broker.positions
        exits = [json.loads(row[0])["payload"] for row in current.journal.connection.execute(
            "SELECT body FROM events WHERE kind='decision'")]
        assert exits[0]["decision"] == "EXIT" and exits[0]["exit_reason"] == "TIME_STOP"
        assert exits[0]["held_bars"] == bars_needed and exits[0]["exit_outcome"] == "EXECUTED"
    finally:
        current.close()


def test_one_sided_book_keeps_previous_mark(tmp_path: Path) -> None:
    current = runtime(tmp_path)
    try:
        current.marks["BTCUSDT"] = Decimal("99")
        one_sided = OrderBookSnapshot(symbol="BTCUSDT", bids=((Decimal("100"), Decimal("1")),),
                                      asks=(), exchange_event_ms=START, ingested_ms=START + 1)
        history = candles(zigzag(80))
        current.evaluate(history, one_sided, rules(), START + 2,
                         current.candidate.signals({"BTCUSDT": history}, {})["BTCUSDT"], 1)
        assert current.marks["BTCUSDT"] == Decimal("99")
    finally:
        current.close()


def test_exit_cancels_entry_journals_it_and_never_reuses_a_book() -> None:
    broker = PaperBroker(Decimal("1000"))
    intent = OrderIntent(owner_id="run", decision_id="x", symbol="BTCUSDT", side="Buy",
                         quantity=Decimal("5"), reference_price=Decimal("100"),
                         stop_price=Decimal("98"), available_ms=100)
    order_id = broker.submit(intent, rules())
    broker.observe(book(130, "99.9", "99.99", "8"), 131)
    assert broker.orders[order_id].status == OrderStatus.PARTIALLY_FILLED
    broker.drain()
    snapshot = book(140, "101", "101.01", "4")
    assert broker.exit(snapshot, 141, "TIME_STOP") == "PARTIAL"
    events = broker.drain()
    order_events = [payload for kind, payload in events if kind == "order"]
    assert order_events and order_events[0]["status"] == OrderStatus.CANCELLED
    assert broker.exit(snapshot, 141, "RSI_EXIT") == "UNEXECUTED_BOOK_ALREADY_USED"
    trades = [payload for kind, payload in events if kind == "trade"]
    assert len(trades) == 1 and trades[0]["funding_convention"] == FUNDING_CONVENTION
    restored = PaperBroker.restore(broker.checkpoint())
    assert restored.exit(snapshot, 141, "RSI_EXIT") == "UNEXECUTED_BOOK_ALREADY_USED"
    zero_depth = PaperBroker(Decimal("1000"))
    second = zero_depth.submit(intent, rules())
    zero_depth.observe(book(130, "99.9", "99.99", "8"), 131)
    assert zero_depth.exit(book(140, "101", "101.01", "0.002"), 141, "TIME_STOP") == "UNEXECUTED_DEPTH"
    assert not zero_depth.orders[second].unresolved


def manifest(run_id: str = "test") -> RunManifest:
    return RunManifest(run_id=run_id, git_sha="a" * 40, dirty=False, mode="paper", started_ms=1,
        config={}, config_hash="b" * 64, candidate_id="reference", candidate_version="1",
        parameter_hash="c" * 64, venue="bybit_linear", universe=("BTCUSDT",),
        universe_hash="d" * 64, fee_provenance="fixture", dataset_identity=None,
        python_version="3.11", package_versions={}, initial_equity_source=None)


def journal_with_history(path: Path) -> Journal:
    journal = Journal(path)
    journal.register(manifest())
    for index in range(3):
        journal.append(EvidenceEnvelope(event_id=f"e{index}", run_id="test", kind="runtime",
                                        recorded_ms=10 + index, source="fixture", payload={}))
    journal.checkpoint("c1", "test", 20, {"cash": "1000"})
    return journal


@pytest.mark.parametrize("tamper", [
    "tail_truncation", "middle_deletion", "column_edit", "manifest_edit", "checkpoint_edit",
    "trigger_drop", "all_events_deleted"])
def test_journal_tampering_is_detected(tmp_path: Path, tamper: str) -> None:
    journal = journal_with_history(tmp_path / "j.sqlite")
    assert journal.verify()
    connection = journal.connection
    for name in ("events_immutable_update", "events_immutable_delete", "runs_immutable_update",
                 "checkpoints_immutable_update"):
        connection.execute(f"DROP TRIGGER {name}")
    statements = {
        "tail_truncation": "DELETE FROM events WHERE sequence=(SELECT max(sequence) FROM events)",
        "middle_deletion": "DELETE FROM events WHERE event_id='e1'",
        "column_edit": "UPDATE events SET kind='trade' WHERE event_id='e2'",
        "manifest_edit": "UPDATE runs SET manifest=replace(manifest,'fixture','edited')",
        "checkpoint_edit": "UPDATE checkpoints SET body='{\"cash\":\"9999\"}'",
        "trigger_drop": "SELECT 1",
        "all_events_deleted": "DELETE FROM events",
    }
    connection.execute(statements[tamper])
    connection.commit()
    if tamper != "trigger_drop":
        # Even with the guards restored, the content change must still be detected.
        connection.executescript(
            "CREATE TRIGGER events_immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'x'); END;"
            "CREATE TRIGGER events_immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'x'); END;"
            "CREATE TRIGGER runs_immutable_update BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'x'); END;"
            "CREATE TRIGGER checkpoints_immutable_update BEFORE UPDATE ON checkpoints BEGIN SELECT RAISE(ABORT, 'x'); END;")
    assert verify_connection(connection) is False
    journal.close()


def test_unbound_or_diverged_checkpoints_refuse_resume(tmp_path: Path) -> None:
    first = runtime(tmp_path)
    run_id = first.manifest.run_id
    config = first.config
    first.close()
    path = tmp_path / "runtime/paper" / run_id / "journal.sqlite"
    raw = sqlite3.connect(path)
    # A legacy-style checkpoint row without a chained binding is newest by insertion order.
    raw.execute("INSERT INTO checkpoints VALUES ('legacy', ?, 0, '{}')", (run_id,))
    raw.commit()
    raw.close()
    with _Opened(path) as journal:
        assert bound_checkpoint(journal.connection, run_id) is None
    with pytest.raises(ValueError, match="not bound"):
        SimulationRuntime(tmp_path, config, resume=run_id)
    second = runtime(tmp_path / "second")
    second_id = second.manifest.run_id
    second.checkpoint()
    second.emit("fill", {"symbol": "BTCUSDT", "note": "journaled after the checkpoint"})
    second.journal.close()
    second.authority.release()
    with pytest.raises(ValueError, match="after the last checkpoint"):
        SimulationRuntime(tmp_path / "second", second.config, resume=second_id)


class _Opened:
    def __init__(self, path: Path) -> None:
        self.journal = Journal(path)

    def __enter__(self) -> Journal:
        return self.journal

    def __exit__(self, *_: object) -> None:
        self.journal.close()


def test_resume_records_software_identity(tmp_path: Path) -> None:
    first = runtime(tmp_path)
    run_id, config = first.manifest.run_id, first.config
    first.close()
    resumed = SimulationRuntime(tmp_path, config, resume=run_id)
    try:
        row = resumed.journal.connection.execute(
            "SELECT body FROM events WHERE kind='runtime' ORDER BY sequence DESC LIMIT 1").fetchone()
        payload = json.loads(row[0])["payload"]
        assert payload["status"] == "STARTING"
        assert payload["resumed_from_checkpoint"]
        assert set(payload["software"]) >= {"git_sha", "dirty", "python_version"}
        assert isinstance(payload["software_matches_manifest"], bool)
    finally:
        resumed.close()


@pytest.mark.parametrize("updates", [
    {"symbols": ()}, {"symbols": ("BTCUSDT", "BTCUSDT")}, {"symbols": ("btcusdt",)},
    {"symbols": ("BTC-PERP",)}, {"max_spread_bps": "1000000"}, {"source_max_age_ms": 60_000}])
def test_runtime_config_rejects_unusable_universes_and_disabled_gates(updates: dict) -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({"mode": "paper", **updates})
    assert RuntimeConfig(symbols=("1000PEPEUSDT", "BTCUSDT")).symbols[0] == "1000PEPEUSDT"



@pytest.mark.parametrize("book_offset,now_offset,expected", [
    (-1, 5, 0),                # quote observed before the close that revealed the signal
    (0, 5, 1),                 # quote at the close is the earliest permitted observation
    (0, 2 * BAR_MS, 0),        # the bar is older than one interval: never act on it late
])
def test_evaluate_enforces_close_availability_boundaries(
    tmp_path: Path, book_offset: int, now_offset: int, expected: int,
) -> None:
    current = runtime(tmp_path)
    try:
        history = candles(zigzag(80))
        final = history[-1]
        now = final.close_ms + now_offset
        snapshot = book(final.close_ms + book_offset, str(final.close),
                        str(final.close + Decimal("0.01")))
        current.evaluate(history, snapshot, rules(), now,
                         current.candidate.signals({"BTCUSDT": history}, {})["BTCUSDT"], 1)
        decisions = current.journal.connection.execute(
            "SELECT count(*) FROM events WHERE kind='decision'").fetchone()[0]
        assert decisions == expected
    finally:
        current.close()
