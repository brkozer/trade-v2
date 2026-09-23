"""Six causal economic hypotheses, each with a declared three-point search."""

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

import numpy as np

from tradev2.research.datasets import FloatArray, Panel
from tradev2.strategies.reference import REFERENCE_PARAMS, ReferenceParams

Family = Literal["rsi_reversion", "time_series_momentum", "compression_breakout",
                 "relative_strength", "basket_residual_reversion", "volume_shock"]


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    family: Family
    lookback: int
    threshold: float
    holding_bars: int
    reference: ReferenceParams | None = None
    stop_pct: float = 0.02
    target_r: float = 1.4

    def payload(self) -> dict[str, Any]:
        return asdict(self)


MECHANISMS = {
    "rsi_reversion": "Temporary short-horizon selling pressure may reverse after an oversold close.",
    "time_series_momentum": "Persistent directional order flow may continue across several hours.",
    "compression_breakout": "A quiet range followed by a directional break may begin volatility expansion.",
    "relative_strength": "Cross-sectional underreaction may reward prior leaders against prior laggards.",
    "basket_residual_reversion": "Idiosyncratic dislocations relative to trailing market beta may converge.",
    "volume_shock": "Unusually large traded volume accompanying a move may reveal persistent information.",
}


def candidate_grid() -> tuple[Candidate, ...]:
    candidates: list[Candidate] = []
    for threshold in (8.0, REFERENCE_PARAMS.entry_rsi_max, 23.0):
        params = replace(REFERENCE_PARAMS, entry_rsi_max=threshold)
        name = params.candidate_id if threshold == REFERENCE_PARAMS.entry_rsi_max else f"RSI_{int(threshold)}"
        candidates.append(Candidate(name, "rsi_reversion", params.entry_period, threshold,
                                    params.time_stop_bars, params, params.stop_pct, params.target_r))
    for lookback in (8, 24, 48):
        candidates.append(Candidate(f"TSM_{lookback}", "time_series_momentum", lookback, .005, 16))
    for lookback in (12, 24, 48):
        candidates.append(Candidate(f"BREAK_{lookback}", "compression_breakout", lookback, .75, 24))
    for lookback in (16, 48, 96):
        candidates.append(Candidate(f"REL_{lookback}", "relative_strength", lookback, .20, 16))
    for threshold in (1.5, 2.0, 2.5):
        candidates.append(Candidate(f"RESID_{threshold:g}", "basket_residual_reversion", 96, threshold, 12))
    for threshold in (1.5, 2.0, 3.0):
        candidates.append(Candidate(f"VOLUME_{threshold:g}", "volume_shock", 32, threshold, 8))
    return tuple(candidates)


def lag(values: FloatArray, bars: int) -> FloatArray:
    output = np.full_like(values, np.nan)
    if 0 < bars < len(values):
        output[bars:] = values[:-bars]
    return output


def rolling_mean(values: FloatArray, window: int) -> FloatArray:
    output = np.full_like(values, np.nan)
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        return output
    finite = np.isfinite(values)
    sums = np.concatenate((np.zeros((1, values.shape[1])),
                           np.cumsum(np.where(finite, values, 0), axis=0)), axis=0)
    counts = np.concatenate((np.zeros((1, values.shape[1])), np.cumsum(finite, axis=0)), axis=0)
    means = (sums[window:] - sums[:-window]) / window
    means[counts[window:] - counts[:-window] != window] = np.nan
    output[window - 1:] = means
    return output


def rsi_series(closes: FloatArray, period: int) -> FloatArray:
    output = np.full_like(closes, 50.)
    if len(closes) <= period:
        return output
    changes = np.diff(closes, axis=0)
    gains = np.maximum(changes[:period], 0).mean(axis=0)
    losses = np.maximum(-changes[:period], 0).mean(axis=0)
    for index in range(period, len(closes)):
        if index > period:
            gains = (gains * (period - 1) + np.maximum(changes[index - 1], 0)) / period
            losses = (losses * (period - 1) + np.maximum(-changes[index - 1], 0)) / period
        ratio = np.divide(gains, losses, out=np.full_like(gains, 1e9), where=losses != 0)
        output[index] = 100 - 100 / (1 + ratio)
    return output


