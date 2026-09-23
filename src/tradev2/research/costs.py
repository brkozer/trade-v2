"""Explicit historical assumptions; unavailable market microstructure stays unavailable."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from tradev2.research.datasets import FloatArray


@dataclass(frozen=True)
class CostScenario:
    name: str = "base_taker"
    fee_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    slippage_bps_per_side: float = 1.0
    latency_bars: int = 0
    fill_fraction: float = 1.0
    miss_every: int = 0

    def __post_init__(self) -> None:
        if min(self.fee_multiplier, self.spread_multiplier, self.slippage_bps_per_side) < 0:
            raise ValueError("cost assumptions must not be negative")
        if not 0 < self.fill_fraction <= 1 or self.latency_bars < 0 or self.miss_every < 0:
            raise ValueError("invalid fill assumptions")


BASE = CostScenario()
WIDE = CostScenario("wide_costs", 1.5, 2., 3.)
FRICTION = CostScenario("delay_partial_missed", 1., 1.5, 2., 1, .5, 4)


@dataclass(frozen=True)
class SymbolEconomics:
    maker_rate: float
    taker_rate: float
    spread_bps: float
    qty_step: float
    min_qty: float
    min_notional: float
    max_qty: float
    funding: FloatArray
    provenance: str

    def __post_init__(self) -> None:
        numeric = (self.maker_rate, self.taker_rate, self.spread_bps, self.qty_step,
                   self.min_qty, self.min_notional, self.max_qty)
        if not all(np.isfinite(numeric)) or min(numeric) < 0 or self.qty_step <= 0:
            raise ValueError("missing/invalid fee, spread or instrument rule")
        if self.funding.ndim != 2 or self.funding.shape[1] != 2 or len(self.funding) < 2:
            raise ValueError("funding coverage required")
        if not np.all(np.isfinite(self.funding)) or np.any(np.diff(self.funding[:, 0]) <= 0):
            raise ValueError("funding observations must be finite, sorted and unique")


def load_economics(payload: dict[str, Any], symbols: tuple[str, ...]) -> dict[str, SymbolEconomics]:
    result: dict[str, SymbolEconomics] = {}
    for symbol in symbols:
        row = payload["symbols"][symbol]
        result[symbol] = SymbolEconomics(
            float(row["maker_rate"]), float(row["taker_rate"]), float(row["spread_bps"]),
            float(row["qty_step"]), float(row["min_qty"]), float(row["min_notional"]),
            float(row["max_qty"]), np.asarray(row["funding"], dtype=np.float64), row["provenance"])
    return result


def funding_cashflow(economics: SymbolEconomics, entry_ms: int, exit_ms: int,
                     notional: float, direction: int) -> float:
    """Positive is a paid cost; actual settlement timestamps, (entry, exit]."""
    if entry_ms < economics.funding[0, 0] or exit_ms > economics.funding[-1, 0]:
        raise ValueError("funding coverage incomplete; unknown must not become zero")
    first = int(np.searchsorted(economics.funding[:, 0], entry_ms, side="right"))
    last = int(np.searchsorted(economics.funding[:, 0], exit_ms, side="right"))
    # Entry notional is an explicit approximation; historical mark prices are unavailable.
    return float(economics.funding[first:last, 1].sum()) * notional * direction
