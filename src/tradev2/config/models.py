from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field

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
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    initial_equity: Decimal = Field(default=Decimal("1000"), gt=0)
    risk_fraction: Decimal = Field(default=Decimal("0.005"), gt=0, le=Decimal("0.02"))
    max_open_risk_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=Decimal("0.10"))
    max_spread_bps: Decimal = Field(default=Decimal("15"), gt=0)
    source_max_age_ms: int = Field(default=15000, gt=0)
    heartbeat_max_age_ms: int = Field(default=30000, gt=0)
    candidate_id: str = "REFERENCE_CANDIDATE_001"
    testnet_authorized: bool = False

