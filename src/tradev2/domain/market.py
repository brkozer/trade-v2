from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from tradev2.domain.base import FrozenModel


class Candle(FrozenModel):
    symbol: str
    start_ms: int = Field(ge=0)
    interval_ms: int = Field(gt=0)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    confirmed: bool = True
    ingested_ms: int | None = None

    @property
    def close_ms(self) -> int:
        return self.start_ms + self.interval_ms

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high below OHLC range")
        if self.low > min(self.open, self.close):
            raise ValueError("low above OHLC range")
        return self


class FeeSchedule(FrozenModel):
    symbol: str
    maker: Decimal | None = None
    taker: Decimal | None = None
    source: str
    observed_ms: int | None = None
    valid_until_ms: int | None = None
    verified: bool = False

    def usable(self, now_ms: int) -> bool:
        return (self.verified and self.maker is not None and self.taker is not None
                and self.observed_ms is not None and self.observed_ms <= now_ms
                and self.valid_until_ms is not None and now_ms <= self.valid_until_ms)


class FundingSnapshot(FrozenModel):
    symbol: str
    rate: Decimal | None
    funding_ms: int | None
    observed_ms: int | None
    source: str
    status: Literal["KNOWN", "KNOWN_ZERO", "UNKNOWN", "ESTIMATED"] = "UNKNOWN"


class OrderBookSnapshot(FrozenModel):
    symbol: str
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]
    update_id: int | None = None
    exchange_sequence: int | None = None
    exchange_event_ms: int | None = None
    matching_engine_ms: int | None = None
    ingested_ms: int

    @property
    def spread_bps(self) -> Decimal | None:
        if not self.bids or not self.asks:
            return None
        bid, ask = self.bids[0][0], self.asks[0][0]
        if bid <= 0 or ask <= bid:
            return None
        return (ask - bid) / ((ask + bid) / 2) * 10000


class PublicTrade(FrozenModel):
    symbol: str
    trade_id: str
    side: Literal["Buy", "Sell"]
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    exchange_event_ms: int
    ingested_ms: int

