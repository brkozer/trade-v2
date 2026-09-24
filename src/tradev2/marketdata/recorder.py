import json
import time
import uuid
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.domain.market import PublicTrade
from tradev2.evidence.journal import Journal
from tradev2.marketdata.integrity import OrderBook
from tradev2.venues.bybit_linear.endpoints import PUBLIC_WEBSOCKET


def normalize_message(message: dict[str, Any], books: dict[str, OrderBook],
                      ingested_ms: int) -> tuple[dict[str, Any], int | None]:
    """Retain raw evidence and a typed, point-in-time query surface."""
    topic = str(message.get("topic", ""))
    source_ms = message.get("ts")
    if source_ms is not None and (not isinstance(source_ms, int) or source_ms < 0):
        raise ValueError("invalid exchange event timestamp")
    payload: dict[str, Any] = {"schema_version": 1, "venue": "bybit_linear",
                               "topic": topic, "ingested_ms": ingested_ms,
                               "exchange_event_ms": source_ms, "raw": message}
    if topic.startswith("orderbook."):
        data = message.get("data")
        if not isinstance(data, dict) or data.get("s") not in books:
            raise ValueError("unsubscribed or invalid orderbook symbol")
        book = books[data["s"]].apply(message, ingested_ms)
        bid = book.bids[0][0] if book.bids else None
        ask = book.asks[0][0] if book.asks else None
        payload.update({"kind": "orderbook", "symbol": book.symbol,
                        "integrity": "VALID" if book.spread_bps is not None else "INCOMPLETE",
                        "update_id": book.update_id, "seq": book.exchange_sequence,
                        "cts": book.matching_engine_ms, "best_bid": str(bid) if bid is not None else None,
                        "best_ask": str(ask) if ask is not None else None,
                        "spread_bps": str(book.spread_bps) if book.spread_bps is not None else None,
                        "bid_depth_50": str(sum((size for _, size in book.bids[:50]))),
                        "ask_depth_50": str(sum((size for _, size in book.asks[:50]))),
                        "bid_levels": len(book.bids), "ask_levels": len(book.asks)})
    elif topic.startswith("publicTrade."):
        raw_trades = message.get("data")
        if not isinstance(raw_trades, list) or not raw_trades:
            raise ValueError("empty public-trade batch")
        trades: list[dict[str, Any]] = []
        for raw in raw_trades:
            if not isinstance(raw, dict) or raw.get("s") not in books:
                raise ValueError("unsubscribed or invalid trade symbol")
            trade = PublicTrade(symbol=raw["s"], trade_id=str(raw["i"]),
                                side=raw["S"], price=raw["p"], quantity=raw["v"],
                                exchange_event_ms=int(raw["T"]), ingested_ms=ingested_ms)
            trades.append(trade.model_dump(mode="json"))
        payload.update({"kind": "public_trade", "symbol": trades[0]["symbol"],
                        "trades": trades, "integrity": "VALID"})
    else:
        raise ValueError("unexpected public subscription topic")
    return payload, source_ms


def record_public(journal: Journal, run_id: str, symbols: tuple[str, ...],
                  duration_seconds: float = 30) -> dict[str, int]:
    if not symbols or len(symbols) > 10 or not 0 < duration_seconds <= 3600:
        raise ValueError("bounded recorder needs 1..10 symbols and duration <=3600 seconds")
    deadline = time.monotonic() + duration_seconds
    counts = {"messages": 0, "books": 0, "trades": 0,
              "reconnects": 0, "invalid_books": 0}
    books = {symbol: OrderBook(symbol) for symbol in symbols}
    while time.monotonic() < deadline:
        try:
            with connect(PUBLIC_WEBSOCKET, open_timeout=10, close_timeout=2) as websocket:
                websocket.send(json.dumps({"op": "subscribe", "args": [
                    topic for symbol in symbols
                    for topic in (f"orderbook.50.{symbol}", f"publicTrade.{symbol}")]}))
                for book in books.values():
                    book.invalidate()
                while time.monotonic() < deadline:
                    try:
                        raw = websocket.recv(timeout=min(5, max(.01, deadline-time.monotonic())))
                    except TimeoutError:
                        websocket.send('{"op":"ping"}')
                        continue
                    message: dict[str, Any] = json.loads(raw)
                    if "topic" not in message:
                        continue
                    now = time.time_ns() // 1_000_000
                    try:
                        payload, source_ms = normalize_message(message, books, now)
                    except (ValueError, KeyError, TypeError) as exc:
                        counts["invalid_books"] += 1
                        journal.append(EvidenceEnvelope(
                            event_id=uuid.uuid4().hex, run_id=run_id, kind="source_failure",
                            recorded_ms=now, source="bybit_public_websocket",
                            payload={"status": "RESEED_REQUIRED", "reason": type(exc).__name__,
                                     "topic": message.get("topic")}))
                        raise ConnectionError("public message integrity failure") from exc
                    journal.append(EvidenceEnvelope(
                        event_id=uuid.uuid4().hex, run_id=run_id, kind="microstructure",
                        recorded_ms=now, source_ms=source_ms,
                        source="bybit_public_websocket", payload=payload))
                    counts["messages"] += 1
                    counts["books"] += payload["kind"] == "orderbook"
                    counts["trades"] += len(payload.get("trades", []))
        except (OSError, TimeoutError, ConnectionError, ConnectionClosed) as exc:
            now = time.time_ns() // 1_000_000
            journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex, run_id=run_id,
                kind="source_failure", recorded_ms=now, source="recorder",
                payload={"reason": type(exc).__name__, "status": "SOURCE_UNKNOWN"}))
            counts["reconnects"] += 1
            if counts["reconnects"] >= 3:
                raise RuntimeError("recorder retry budget exhausted") from exc
    return counts
