from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from tradev2.domain.base import FrozenModel


class Amount(FrozenModel):
    value: Decimal | None
    status: Literal["KNOWN", "KNOWN_ZERO", "UNKNOWN", "ESTIMATED"]
    source: str = Field(min_length=1)
    source_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status == "UNKNOWN") != (self.value is None):
            raise ValueError("unknown amount must remain null")
        if self.status == "KNOWN_ZERO" and self.value != 0:
            raise ValueError("known zero requires zero")
        return self


class LedgerEntry(FrozenModel):
    event_id: str
    position_id: str
    gross_pnl: Amount
    entry_fee: Amount
    exit_fee: Amount
    funding: Amount

    @property
    def complete(self) -> bool:
        return all(a.status in {"KNOWN", "KNOWN_ZERO"} for a in
                   (self.gross_pnl, self.entry_fee, self.exit_fee, self.funding))

    @property
    def net_pnl(self) -> Decimal | None:
        parts = (self.gross_pnl.value, self.entry_fee.value, self.exit_fee.value, self.funding.value)
        if not self.complete or any(value is None for value in parts):
            return None
        gross, entry, exit_fee, funding = parts
        assert gross is not None and entry is not None and exit_fee is not None and funding is not None
        return gross - entry - exit_fee + funding


class Ledger:
    def __init__(self) -> None:
        self.entries: dict[str, LedgerEntry] = {}

    def post(self, entry: LedgerEntry) -> bool:
        previous = self.entries.get(entry.event_id)
        if previous is not None:
            if previous != entry:
                raise ValueError("conflicting immutable accounting event")
            return False
        self.entries[entry.event_id] = entry
        return True
