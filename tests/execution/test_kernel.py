from decimal import Decimal as D

import pytest

from tradev2.accounting.ledger import Amount, Ledger, LedgerEntry
from tradev2.domain.account import PortfolioRisk
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.orders import Fill, OrderIntent
from tradev2.domain.positions import Position
from tradev2.execution.lifecycle import OrderLifecycle, validate_exit
from tradev2.reconciliation.positions import reconcile_exit
from tradev2.risk.correlation import ReturnObservation, rolling_correlation_bucket
from tradev2.risk.engine import RiskLimits, assess


def intent() -> OrderIntent:
    return OrderIntent(owner_id="paper", decision_id="d1", symbol="ETHUSDT", side="Buy",
                       quantity=D(2), reference_price=D(100), stop_price=D(99), available_ms=1000)


def fill(order: OrderIntent, quantity: str = "1", execution_id: str = "e1") -> Fill:
    return Fill(execution_id=execution_id, client_id=order.client_id, symbol=order.symbol,
                side=order.side, quantity=D(quantity), price=D(100), source="simulation", source_ms=1001)


def test_budget_floor_does_not_inflate_minimum() -> None:
    rules = InstrumentRules(symbol="ETHUSDT", qty_step=D("0.1"), min_qty=D("0.1"),
                            min_notional=D(50), tick_size=D("0.01"))
    portfolio = PortfolioRisk(equity=D(100), available_margin=D(100), open_risk=D(0),
                              pending_risk=D(0), directional_notional=D(0),
                              correlated_notional=D(0), daily_pnl=D(0), reconciled=True,
                              protection_healthy=True)
    limits = RiskLimits(per_trade=D("0.3"), total_open=D(10), directional_notional=D(1000),
                        correlated_notional=D(1000), daily_loss=D(5), equity_floor=D(1))
    assert assess(intent(), rules, portfolio, limits).action == "REJECT"
    resized = assess(intent(), rules.model_copy(update={"min_notional": D(0)}), portfolio, limits)
    assert resized.action == "RESIZE" and resized.quantity == D("0.2")
    assert resized.risk is not None and resized.risk <= limits.per_trade
    assert assess(intent(), rules, portfolio.model_copy(update={"equity": None}), limits).action == "HALT"
    assert assess(intent(), rules, portfolio.model_copy(update={"pending_risk": D(10)}), limits).action == "REJECT"


def test_cancel_unknown_late_fill_duplicate_and_close_time() -> None:
    order = OrderLifecycle(intent())
    with pytest.raises(ValueError, match="unavailable"):
        order.record_fill(fill(intent()).model_copy(update={"source_ms": 1000}))
    order.request_cancel()
    order.confirm_cancel(D(1))
    assert order.unresolved and order.status == "UNRESOLVED"
    assert order.record_fill(fill(intent()))
    assert not order.record_fill(fill(intent()))
    with pytest.raises(ValueError, match="conflicting"):
        order.record_fill(fill(intent(), "0.5"))
    order.confirm_cancel(D(1))
    assert order.status == "CANCELLED"
    order.record_fill(fill(intent(), "1", "late"))
    assert order.status == "FILLED"
    with pytest.raises(ValueError, match="overfill"):
        order.record_fill(fill(intent(), "1", "extra"))


def test_acknowledgement_does_not_fill_and_invalidation_stays_unresolved() -> None:
    order = OrderLifecycle(intent())
    order.submitted()
    order.acknowledge()
    assert order.filled == 0 and order.unresolved
    order.resting()
    order.invalidate(price_left=True)
    assert order.unresolved
    order.request_cancel()
    order.confirm_cancel(D(0))
    assert order.status == "CANCELLED"


def test_owned_exit_needs_exact_coverage_and_fresh_snapshot() -> None:
    position = Position(position_id="p", owner_id="paper", symbol="ETHUSDT", side="Buy",
                        quantity=D(2), entry_price=D(100), protected_quantity=D(2))
    exit_order = intent().model_copy(update={"side": "Sell", "reduce_only": True})
    validate_exit(exit_order, position)
    execution = fill(exit_order, "2")
    params = dict(owned_client_ids=frozenset({exit_order.client_id}), observed_quantity=D(0),
                  snapshot_ms=1002, complete_snapshot=True)
    final = reconcile_exit(position, (execution, execution), **params)
    assert not final.managed and final.flat_proven
    assert reconcile_exit(position, (execution,), **params) == final
    params["complete_snapshot"] = False
    assert reconcile_exit(position, (execution,), **params).managed
    with pytest.raises(ValueError, match="reduce"):
        validate_exit(intent(), position)
    assert position.model_copy(update={"protected_quantity": D(1)}).protection_healthy is False


def test_accounting_unknown_estimate_zero_and_conflicts() -> None:
    zero = Amount(value=D(0), status="KNOWN_ZERO", source="fixture", source_ms=1)
    unknown = Amount(value=None, status="UNKNOWN", source="fixture", source_ms=1)
    gross = Amount(value=D(10), status="KNOWN", source="fixture", source_ms=1)
    entry = LedgerEntry(event_id="e", position_id="p", gross_pnl=gross, entry_fee=zero,
                        exit_fee=unknown, funding=zero)
    assert entry.net_pnl is None and not entry.complete
    known = entry.model_copy(update={"exit_fee": zero})
    assert known.net_pnl == D(10)
    ledger = Ledger()
    assert ledger.post(entry) and not ledger.post(entry)
    with pytest.raises(ValueError, match="conflicting"):
        ledger.post(known)
    estimate = gross.model_copy(update={"status": "ESTIMATED"})
    assert known.model_copy(update={"funding": estimate}).net_pnl is None


def test_rolling_correlation_unknown_is_conservative_and_future_excluded() -> None:
    values = tuple(ReturnObservation(time_ms=i, value=D(i)) for i in range(4))
    opposite = tuple(ReturnObservation(time_ms=i, value=-D(i)) for i in range(4))
    assert rolling_correlation_bucket(values, {"inverse": opposite, "unknown": ()},
                                      as_of_ms=2, window=3) == {"inverse", "unknown"}
