from decimal import Decimal
from typing import Literal

from tradev2.domain.base import FrozenModel


class RiskDecision(FrozenModel):
    action: Literal["ALLOW", "RESIZE", "REJECT", "HALT"]
    reason: str
    quantity: Decimal = Decimal(0)
    risk: Decimal | None = None
    notional: Decimal | None = None
