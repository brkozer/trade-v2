"""Point-in-time, closed-bar factor registry for the completion campaign.

The historical panel is reused discovery evidence. A signal at row i is not
available until that bar closes; replay enters no earlier than row i + 1.
"""

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from tradev2.alpha.candidates import lag, rolling_mean
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel


@dataclass(frozen=True)
class FactorSpec:
    family: str
    lookback: int
    threshold: float
    holding_bars: int
    stop_pct: float = 0.025
    target_r: float = 1.5

    @property
    def candidate_id(self) -> str:
        return f"FINAL_{self.family}_{self.lookback}_{self.threshold:g}"

    def payload(self) -> dict[str, Any]:
        return asdict(self) | {"candidate_id": self.candidate_id}


MECHANISMS: dict[str, str] = {
    "trend_persistence": "Multi-day momentum persists after a material directional move.",
    "trend_pullback": "A pullback within an established trend offers a better entry.",
    "range_breakout": "A prior range break initiates a new directional move.",
    "short_reversal": "An extreme short-horizon move mean-reverts after costs.",
    "medium_reversal": "A larger multi-session dislocation mean-reverts.",
    "cross_sectional_momentum": "Leaders outperform laggards in cross-sectional selection; executed neutrality is not guaranteed.",
    "cross_sectional_reversal": "Cross-sectional extremes converge after a common shock.",
    "btc_residual": "A coin's return relative to lagged BTC beta converges.",
    "btc_eth_residual": "A coin's return relative to lagged BTC and ETH factors converges.",
    "volatility_expansion": "Directional volatility acceleration continues briefly.",
    "volume_reversal": "A volume-backed price shock exhausts rather than continues.",
    "btc_lead_lag": "Large BTC moves precede aligned moves in slower altcoins.",
    "funding_crowding": "The last settled funding rate proxies crowded positioning.",
}


def registry() -> tuple[FactorSpec, ...]:
    """Fixed two-point spaces; no result-dependent grid edits."""
    return (
        FactorSpec("trend_persistence", 96, .025, 24),
        FactorSpec("trend_persistence", 192, .04, 32),
        FactorSpec("trend_pullback", 96, .012, 16),
        FactorSpec("trend_pullback", 192, .018, 24),
        FactorSpec("range_breakout", 48, .001, 24),
        FactorSpec("range_breakout", 96, .0015, 32),
        FactorSpec("short_reversal", 4, .012, 8),
        FactorSpec("short_reversal", 8, .018, 12),
        FactorSpec("medium_reversal", 48, .045, 24),
        FactorSpec("medium_reversal", 96, .07, 32),
        FactorSpec("cross_sectional_momentum", 48, .20, 16),
        FactorSpec("cross_sectional_momentum", 96, .25, 24),
        FactorSpec("cross_sectional_reversal", 16, .20, 12),
        FactorSpec("cross_sectional_reversal", 48, .25, 16),
        FactorSpec("btc_residual", 48, .012, 16),
        FactorSpec("btc_residual", 96, .020, 24),
        FactorSpec("btc_eth_residual", 48, .012, 16),
        FactorSpec("btc_eth_residual", 96, .020, 24),
        FactorSpec("volatility_expansion", 32, 1.5, 16),
        FactorSpec("volatility_expansion", 64, 2.0, 24),
        FactorSpec("volume_reversal", 32, 2.0, 8),
        FactorSpec("volume_reversal", 64, 3.0, 12),
        FactorSpec("btc_lead_lag", 4, .006, 8),
        FactorSpec("btc_lead_lag", 8, .010, 12),
        FactorSpec("funding_crowding", 48, .0002, 16),
        FactorSpec("funding_crowding", 96, .0004, 24),
    )


def _factor_beta(returns: FloatArray, factor: FloatArray, window: int) -> FloatArray:
    mean_y = rolling_mean(returns, window)
    mean_x = rolling_mean(factor, window)
    covariance = rolling_mean(returns * factor, window) - mean_y * mean_x
    variance = rolling_mean(factor * factor, window) - mean_x * mean_x
    beta = np.divide(covariance, variance, out=np.full_like(covariance, np.nan),
                     where=variance > 1e-12)
    return lag(beta, 1)


def _two_factor_residual(returns: FloatArray, btc: FloatArray,
                         eth: FloatArray, window: int) -> FloatArray:
    mean_y = rolling_mean(returns, window)
    mean_b = rolling_mean(btc, window)
    mean_e = rolling_mean(eth, window)
    var_b = rolling_mean(btc * btc, window) - mean_b * mean_b
    var_e = rolling_mean(eth * eth, window) - mean_e * mean_e
    cov_be = rolling_mean(btc * eth, window) - mean_b * mean_e
    cov_yb = rolling_mean(returns * btc, window) - mean_y * mean_b
    cov_ye = rolling_mean(returns * eth, window) - mean_y * mean_e
    determinant = var_b * var_e - cov_be * cov_be
    beta_b = lag(np.divide(cov_yb * var_e - cov_ye * cov_be, determinant,
                           out=np.full_like(returns, np.nan), where=determinant > 1e-16), 1)
    beta_e = lag(np.divide(cov_ye * var_b - cov_yb * cov_be, determinant,
                           out=np.full_like(returns, np.nan), where=determinant > 1e-16), 1)
    return returns - beta_b * btc - beta_e * eth


