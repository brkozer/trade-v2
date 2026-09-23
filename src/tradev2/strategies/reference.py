"""Adapted from Bybit v4.2 rsi_candidate.py; no execution capabilities."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceParams:
    candidate_id: str = "REFERENCE_CANDIDATE_001"
    bar_minutes: int = 15
    entry_period: int = 4
    exit_period: int = 5
    entry_rsi_max: float = 15.0
    exit_rsi_min: float = 65.0
    stop_pct: float = 0.02
    target_r: float = 1.4
    time_stop_bars: int = 32
    maker_wait_ms: int = 60_000

    def __post_init__(self) -> None:
        if not (0 < self.entry_rsi_max < self.exit_rsi_min < 100):
            raise ValueError("RSI thresholds must be ordered inside (0, 100)")
        if min(self.bar_minutes, self.entry_period, self.exit_period,
               self.time_stop_bars, self.maker_wait_ms) <= 0:
            raise ValueError("periods and waits must be positive")
        if not (0 < self.stop_pct < 1 and self.target_r > 0):
            raise ValueError("invalid protective levels")


REFERENCE_PARAMS = ReferenceParams()


def wilder_rsi(closes: Sequence[float], period: int) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) < period + 1:
        return 50.0
    gains = sum(max(closes[i] - closes[i - 1], 0.0) for i in range(1, period + 1)) / period
    losses = sum(max(closes[i - 1] - closes[i], 0.0) for i in range(1, period + 1)) / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains = (gains * (period - 1) + max(delta, 0.0)) / period
        losses = (losses * (period - 1) + max(-delta, 0.0)) / period
    # Preserve the legacy zero-loss convention for exact decision parity.
    return 100 - 100 / (1 + (gains / losses if losses else 1e9))


def reference_entry(closes: Sequence[float], bar_ms: int, last_signal_bar: int | None = None,
                    params: ReferenceParams = REFERENCE_PARAMS) -> bool:
    return bar_ms != last_signal_bar and wilder_rsi(closes, params.entry_period) <= params.entry_rsi_max


def reference_exit(closes: Sequence[float], bars_held: int,
                   params: ReferenceParams = REFERENCE_PARAMS) -> str | None:
    if wilder_rsi(closes, params.exit_period) >= params.exit_rsi_min:
        return "RSI_EXIT"
    if bars_held >= params.time_stop_bars:
        return "TIME_STOP"
    return None


def reference_levels(entry: float, params: ReferenceParams = REFERENCE_PARAMS) -> tuple[float, float]:
    if entry <= 0:
        raise ValueError("entry must be positive")
    return entry * (1 - params.stop_pct), entry * (1 + params.stop_pct * params.target_r)


def maker_eligible(limit_price: float, ask: float, placed_ms: int, now_ms: int,
                   params: ReferenceParams = REFERENCE_PARAMS) -> bool:
    return 0 <= now_ms - placed_ms <= params.maker_wait_ms and ask <= limit_price
