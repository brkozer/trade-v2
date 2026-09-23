from decimal import Decimal

from tradev2.domain.orders import Fill, OrderIntent, OrderSnapshot, OrderStatus
from tradev2.domain.positions import Position


class OrderLifecycle:
    """In-memory order reducer. Transport acknowledgements never prove fills or flatness."""

    def __init__(self, intent: OrderIntent) -> None:
        self.intent = intent
        self.fills: dict[str, Fill] = {}
        self.status = OrderStatus.CREATED

    @property
    def filled(self) -> Decimal:
        return sum((fill.quantity for fill in self.fills.values()), Decimal(0))

    @property
    def unresolved(self) -> bool:
        return self.status not in {OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.REJECTED, OrderStatus.UNPLACED, OrderStatus.EXCHANGE_ENDED}

    def submitted(self) -> None:
        if self.status != OrderStatus.CREATED:
            raise ValueError("submission requires created order")
        self.status = OrderStatus.SUBMITTED

    def acknowledge(self) -> None:
        if self.status != OrderStatus.SUBMITTED:
            raise ValueError("acknowledgement requires submitted order")
        self.status = OrderStatus.ACKNOWLEDGED

    def resting(self) -> None:
        if self.status != OrderStatus.ACKNOWLEDGED:
            raise ValueError("resting requires acknowledged order")
        self.status = OrderStatus.RESTING

    def invalidate(self, *, price_left: bool = False) -> None:
        self.status = OrderStatus.PRICE_LEFT if price_left else OrderStatus.SIGNAL_INVALIDATED

    def reject(self, *, exchange_ended: bool = False) -> None:
        if self.filled:
            raise ValueError("filled exposure cannot be rejected away")
        self.status = OrderStatus.EXCHANGE_ENDED if exchange_ended else OrderStatus.REJECTED

    def unplaced(self) -> None:
        if self.status != OrderStatus.CREATED:
            raise ValueError("submitted order cannot be declared unplaced")
        self.status = OrderStatus.UNPLACED

    def record_fill(self, fill: Fill) -> bool:
        old = self.fills.get(fill.execution_id)
        if old is not None:
            if old != fill:
                raise ValueError("conflicting execution replay")
            return False
        if (fill.client_id != self.intent.client_id or fill.symbol != self.intent.symbol
                or fill.side != self.intent.side):
            raise ValueError("foreign fill")
        if fill.source_ms <= self.intent.available_ms:
            raise ValueError("fill unavailable at decision time")
        if self.filled + fill.quantity > self.intent.quantity:
            raise ValueError("overfill")
        self.fills[fill.execution_id] = fill
        # Late fills after cancel still belong to this order and require protection.
        self.status = OrderStatus.FILLED if self.filled == self.intent.quantity else OrderStatus.PARTIALLY_FILLED
        return True

    def request_cancel(self) -> None:
        if self.status != "FILLED":
            self.status = OrderStatus.CANCEL_REQUESTED

    def confirm_cancel(self, cumulative_filled: Decimal) -> None:
        if cumulative_filled != self.filled:
            self.status = OrderStatus.UNRESOLVED
            return
        self.status = OrderStatus.FILLED if self.filled == self.intent.quantity else OrderStatus.CANCELLED

    def mark_unknown(self) -> None:
        self.status = OrderStatus.UNRESOLVED

    def snapshot(self) -> OrderSnapshot:
        return OrderSnapshot.model_validate(dict(client_id=self.intent.client_id,
            owner_id=self.intent.owner_id, requested=self.intent.quantity,
            filled=self.filled, status=self.status))


def validate_exit(intent: OrderIntent, position: Position) -> None:
    if (not intent.reduce_only or intent.owner_id != position.owner_id
            or intent.symbol != position.symbol or intent.side == position.side
            or intent.quantity > position.quantity or position.quantity <= 0):
        raise ValueError("exit must reduce owned position without reversal")
