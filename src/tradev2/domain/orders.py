from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Self

from pydantic import Field, model_validator

from tradev2.domain.base import FrozenModel


class OrderIntent(FrozenModel):
    owner_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    symbol: str
    side: Literal["Buy", "Sell"]
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    available_ms: int = Field(ge=0)
    reduce_only: bool = False

    @property
    def client_id(self) -> str:
        # Length framing prevents ambiguous delimiter concatenation.
        fields = (self.owner_id, self.decision_id, self.symbol, self.side, str(self.reduce_only))
        payload = "".join(f"{len(value)}:{value}" for value in fields)
        return "tv2-" + sha256(payload.encode()).hexdigest()[:28]


class Fill(FrozenModel):
    execution_id: str = Field(min_length=1)
    client_id: str
    symbol: str
    side: Literal["Buy", "Sell"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal | None = None
    source: str
    source_ms: int = Field(ge=0)


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESTING = "RESTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXCHANGE_ENDED = "EXCHANGE_ENDED"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    PRICE_LEFT = "PRICE_LEFT"
    UNPLACED = "UNPLACED"
    UNRESOLVED = "UNRESOLVED"


class OrderSnapshot(FrozenModel):
    client_id: str
    owner_id: str
    requested: Decimal = Field(gt=0)
    filled: Decimal = Field(ge=0)
    status: OrderStatus

    @model_validator(mode="after")
    def valid_fill(self) -> Self:
        if self.filled > self.requested:
            raise ValueError("overfill")
        return self
