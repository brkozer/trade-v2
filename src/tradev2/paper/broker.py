from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import FundingSnapshot, OrderBookSnapshot
from tradev2.domain.orders import Fill, OrderIntent, OrderStatus
from tradev2.domain.positions import Position
from tradev2.execution.lifecycle import OrderLifecycle
from tradev2.strategies.reference import REFERENCE_PARAMS


@dataclass
class SimPosition:
    position: Position
    stop: Decimal
    target: Decimal
    opened_ms: int
    entry_fee: Decimal
    funding: Decimal = Decimal(0)


class PaperBroker:
    """Conservative quote-cross simulation, not a calibrated exchange queue model.

    No transport is accepted or stored. Maker touch alone never fills; a later quote
    must trade through the limit. Executed size is capped at 25% of visible top depth.
    """

    def __init__(self, equity: Decimal, maker_fee: Decimal = Decimal("0.0004"),
                 taker_fee: Decimal = Decimal("0.0011")) -> None:
        self.initial_equity = equity
        self.cash = equity
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.orders: dict[str, OrderLifecycle] = {}
        self.rules: dict[str, InstrumentRules] = {}
        self.positions: dict[str, SimPosition] = {}
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.funding_seen: set[tuple[str, int]] = set()
        self.realized = Decimal(0)
        self.fees = Decimal(0)
        self.funding = Decimal(0)
        self.last_book_ms: dict[str, int] = {}

    def submit(self, intent: OrderIntent, rules: InstrumentRules) -> str:
        if intent.reduce_only:
            raise ValueError("entry intent cannot be reduce-only; exit uses owned position")
        if ((intent.side == "Buy" and intent.stop_price >= intent.reference_price)
                or (intent.side == "Sell" and intent.stop_price <= intent.reference_price)):
            raise ValueError("protective stop must oppose entry direction")
        if intent.symbol in self.positions or any(
            o.intent.symbol == intent.symbol and o.unresolved for o in self.orders.values()
        ):
            raise ValueError("symbol already has exposure or pending entry")
        if intent.client_id in self.orders:
            if self.orders[intent.client_id].intent != intent:
                raise ValueError("client identity conflict")
            return intent.client_id
        lifecycle = OrderLifecycle(intent)
        self.orders[intent.client_id] = lifecycle
        self.rules[intent.symbol] = rules
        self._order_event(lifecycle)
        lifecycle.submitted()
        self._order_event(lifecycle)
        lifecycle.acknowledge()
        self._order_event(lifecycle)
        lifecycle.resting()
        self._order_event(lifecycle)
        return intent.client_id

    def _order_event(self, order: OrderLifecycle) -> None:
        self.events.append(("order", order.snapshot().model_dump(mode="json") | {
            "symbol": order.intent.symbol, "side": order.intent.side,
            "limit": str(order.intent.reference_price), "simulated": True,
            "available_ms": order.intent.available_ms}))

    def observe(self, book: OrderBookSnapshot, now_ms: int) -> None:
        event_ms = book.exchange_event_ms
        if event_ms is None or event_ms > now_ms or now_ms - event_ms > 15000:
            self.events.append(("rejection", {"symbol": book.symbol, "reason": "STALE_BOOK"}))
            return
        if book.spread_bps is None:
            return
        if event_ms <= self.last_book_ms.get(book.symbol, -1):
            return
        self.last_book_ms[book.symbol] = event_ms
        for order in self.orders.values():
            intent = order.intent
            if intent.symbol != book.symbol or not order.unresolved:
                continue
            existing_position = self.positions.get(book.symbol)
            if existing_position is not None and (
                (existing_position.position.side == "Buy" and book.bids[0][0] <= existing_position.stop)
                or (existing_position.position.side == "Sell" and book.asks[0][0] >= existing_position.stop)
            ):
                # An adverse quote makes further simulated entry unsafe. The real venue
                # may still report a late fill; this simulator does not claim certainty.
                order.request_cancel()
                order.confirm_cancel(order.filled)
                self._order_event(order)
                continue
            if now_ms - intent.available_ms > REFERENCE_PARAMS.maker_wait_ms:
                order.request_cancel()
                order.confirm_cancel(order.filled)
                self._order_event(order)
                continue
            # Strict later availability and through-price avoid guaranteed maker touches.
            through = (book.asks[0][0] < intent.reference_price if intent.side == "Buy"
                       else book.bids[0][0] > intent.reference_price)
            if event_ms <= intent.available_ms or not through:
                continue
            rules = self.rules[book.symbol]
            opposite_depth = book.asks[0][1] if intent.side == "Buy" else book.bids[0][1]
            capacity = (opposite_depth * Decimal("0.25") / rules.qty_step).to_integral_value(
                rounding=ROUND_DOWN) * rules.qty_step
            quantity = min(intent.quantity - order.filled, capacity)
            if quantity <= 0:
                continue
            fee = quantity * intent.reference_price * self.maker_fee
            fill = Fill(execution_id=f"{intent.client_id}-{event_ms}-{order.filled}",
                        client_id=intent.client_id, symbol=book.symbol, side=intent.side,
                        quantity=quantity, price=intent.reference_price, fee=fee,
                        source="simulated_quote_through", source_ms=event_ms)
            if not order.record_fill(fill):
                continue
            self.cash -= fee
            self.fees += fee
            existing = self.positions.get(book.symbol)
            total = quantity + (existing.position.quantity if existing else Decimal(0))
            position = Position(position_id=intent.client_id, owner_id=intent.owner_id,
                                symbol=book.symbol, side=intent.side, quantity=total,
                                entry_price=intent.reference_price, protected_quantity=total)
            target = intent.reference_price + (
                intent.reference_price - intent.stop_price) * Decimal(str(REFERENCE_PARAMS.target_r))
            self.positions[book.symbol] = SimPosition(position, intent.stop_price, target,
                existing.opened_ms if existing else event_ms,
                (existing.entry_fee if existing else Decimal(0)) + fee,
                existing.funding if existing else Decimal(0))
            self.events.append(("fill", fill.model_dump(mode="json") | {"simulated": True}))
            self._order_event(order)
            self._position_event(self.positions[book.symbol])
        current = self.positions.get(book.symbol)
        if current is not None:
            mark = book.bids[0][0] if current.position.side == "Buy" else book.asks[0][0]
            stop_hit = mark <= current.stop if current.position.side == "Buy" else mark >= current.stop
            target_hit = mark >= current.target if current.position.side == "Buy" else mark <= current.target
            if stop_hit:
                self.exit(book, now_ms, "STOP")
            elif target_hit:
                self.exit(book, now_ms, "TARGET")

    def _position_event(self, item: SimPosition) -> None:
        self.events.append(("position", item.position.model_dump(mode="json") | {
            "stop": str(item.stop), "target": str(item.target), "opened_ms": item.opened_ms,
            "protection": "SIMULATED_PROTECTED" if item.position.protection_healthy else "UNSAFE",
            "simulated": True}))

    def exit(self, book: OrderBookSnapshot, now_ms: int, reason: str) -> None:
        item = self.positions.get(book.symbol)
        if item is None or book.spread_bps is None or book.exchange_event_ms is None:
            return
        if not item.opened_ms < book.exchange_event_ms <= now_ms:
            return
        if now_ms - book.exchange_event_ms > 15000:
            return
        rules = self.rules[book.symbol]
        opposite_depth = book.bids[0][1] if item.position.side == "Buy" else book.asks[0][1]
        capacity = (opposite_depth * Decimal("0.25") / rules.qty_step).to_integral_value(
            rounding=ROUND_DOWN) * rules.qty_step
        quantity = min(item.position.quantity, capacity)
        if quantity <= 0:
            self.events.append(("rejection", {"symbol": book.symbol,
                                               "reason": "EXIT_UNRESOLVED_DEPTH"}))
            return
        # Any residual entry is cancelled before reducing this simulated position.
        order = self.orders[item.position.position_id]
        order.request_cancel()
        order.confirm_cancel(order.filled)
        direction = Decimal(1) if item.position.side == "Buy" else Decimal(-1)
        mark = book.bids[0][0] if direction == 1 else book.asks[0][0]
        price = mark * (Decimal(1) - direction * Decimal("0.0002"))  # 2bps adverse exit
        gross = direction * quantity * (price - item.position.entry_price)
        exit_fee = quantity * price * self.taker_fee
        fraction = quantity / item.position.quantity
        entry_fee = item.entry_fee * fraction
        funding = item.funding * fraction
        net = gross - entry_fee - exit_fee + funding
        self.cash += gross - exit_fee
        self.realized += net
        self.fees += exit_fee
        residual = item.position.quantity - quantity
        self.events.append(("trade", {"position_id": item.position.position_id,
            "symbol": book.symbol, "side": item.position.side, "quantity": str(quantity),
            "entry_price": str(item.position.entry_price), "exit_price": str(price),
            "gross_pnl": str(gross), "fees": str(entry_fee + exit_fee),
            "funding": str(funding), "net_pnl": str(net), "reason": reason,
            "opened_ms": item.opened_ms, "closed_ms": book.exchange_event_ms,
            "canonical_live_net": None, "net_completeness": "SIMULATED_ESTIMATE",
            "simulated": True}))
        item.position = item.position.model_copy(update={"quantity": residual,
            "protected_quantity": residual, "flat_proven": residual == 0})
        item.entry_fee -= entry_fee
        item.funding -= funding
        self._position_event(item)
        if residual == 0:
            del self.positions[book.symbol]

    def apply_funding(self, snapshot: FundingSnapshot) -> None:
        if snapshot.funding_ms is None or snapshot.rate is None or snapshot.status == "UNKNOWN":
            return
        if snapshot.observed_ms is None or snapshot.funding_ms > snapshot.observed_ms:
            raise ValueError("funding event is not yet observable")
        key = (snapshot.symbol, snapshot.funding_ms)
        if key in self.funding_seen:
            return
        self.funding_seen.add(key)
        item = self.positions.get(snapshot.symbol)
        if item is None or snapshot.funding_ms <= item.opened_ms:
            return
        # Entry notional proxy is disclosed; historical mark-price not available here.
        direction = Decimal(1) if item.position.side == "Buy" else Decimal(-1)
        amount = -(direction * item.position.quantity * item.position.entry_price * snapshot.rate)
        item.funding += amount
        self.cash += amount
        self.funding += amount
        self.events.append(("funding", {"symbol": snapshot.symbol, "amount": str(amount),
            "source": snapshot.source, "source_ms": snapshot.funding_ms,
            "status": "ESTIMATED_ENTRY_NOTIONAL", "simulated": True}))

    def account(self, marks: dict[str, Decimal]) -> dict[str, Any]:
        complete = all(symbol in marks for symbol in self.positions)
        unrealized = sum(((marks[symbol] - item.position.entry_price) * item.position.quantity
                           * (Decimal(1) if item.position.side == "Buy" else Decimal(-1))
                           for symbol, item in self.positions.items() if symbol in marks), Decimal(0))
        return {"equity": str(self.cash + unrealized) if complete else None,
                "start_equity": str(self.initial_equity), "cash": str(self.cash),
                "equity_delta": str(self.cash + unrealized - self.initial_equity) if complete else None,
                "realized_pnl": str(self.realized), "unrealized_pnl": str(unrealized) if complete else None,
                "known_fees": str(self.fees), "funding": str(self.funding),
                "open_risk": str(sum((abs(item.position.entry_price-item.stop)*item.position.quantity
                                      for item in self.positions.values()), Decimal(0))),
                "net_completeness": "SIMULATED_ESTIMATE", "source": "paper_broker",
                "simulated": True}

    def drain(self) -> list[tuple[str, dict[str, Any]]]:
        events, self.events = self.events, []
        return events

    def checkpoint(self) -> dict[str, Any]:
        return {"schema_version": 1, "initial_equity": str(self.initial_equity),
            "cash": str(self.cash), "maker_fee": str(self.maker_fee), "taker_fee": str(self.taker_fee),
            "realized": str(self.realized), "fees": str(self.fees), "funding": str(self.funding),
            "funding_seen": sorted(self.funding_seen), "last_book_ms": self.last_book_ms,
            "rules": {s: r.model_dump(mode="json") for s, r in self.rules.items()},
            "orders": {key: {"intent": o.intent.model_dump(mode="json"),
                "fills": [f.model_dump(mode="json") for f in o.fills.values()], "status": o.status.value}
                for key, o in self.orders.items()},
            "positions": {s: {"position": p.position.model_dump(mode="json"),
                "stop": str(p.stop), "target": str(p.target), "opened_ms": p.opened_ms,
                "entry_fee": str(p.entry_fee), "funding": str(p.funding)}
                for s, p in self.positions.items()}}

    @classmethod
    def restore(cls, state: dict[str, Any]) -> "PaperBroker":
        if state["schema_version"] != 1:
            raise ValueError("unsupported simulation checkpoint schema")
        result = cls(Decimal(state["initial_equity"]), Decimal(state["maker_fee"]),
                     Decimal(state["taker_fee"]))
        for field in ("cash", "realized", "fees", "funding"):
            setattr(result, field, Decimal(state[field]))
        result.funding_seen = {(str(s), int(t)) for s, t in state["funding_seen"]}
        result.last_book_ms = {s: int(t) for s, t in state["last_book_ms"].items()}
        result.rules = {s: InstrumentRules.model_validate(r) for s, r in state["rules"].items()}
        for key, raw in state["orders"].items():
            order = OrderLifecycle(OrderIntent.model_validate(raw["intent"]))
            if key != order.intent.client_id:
                raise ValueError("checkpoint order identity mismatch")
            for fill in raw["fills"]:
                order.record_fill(Fill.model_validate(fill))
            order.status = OrderStatus(raw["status"])
            result.orders[key] = order
        for symbol, raw in state["positions"].items():
            position = Position.model_validate(raw["position"])
            if not position.protection_healthy or position.position_id not in result.orders:
                raise ValueError("checkpoint position lacks proven simulated protection/ownership")
            result.positions[symbol] = SimPosition(position, Decimal(raw["stop"]),
                Decimal(raw["target"]), int(raw["opened_ms"]),
                Decimal(raw["entry_fee"]), Decimal(raw["funding"]))
        return result
