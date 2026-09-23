from decimal import Decimal
from typing import Literal

from pydantic import Field

from tradev2.domain.base import FrozenModel


class Position(FrozenModel):
    position_id: str
    owner_id: str
    symbol: str
    side: Literal["Buy", "Sell"]
    quantity: Decimal = Field(ge=0)
    entry_price: Decimal = Field(gt=0)
    protected_quantity: Decimal = Field(default=Decimal(0), ge=0)
    flat_proven: bool = False

    @property
    def managed(self) -> bool:
        return self.quantity > 0 or not self.flat_proven

    @property
    def protection_healthy(self) -> bool:
        return self.quantity == 0 or self.protected_quantity >= self.quantity
