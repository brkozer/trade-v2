from decimal import Decimal

from tradev2.domain.orders import Fill
from tradev2.domain.positions import Position


def reconcile_exit(position: Position, fills: tuple[Fill, ...], *, owned_client_ids: frozenset[str],
                   observed_quantity: Decimal | None, snapshot_ms: int,
                   complete_snapshot: bool) -> Position:
    """Only exact owned execution coverage plus a fresh position snapshot proves flat."""
    unique: dict[str, Fill] = {}
    for fill in fills:
        if (fill.client_id not in owned_client_ids or fill.symbol != position.symbol
                or fill.side == position.side):
            raise ValueError("foreign exit execution")
        if fill.execution_id in unique and unique[fill.execution_id] != fill:
            raise ValueError("conflicting execution identity")
        unique[fill.execution_id] = fill
    closed = sum((fill.quantity for fill in unique.values()), Decimal(0))
    if closed > position.quantity:
        raise ValueError("oversubscribed exit")
    if not complete_snapshot or observed_quantity is None:
        return position
    if any(fill.source_ms > snapshot_ms for fill in unique.values()):
        return position
    remaining = position.quantity - closed
    if observed_quantity != remaining:
        return position
    return position.model_copy(update={"quantity": remaining, "flat_proven": remaining == 0,
                                      "protected_quantity": min(position.protected_quantity, remaining)})
