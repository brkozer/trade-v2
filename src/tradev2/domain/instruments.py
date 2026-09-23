from decimal import Decimal

from pydantic import Field

from tradev2.domain.base import FrozenModel


class MarketIdentity(FrozenModel):
    venue: str = "bybit"
    category: str = "linear"
    symbol: str
    settlement: str = "USDT"


class InstrumentRules(FrozenModel):
    symbol: str
    qty_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(ge=0)
    tick_size: Decimal = Field(gt=0)
    max_qty: Decimal | None = Field(default=None, gt=0)
    observed_ms: int | None = None
    source: str = "unknown"

