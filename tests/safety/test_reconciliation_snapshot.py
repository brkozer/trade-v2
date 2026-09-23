from decimal import Decimal

import httpx
import pytest

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.orders import Fill, OrderSnapshot, OrderStatus
from tradev2.domain.positions import Position
from tradev2.reconciliation.snapshot import (
    AccountObservation,
    ReconciliationInput,
    reconcile_snapshot,
)
from tradev2.runtime.startup import REQUIRED
from tradev2.testnet.transport import TestnetCredentials as Credentials
from tradev2.testnet.transport import TestnetLinear as LinearTransport


def sample() -> ReconciliationInput:
    order = OrderSnapshot(client_id="tv2-owned", owner_id="run", requested=Decimal("2"),
                          filled=Decimal("1"), status=OrderStatus.PARTIALLY_FILLED)
    fill = Fill(execution_id="e1", client_id="tv2-owned", symbol="BTCUSDT", side="Buy",
                quantity=Decimal("1"), price=Decimal("100"), fee=Decimal("0.1"),
                source="exchange", source_ms=10)
    position = Position(position_id="p1", owner_id="run", symbol="BTCUSDT", side="Buy",
                        quantity=Decimal("1"), entry_price=Decimal("100"),
                        protected_quantity=Decimal("1"))
    account = AccountObservation(account_id="dedicated-testnet", equity=Decimal("1000"),
                                 available_balance=Decimal("900"), closed_pnl=Decimal("0"),
                                 source_ms=11)
    return ReconciliationInput(owner_id="run", expected_account_id="dedicated-testnet",
                               journal_orders=(order,), exchange_orders=(order,),
                               journal_fills=(fill,), exchange_fills=(fill,),
                               journal_positions=(position,), exchange_positions=(position,),
                               journal_account=account, exchange_account=account,
                               complete_orders=True, complete_fills=True,
                               complete_positions=True, complete_closed_pnl=True,
                               snapshot_ms=12)


def test_exact_complete_snapshot_reconciles() -> None:
    assert reconcile_snapshot(sample()).entry_permitted


def test_unknown_is_not_zero_and_duplicate_fill_blocks() -> None:
    initial = sample()
    unknown = initial.model_copy(update={
        "exchange_account": initial.exchange_account.model_copy(update={"closed_pnl": None}),
        "exchange_fills": initial.exchange_fills * 2,
    })
    result = reconcile_snapshot(unknown)
    assert not result.entry_permitted
    assert "CLOSED_PNL_UNKNOWN" in result.missing
    assert "EXCHANGE_FILL_DUPLICATE" in result.missing


def test_stale_incomplete_or_unprotected_blocks() -> None:
    initial = sample()
    position = initial.exchange_positions[0].model_copy(update={"protected_quantity": Decimal(0)})
    changed = initial.model_copy(update={"exchange_positions": (position,),
                                         "complete_orders": False, "snapshot_ms": 9})
    result = reconcile_snapshot(changed)
    assert not result.entry_permitted
    assert "PROTECTION_UNVERIFIED" in result.missing
    assert "INCOMPLETE_ORDERS" in result.missing
    assert "FILL_OWNERSHIP_OR_TIME" in result.missing


def test_testnet_stop_needs_owned_position_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEV2_TESTNET_ENABLE", "1")
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"retCode": 0, "result": {"orderId": "ack"}})

    with LinearTransport(RuntimeConfig(mode=Mode.TESTNET, testnet_authorized=True),
                       credentials=Credentials("fake", "fake"),
                       transport=httpx.MockTransport(handler)) as transport:
        transport.authorize_entry({name: True for name in REQUIRED})
        proof = sample()
        with pytest.raises(PermissionError, match="owned position"):
            transport.set_stop("ETHUSDT", Decimal("90"), proof)
        assert not observed
        unsafe = proof.model_copy(update={"complete_fills": False})
        with pytest.raises(PermissionError, match="reconciliation"):
            transport.set_stop("BTCUSDT", Decimal("90"), unsafe)
        assert not observed
        result = transport.set_stop("BTCUSDT", Decimal("90"), proof)
        assert result["status"] == "PROTECTION_ACK_UNVERIFIED"
        assert len(observed) == 1
