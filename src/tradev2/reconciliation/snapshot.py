"""Fail-closed comparison of journal and exchange observations at startup.

This is a pure verifier: a transport acknowledgement is deliberately absent
from the proof inputs. Callers must obtain complete, dated exchange snapshots.
"""

from decimal import Decimal

from pydantic import Field

from tradev2.domain.base import FrozenModel
from tradev2.domain.orders import Fill, OrderSnapshot
from tradev2.domain.positions import Position


class AccountObservation(FrozenModel):
    account_id: str = Field(min_length=1)
    equity: Decimal | None
    available_balance: Decimal | None
    closed_pnl: Decimal | None
    source_ms: int = Field(ge=0)


class ReconciliationInput(FrozenModel):
    owner_id: str = Field(min_length=1)
    expected_account_id: str = Field(min_length=1)
    journal_orders: tuple[OrderSnapshot, ...]
    exchange_orders: tuple[OrderSnapshot, ...]
    journal_fills: tuple[Fill, ...]
    exchange_fills: tuple[Fill, ...]
    journal_positions: tuple[Position, ...]
    exchange_positions: tuple[Position, ...]
    journal_account: AccountObservation
    exchange_account: AccountObservation
    complete_orders: bool = False
    complete_fills: bool = False
    complete_positions: bool = False
    complete_closed_pnl: bool = False
    snapshot_ms: int = Field(ge=0)


class ReconciliationResult(FrozenModel):
    status: str
    missing: tuple[str, ...]

    @property
    def entry_permitted(self) -> bool:
        return self.status == "RECONCILED"


def reconcile_snapshot(value: ReconciliationInput) -> ReconciliationResult:
    missing: set[str] = set()
    if value.exchange_account.account_id != value.expected_account_id or (
        value.journal_account.account_id != value.expected_account_id
    ):
        missing.add("ACCOUNT_IDENTITY")
    if value.exchange_account.source_ms > value.snapshot_ms or (
        value.journal_account.source_ms > value.snapshot_ms
    ):
        missing.add("TIMESTAMP_ORDER")
    for name in ("orders", "fills", "positions", "closed_pnl"):
        if not getattr(value, f"complete_{name}"):
            missing.add(f"INCOMPLETE_{name.upper()}")
    if (value.exchange_account.equity is None or value.exchange_account.available_balance is None
            or value.journal_account.equity is None or value.journal_account.available_balance is None):
        missing.add("ACCOUNT_UNKNOWN")
    elif (value.exchange_account.equity != value.journal_account.equity
          or value.exchange_account.available_balance != value.journal_account.available_balance):
        missing.add("ACCOUNT_MISMATCH")
    if value.exchange_account.closed_pnl is None or value.journal_account.closed_pnl is None:
        missing.add("CLOSED_PNL_UNKNOWN")
    elif value.exchange_account.closed_pnl != value.journal_account.closed_pnl:
        missing.add("CLOSED_PNL_MISMATCH")

    journal_orders = _unique(value.journal_orders, "client_id", missing, "JOURNAL_ORDER_DUPLICATE")
    exchange_orders = _unique(value.exchange_orders, "client_id", missing, "EXCHANGE_ORDER_DUPLICATE")
    for item in (*value.journal_orders, *value.exchange_orders):
        if item.owner_id != value.owner_id:
            missing.add("FOREIGN_ORDER")
    if journal_orders != exchange_orders:
        missing.add("ORDER_MISMATCH")
    journal_fills = _unique(value.journal_fills, "execution_id", missing, "JOURNAL_FILL_DUPLICATE")
    exchange_fills = _unique(value.exchange_fills, "execution_id", missing, "EXCHANGE_FILL_DUPLICATE")
    if journal_fills != exchange_fills:
        missing.add("FILL_MISMATCH")
    for fill in (*value.journal_fills, *value.exchange_fills):
        if fill.client_id not in journal_orders or fill.source_ms > value.snapshot_ms:
            missing.add("FILL_OWNERSHIP_OR_TIME")
    journal_positions = _unique(value.journal_positions, "position_id", missing, "JOURNAL_POSITION_DUPLICATE")
    exchange_positions = _unique(value.exchange_positions, "position_id", missing, "EXCHANGE_POSITION_DUPLICATE")
    for position in (*value.journal_positions, *value.exchange_positions):
        if position.owner_id != value.owner_id:
            missing.add("FOREIGN_POSITION")
        if position.quantity > 0 and not position.protection_healthy:
            missing.add("PROTECTION_UNVERIFIED")
    if journal_positions != exchange_positions:
        missing.add("POSITION_MISMATCH")
    reasons = tuple(sorted(missing))
    return ReconciliationResult(status="ENTRY_BLOCKED" if reasons else "RECONCILED", missing=reasons)


def _unique(items: tuple[object, ...], attribute: str,
            missing: set[str], reason: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        identity = str(getattr(item, attribute))
        if identity in result:
            missing.add(reason)
        result[identity] = item
    return result
