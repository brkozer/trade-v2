from decimal import Decimal
from typing import Any

from tradev2.domain.market import Candle, OrderBookSnapshot


def confirmed_window(candles: list[Candle], decision_ms: int, minimum: int = 64) -> list[Candle]:
    result = [c for c in candles if c.confirmed and c.close_ms <= decision_ms]
    if len(result) < minimum:
        raise ValueError("INSUFFICIENT_CANDLES")
    result = result[-minimum:]
    for previous, current in zip(result, result[1:], strict=False):
        if (current.symbol != previous.symbol or current.interval_ms != previous.interval_ms
                or current.start_ms != previous.close_ms):
            raise ValueError("CANDLE_GAP_OR_DUPLICATE")
    return result


class OrderBook:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.sequence: int | None = None
        self.seeded = False

    def invalidate(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.sequence = None
        self.seeded = False

    def apply(self, message: dict[str, Any], ingested_ms: int) -> OrderBookSnapshot:
        data = message["data"]
        if data["s"] != self.symbol:
            self.invalidate()
            raise ValueError("book symbol mismatch")
        snapshot = message["type"] == "snapshot"
        if message["type"] not in {"snapshot", "delta"}:
            self.invalidate()
            raise ValueError("unknown orderbook message type")
        if snapshot:
            self.invalidate()
            self.seeded = True
        elif not self.seeded or data.get("u") == 1:
            self.invalidate()
            raise ValueError("book requires snapshot reseed")
        sequence = data.get("seq")
        if self.sequence is not None and sequence is not None and sequence <= self.sequence:
            self.invalidate()
            raise ValueError("out-of-order delta; reseed required")
        try:
            for key, levels in (("b", self.bids), ("a", self.asks)):
                for raw_price, raw_qty in data.get(key, []):
                    price, quantity = Decimal(raw_price), Decimal(raw_qty)
                    if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity < 0:
                        raise ValueError("invalid book level")
                    if quantity == 0:
                        levels.pop(price, None)
                    else:
                        levels[price] = quantity
            if self.bids and self.asks and max(self.bids) >= min(self.asks):
                raise ValueError("crossed book")
        except (ValueError, ArithmeticError):
            self.invalidate()
            raise
        self.sequence = sequence
        # u/seq are retained; Bybit does not promise contiguous +1 update IDs.
        return OrderBookSnapshot(
            symbol=self.symbol, bids=tuple(sorted(self.bids.items(), reverse=True)),
            asks=tuple(sorted(self.asks.items())), update_id=data.get("u"),
            exchange_sequence=sequence, exchange_event_ms=message.get("ts"),
            matching_engine_ms=message.get("cts"), ingested_ms=ingested_ms)

