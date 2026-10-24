from decimal import Decimal as D

import pytest

from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import FundingSnapshot, OrderBookSnapshot
from tradev2.domain.orders import OrderIntent, OrderStatus
from tradev2.paper.broker import PaperBroker


def rules() -> InstrumentRules:
    return InstrumentRules(symbol="BTCUSDT", qty_step=D("0.1"), min_qty=D("0.1"),
                           min_notional=D("5"), tick_size=D("0.01"))


def book(event_ms: int, bid: str, ask: str, size: str = "8") -> OrderBookSnapshot:
    return OrderBookSnapshot(symbol="BTCUSDT", bids=((D(bid), D(size)),),
                             asks=((D(ask), D(size)),), exchange_event_ms=event_ms,
                             ingested_ms=event_ms + 1)


def intent() -> OrderIntent:
    return OrderIntent(owner_id="paper-run", decision_id="opportunity1", symbol="BTCUSDT",
                       side="Buy", quantity=D(5), reference_price=D(100), stop_price=D(98),
                       available_ms=100)


def test_maker_touch_and_same_observation_never_duplicate_a_fill():
    broker = PaperBroker(D(1000))
    identity = broker.submit(intent(), rules())
    assert broker.orders[identity].status == OrderStatus.RESTING
    broker.observe(book(120, "99.90", "100.00"), 121)
    assert broker.orders[identity].filled == 0  # touch cannot prove queue fill
    broker.observe(book(130, "99.90", "99.99"), 131)
    assert broker.orders[identity].filled == D(2)  # 25% of visible 8
    broker.observe(book(130, "99.90", "99.99"), 131)
    assert broker.orders[identity].filled == D(2)
    assert broker.positions["BTCUSDT"].position.protection_healthy
    assert not hasattr(broker, "authenticated_transport")
    state = broker.checkpoint()
    restored = PaperBroker.restore(state)
    assert restored.account({"BTCUSDT": D(99)}) == broker.account({"BTCUSDT": D(99)})
    assert restored.orders[identity].status == OrderStatus.PARTIALLY_FILLED


def test_partial_stop_exit_keeps_residual_managed_and_account_estimated():
    broker = PaperBroker(D(1000))
    broker.submit(intent(), rules())
    broker.observe(book(130, "99.9", "99.99"), 131)
    broker.observe(book(140, "97", "97.01", "4"), 141)
    residual = broker.positions["BTCUSDT"].position
    assert residual.quantity == D(1)
    assert residual.managed and residual.protection_healthy
    trade = [body for kind, body in broker.drain() if kind == "trade"][0]
    assert trade["quantity"] == "1.0"
    assert trade["canonical_live_net"] is None
    assert broker.account({"BTCUSDT": D(97)})["net_completeness"] == "SIMULATED_ESTIMATE"


def test_funding_uses_observed_settlement_and_unknown_is_not_zero():
    broker = PaperBroker(D(1000))
    broker.submit(intent(), rules())
    broker.observe(book(130, "99.9", "99.99"), 131)
    unknown = FundingSnapshot(symbol="BTCUSDT", rate=None, funding_ms=None,
        observed_ms=200, source="missing", status="UNKNOWN")
    broker.apply_funding(unknown)
    broker.apply_funding(unknown)
    # The unknown settlement is journaled once and the account says funding is incomplete.
    rejections = [body for kind, body in broker.drain() if kind == "rejection"]
    assert [row["reason"] for row in rejections] == ["FUNDING_UNKNOWN"]
    assert broker.account({"BTCUSDT": D(100)})["funding_completeness"] == "INCOMPLETE_UNKNOWN_SETTLEMENT"
    assert PaperBroker.restore(broker.checkpoint()).funding_unknown == broker.funding_unknown
    future = FundingSnapshot(symbol="BTCUSDT", rate=D(".001"), funding_ms=210,
        observed_ms=200, source="fixture", status="KNOWN")
    with pytest.raises(ValueError, match="not yet observable"):
        broker.apply_funding(future)
    settled = future.model_copy(update={"observed_ms": 211})
    broker.apply_funding(settled)
    broker.apply_funding(settled)
    assert broker.funding == D("-0.2")


def test_short_maker_fill_funding_and_partial_protected_exit():
    broker = PaperBroker(D(1000))
    short = intent().model_copy(update={"side": "Sell", "stop_price": D(102)})
    broker.submit(short, rules())
    broker.observe(book(130, "100.01", "100.02"), 131)
    held = broker.positions["BTCUSDT"]
    assert held.position.side == "Sell"
    assert held.position.quantity == D(2)
    assert held.position.protection_healthy
    assert D(broker.account({"BTCUSDT": D("100.02")})["unrealized_pnl"]) == D("-0.04")
    broker.apply_funding(FundingSnapshot(symbol="BTCUSDT", rate=D(".001"),
        funding_ms=200, observed_ms=201, source="settled", status="KNOWN"))
    assert broker.funding == D("0.2")  # short receives positive funding
    broker.observe(book(220, "102.99", "103", "4"), 221)
    remaining = broker.positions["BTCUSDT"].position
    assert remaining.quantity == D(1) and remaining.protection_healthy
    trade = [payload for kind, payload in broker.drain() if kind == "trade"][0]
    assert trade["side"] == "Sell"
    assert D(trade["gross_pnl"]) < 0
    assert D(trade["funding"]) > 0