def decisions(panel: Panel, candidate: Candidate) -> tuple[FloatArray, FloatArray]:
    """Closed-bar signed strengths and exit-RSI; no future values or learned full-sample thresholds."""
    close, high, low, volume = (panel.values[:, :, i] for i in (3, 1, 2, 4))
    returns = np.divide(close, lag(close, 1)) - 1
    signals = np.zeros_like(close)
    exit_rsi = rsi_series(close, REFERENCE_PARAMS.exit_period)
    lookback, threshold = candidate.lookback, candidate.threshold
    if candidate.family == "rsi_reversion":
        params = candidate.reference
        if params is None:
            raise ValueError("reference candidate missing immutable parameters")
        rsi = rsi_series(close, params.entry_period)
        signals = np.where(rsi <= params.entry_rsi_max, (100 - rsi) / 100, 0.)
    elif candidate.family == "time_series_momentum":
        movement = close / lag(close, lookback) - 1
        signals = np.where(np.abs(movement) >= threshold, movement, 0.)
    elif candidate.family == "compression_breakout":
        prior_high = np.full_like(high, np.nan)
        prior_low = np.full_like(low, np.nan)
        for index in range(lookback, len(high)):
            prior_high[index] = high[index - lookback:index].max(axis=0)
            prior_low[index] = low[index - lookback:index].min(axis=0)
        absolute = np.abs(returns)
        quiet = lag(rolling_mean(absolute, lookback), 1) < threshold * lag(rolling_mean(absolute, lookback * 4), 1)
        signals = np.where(quiet & (close > prior_high), close / prior_high - 1,
                           np.where(quiet & (close < prior_low), close / prior_low - 1, 0.))
    elif candidate.family == "relative_strength":
        movement = close / lag(close, lookback) - 1
        # Ranks only use the same already-closed timestamp across the aligned universe.
        order = np.argsort(np.argsort(movement, axis=1, kind="stable"), axis=1, kind="stable")
        lower = int(len(panel.symbols) * threshold)
        upper = len(panel.symbols) - lower
        centered = order - (len(panel.symbols) - 1) / 2
        signals = np.where((order < lower) | (order >= upper), centered / len(panel.symbols), 0.)
        signals[~np.isfinite(movement)] = 0
    elif candidate.family == "basket_residual_reversion":
        market = returns.mean(axis=1, keepdims=True)
        market = np.broadcast_to(market, returns.shape).copy()
        mean_r = rolling_mean(returns, lookback)
        mean_m = rolling_mean(market, lookback)
        covariance = rolling_mean(returns * market, lookback) - mean_r * mean_m
        variance = rolling_mean(market * market, lookback) - mean_m * mean_m
        beta = lag(np.divide(covariance, variance, out=np.full_like(covariance, np.nan), where=variance > 1e-14), 1)
        residual = returns - beta * market
        center = lag(rolling_mean(residual, lookback), 1)
        scale = np.sqrt(np.maximum(lag(rolling_mean(residual * residual, lookback), 1) - center * center, 0))
        z = np.divide(residual - center, scale, out=np.full_like(residual, np.nan), where=scale > 1e-12)
        signals = np.where(np.abs(z) >= threshold, -z, 0.)
    elif candidate.family == "volume_shock":
        typical = lag(rolling_mean(volume, lookback), 1)
        ratio = np.divide(volume, typical, out=np.zeros_like(volume), where=typical > 0)
        signals = np.where((ratio >= threshold) & (np.abs(returns) >= .002), np.sign(returns) * ratio, 0.)
    else:
        raise ValueError("unknown family")
    signals[~np.isfinite(signals)] = 0
    signals[:max(200, lookback)] = 0
    return signals, exit_rsi
