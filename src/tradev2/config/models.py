from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from tradev2.domain.base import FrozenModel


class Mode(StrEnum):
    RESEARCH = "research"
    PAPER = "paper"
    SHADOW = "shadow"
    TESTNET = "testnet"
    LIVE = "live"


class RuntimeConfig(FrozenModel):
    mode: Mode = Mode.PAPER
    venue: Literal["bybit_linear"] = "bybit_linear"
    profile: str = Field(default="local-simulation", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    symbols: tuple[str, ...] = Field(default=("BTCUSDT", "ETHUSDT"), min_length=1, max_length=50)
    initial_equity: Decimal = Field(default=Decimal("1000"), gt=0)
    risk_fraction: Decimal = Field(default=Decimal("0.005"), gt=0, le=Decimal("0.02"))
    max_open_risk_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=Decimal("0.10"))
    # Bounded so a config cannot disable the spread gate or accept books the broker refuses.
    max_spread_bps: Decimal = Field(default=Decimal("15"), gt=0, le=Decimal("100"))
    source_max_age_ms: int = Field(default=15000, gt=0, le=15000)
    heartbeat_max_age_ms: int = Field(default=30000, gt=0)
    candidate_id: str = "REFERENCE_CANDIDATE_001"
    fixture_mode: bool = False
    testnet_authorized: bool = False

    @field_validator("symbols")
    @classmethod
    def linear_usdt_universe(cls, symbols: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(symbols)) != len(symbols):
            raise ValueError("symbol universe contains duplicates")
        for symbol in symbols:
            if not (symbol.isascii() and symbol.isalnum() and symbol.isupper()
                    and symbol.endswith("USDT") and 5 <= len(symbol) <= 24):
                raise ValueError(f"unsupported linear USDT symbol: {symbol!r}")
        return symbols
