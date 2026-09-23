from decimal import Decimal

from pydantic import Field

from tradev2.domain.base import FrozenModel


class PortfolioRisk(FrozenModel):
    equity: Decimal | None
    available_margin: Decimal | None
    open_risk: Decimal = Field(ge=0)
    pending_risk: Decimal = Field(ge=0)
    directional_notional: Decimal = Field(ge=0)
    correlated_notional: Decimal = Field(ge=0)
    symbol_notional: Decimal = Field(default=Decimal(0), ge=0)
    daily_pnl: Decimal | None
    reconciled: bool = False
    protection_healthy: bool = False
