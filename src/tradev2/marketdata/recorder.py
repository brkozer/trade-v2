import json
import time
import uuid
from typing import Any

from websockets.sync.client import connect

from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.evidence.journal import Journal
from tradev2.marketdata.integrity import OrderBook
from tradev2.venues.bybit_linear.endpoints import PUBLIC_WEBSOCKET


def record_public(journal: Journal, run_id: str, symbols: tuple[str, ...],
                  duration_seconds: float = 30) -> dict[str, int]:
    if not symbols or len(symbols) > 10 or not 0 < duration_seconds <= 3600:
        raise ValueError("bounded recorder needs 1..10 symbols and duration <=3600 seconds")
    deadline = time.monotonic() + duration_seconds
    counts = {"messages": 0, "reconnects": 0, "invalid_books": 0}
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
                    payload: dict[str, Any] = {"venue": "bybit_linear", "raw": message}
                    if message["topic"].startswith("orderbook."):
                        try:
                            book_snapshot = books[message["data"]["s"]].apply(message, now)
                            payload["integrity"] = "VALID" if book_snapshot.spread_bps is not None else "INCOMPLETE"
                        except ValueError:
                            counts["invalid_books"] += 1
                            payload["integrity"] = "RESEED_REQUIRED"
                            journal.append(EvidenceEnvelope(
                                event_id=uuid.uuid4().hex, run_id=run_id, kind="microstructure",
                                recorded_ms=now, source_ms=message.get("ts"),
                                source="bybit_public_websocket", payload=payload))
                            raise ConnectionError("book integrity failure") from None
                    journal.append(EvidenceEnvelope(
                        event_id=uuid.uuid4().hex, run_id=run_id, kind="microstructure",
                        recorded_ms=now, source_ms=message.get("ts"),
                        source="bybit_public_websocket", payload=payload))
                    counts["messages"] += 1
        except (OSError, TimeoutError, ConnectionError) as exc:
            now = time.time_ns() // 1_000_000
            journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex, run_id=run_id,
                kind="source_failure", recorded_ms=now, source="recorder",
                payload={"reason": type(exc).__name__, "status": "SOURCE_UNKNOWN"}))
            counts["reconnects"] += 1
            if counts["reconnects"] >= 3:
                raise RuntimeError("recorder retry budget exhausted") from exc
    return counts

