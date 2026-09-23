import time
from decimal import Decimal
from typing import Any

import httpx

from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import Candle, FundingSnapshot, OrderBookSnapshot
from tradev2.venues.bybit_linear.endpoints import PUBLIC_PATHS, PUBLIC_REST


class PublicBybit:
    """GET-only, public-path-only client. No secrets, signing, or order methods."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=PUBLIC_REST, timeout=15, transport=transport,
                                    follow_redirects=False, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: dict[str, str | int] | None = None) -> dict[str, Any]:
        if path not in PUBLIC_PATHS:
            raise PermissionError("only built-in public market-data paths are allowed")
        for attempt in range(3):
            response = self._client.get(path, params=params)
            if response.status_code == 429 and attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            if body.get("retCode") != 0:
                raise ValueError(f"Bybit public request rejected: {body.get('retCode')}")
            return body
        raise RuntimeError("public retry budget exhausted")

    def server_time(self) -> int:
        body = self.get("/v5/market/time")
        return int(body["time"])

    def candles(self, symbol: str, *, interval_minutes: int = 15, limit: int = 200,
                end_ms: int | None = None) -> list[Candle]:
        params: dict[str, str | int] = {"category": "linear", "symbol": symbol,
                                      "interval": str(interval_minutes), "limit": limit}
        if end_ms is not None:
            params["end"] = end_ms
        body = self.get("/v5/market/kline", params)
        now = int(body["time"])
        interval = interval_minutes * 60000
        result = [Candle(symbol=symbol, start_ms=int(row[0]), interval_ms=interval,
                         open=Decimal(row[1]), high=Decimal(row[2]), low=Decimal(row[3]),
                         close=Decimal(row[4]), volume=Decimal(row[5]),
                         confirmed=int(row[0]) + interval <= now, ingested_ms=now)
                  for row in body["result"]["list"]]
        return sorted(result, key=lambda candle: candle.start_ms)

    def instruments(self, symbol: str | None = None) -> dict[str, InstrumentRules]:
        params: dict[str, str | int] = {"category": "linear", "limit": 1000}
        if symbol is not None:
            params["symbol"] = symbol
        result: dict[str, InstrumentRules] = {}
        seen: set[str] = set()
        while True:
            body = self.get("/v5/market/instruments-info", params)
            for item in body["result"]["list"]:
                if item["status"] != "Trading" or item["settleCoin"] != "USDT":
                    continue
                lot = item["lotSizeFilter"]
                result[item["symbol"]] = InstrumentRules(
                    symbol=item["symbol"], qty_step=Decimal(lot["qtyStep"]),
                    min_qty=Decimal(lot["minOrderQty"]),
                    min_notional=Decimal(lot["minNotionalValue"]),
                    tick_size=Decimal(item["priceFilter"]["tickSize"]),
                    max_qty=Decimal(lot["maxOrderQty"]), observed_ms=int(body["time"]),
                    source="bybit_public_instruments")
            cursor = body["result"].get("nextPageCursor", "")
            if not cursor:
                return result
            if cursor in seen:
                raise ValueError("instrument pagination did not advance")
            seen.add(cursor)
            params["cursor"] = cursor

    def orderbook(self, symbol: str) -> OrderBookSnapshot:
        body = self.get("/v5/market/orderbook", {"category": "linear", "symbol": symbol,
                                               "limit": 50})
        book = body["result"]
        return OrderBookSnapshot(
            symbol=symbol, bids=tuple((Decimal(p), Decimal(q)) for p, q in book["b"]),
            asks=tuple((Decimal(p), Decimal(q)) for p, q in book["a"]),
            update_id=book.get("u"), exchange_sequence=book.get("seq"),
            exchange_event_ms=book.get("ts"), matching_engine_ms=book.get("cts"),
            ingested_ms=int(body["time"]))

    def funding_history(self, symbol: str, *, end_ms: int | None = None) -> list[FundingSnapshot]:
        params: dict[str, str | int] = {"category": "linear", "symbol": symbol, "limit": 200}
        if end_ms is not None:
            params["endTime"] = end_ms
        body = self.get("/v5/market/funding/history", params)
        return [FundingSnapshot(
            symbol=symbol, rate=Decimal(row["fundingRate"]),
            funding_ms=int(row["fundingRateTimestamp"]), observed_ms=int(body["time"]),
            source="bybit_settled_funding_history",
            status="KNOWN_ZERO" if Decimal(row["fundingRate"]) == 0 else "KNOWN")
            for row in body["result"]["list"]]