def _previous_range(values: FloatArray, window: int, highest: bool) -> FloatArray:
    output = np.full_like(values, np.nan)
    for index in range(window, len(values)):
        period = values[index - window:index]
        output[index] = period.max(axis=0) if highest else period.min(axis=0)
    return output


def _settled_funding(panel: Panel, economics: dict[str, SymbolEconomics]) -> FloatArray:
    result = np.full((len(panel.timestamps), len(panel.symbols)), np.nan)
    decision_times = panel.timestamps + BAR_MS
    for column, symbol in enumerate(panel.symbols):
        observations = economics[symbol].funding
        indices = np.searchsorted(observations[:, 0], decision_times, side="right") - 1
        known = indices >= 0
        result[known, column] = observations[indices[known], 1]
    return result


def signals(panel: Panel, spec: FactorSpec,
            economics: dict[str, SymbolEconomics]) -> FloatArray:
    close, high, low, volume = (panel.values[:, :, index] for index in (3, 1, 2, 4))
    ret = close / lag(close, 1) - 1
    movement = close / lag(close, spec.lookback) - 1
    with np.errstate(divide="ignore", invalid="ignore"):
        if spec.family == "trend_persistence":
            signal = np.where(np.abs(movement) >= spec.threshold, movement, 0.)
        elif spec.family == "trend_pullback":
            trend = close / lag(close, spec.lookback) - 1
            short = close / lag(close, 8) - 1
            signal = np.where((trend > spec.threshold) & (short < -.006), trend,
                     np.where((trend < -spec.threshold) & (short > .006), trend, 0.))
        elif spec.family == "range_breakout":
            prior_high = _previous_range(high, spec.lookback, True)
            prior_low = _previous_range(low, spec.lookback, False)
            upside = close / prior_high - 1
            downside = close / prior_low - 1
            signal = np.where(upside > spec.threshold, upside,
                     np.where(downside < -spec.threshold, downside, 0.))
        elif spec.family in {"short_reversal", "medium_reversal"}:
            signal = np.where(np.abs(movement) >= spec.threshold, -movement, 0.)
        elif spec.family in {"cross_sectional_momentum", "cross_sectional_reversal"}:
            ranks = np.argsort(np.argsort(movement, axis=1, kind="stable"),
                               axis=1, kind="stable")
            edge = max(1, int(len(panel.symbols) * spec.threshold))
            centered = ranks - (len(panel.symbols) - 1) / 2
            sign = 1 if spec.family == "cross_sectional_momentum" else -1
            signal = np.where((ranks < edge) | (ranks >= len(panel.symbols) - edge),
                              sign * centered / len(panel.symbols), 0.)
            signal[~np.isfinite(movement)] = 0
        elif spec.family in {"btc_residual", "btc_eth_residual"}:
            btc = ret[:, panel.symbols.index("BTCUSDT")][:, None]
            btc_factor = np.broadcast_to(btc, ret.shape)
            if spec.family == "btc_eth_residual":
                eth = ret[:, panel.symbols.index("ETHUSDT")][:, None]
                eth_factor = np.broadcast_to(eth, ret.shape)
                residual = _two_factor_residual(ret, btc_factor, eth_factor, spec.lookback)
            else:
                residual = ret - _factor_beta(ret, btc_factor, spec.lookback) * btc_factor
            scale = np.sqrt(rolling_mean(residual * residual, spec.lookback))
            displacement = rolling_mean(residual, 4)
            ratio = np.divide(displacement, scale,
                              out=np.full_like(residual, np.nan), where=scale > 1e-12)
            signal = np.where(np.abs(displacement) >= spec.threshold, -ratio, 0.)
        elif spec.family == "volatility_expansion":
            recent = rolling_mean(np.abs(ret), 8)
            baseline = lag(rolling_mean(np.abs(ret), spec.lookback), 1)
            ratio = recent / baseline
            signal = np.where((ratio >= spec.threshold) & (np.abs(ret) >= .003),
                              np.sign(ret) * ratio, 0.)
        elif spec.family == "volume_reversal":
            typical = lag(rolling_mean(volume, spec.lookback), 1)
            ratio = volume / typical
            signal = np.where((ratio >= spec.threshold) & (np.abs(ret) >= .005),
                              -np.sign(ret) * ratio, 0.)
        elif spec.family == "btc_lead_lag":
            btc_index = panel.symbols.index("BTCUSDT")
            lead = movement[:, btc_index][:, None]
            quiet = np.abs(movement) < np.abs(lead) * .5
            signal = np.where((np.abs(lead) >= spec.threshold) & quiet, lead, 0.)
            signal[:, btc_index] = 0
        elif spec.family == "funding_crowding":
            settled = _settled_funding(panel, economics)
            signal = np.where(np.abs(settled) >= spec.threshold, -settled, 0.)
        else:
            raise ValueError(f"unregistered factor family: {spec.family}")
    signal = np.asarray(signal, dtype=np.float64)
    signal[~np.isfinite(signal)] = 0
    signal[:max(200, spec.lookback + 2)] = 0
    return signal
