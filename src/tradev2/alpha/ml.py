"""Small, deterministic ridge baseline with purged chronological training.

No shuffled split, tuning on outer validation, or claim that OHLCV can predict
market microstructure. Model selection uses an inner forward interval only.
"""

from dataclasses import dataclass

import numpy as np

from tradev2.alpha.candidates import lag, rolling_mean
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import FloatArray, Panel

HORIZON_BARS = 4


@dataclass(frozen=True)
class RidgeFit:
    alpha: float
    train_start: int
    train_stop: int
    last_label_end: int
    samples: int
    coefficients: tuple[float, ...]


def features(panel: Panel) -> FloatArray:
    close = panel.values[:, :, 3]
    volume = panel.values[:, :, 4]
    one = close / lag(close, 1) - 1
    four = close / lag(close, 4) - 1
    sixteen = close / lag(close, 16) - 1
    volatility = np.sqrt(rolling_mean(one * one, 32))
    typical = lag(rolling_mean(volume, 32), 1)
    ratio = np.divide(volume, typical, out=np.full_like(volume, np.nan), where=typical > 0)
    btc = np.broadcast_to(four[:, panel.symbols.index("BTCUSDT")][:, None], close.shape)
    eth = np.broadcast_to(four[:, panel.symbols.index("ETHUSDT")][:, None], close.shape)
    finite = np.isfinite(four)
    count = finite.sum(axis=1, keepdims=True)
    basket = np.divide(np.where(finite, four, 0).sum(axis=1, keepdims=True), count,
                       out=np.full((len(close), 1), np.nan), where=count > 0)
    dispersion = four - basket
    return np.stack((one, four, sixteen, volatility, ratio - 1, btc, eth, dispersion), axis=2)


def fit_signals(panel: Panel, inputs: FloatArray, economics: dict[str, SymbolEconomics],
                train_start: int, train_stop: int, alpha: float) -> tuple[FloatArray, RidgeFit]:
    if (inputs.shape != (*panel.values.shape[:2], 8) or alpha <= 0
            or not 0 <= train_start < train_stop - HORIZON_BARS < len(panel.timestamps)):
        raise ValueError("invalid chronological ridge fit")
    close = panel.values[:, :, 3]
    forward = np.full_like(close, np.nan)
    forward[:-HORIZON_BARS] = close[HORIZON_BARS:] / close[:-HORIZON_BARS] - 1
    # Last training label must be observable strictly before the forward fold.
    last_feature_index = train_stop - HORIZON_BARS - 1
    train_x: FloatArray = inputs[train_start:last_feature_index + 1].reshape(-1, 8)
    train_y: FloatArray = forward[train_start:last_feature_index + 1].reshape(-1)
    valid = np.isfinite(train_x).all(axis=1) & np.isfinite(train_y)
    train_x, train_y = train_x[valid], train_y[valid]
    if len(train_y) < 1000:
        raise ValueError("insufficient chronological ML observations")
    # Deterministic stride limits computation without selecting on outcomes.
    stride = max(1, len(train_y) // 100_000)
    train_x, train_y = train_x[::stride], train_y[::stride]
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-12] = 1
    scaled = np.clip((train_x - mean) / scale, -10, 10)
    design = np.column_stack((np.ones(len(scaled)), scaled))
    penalty = np.diag([0.] + [alpha] * 8)
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ train_y)
    finite = np.isfinite(inputs).all(axis=2)
    safe = np.where(np.isfinite(inputs), inputs, mean)
    predictions = beta[0] + np.einsum("tsi,i->ts", np.clip((safe - mean) / scale, -10, 10), beta[1:])
    cost = np.asarray([2 * e.taker_rate + e.spread_bps / 10_000 + .0002
                       for e in (economics[s] for s in panel.symbols)])
    strength = np.where(finite & (np.abs(predictions) > 1.25 * cost[None, :]), predictions, 0.)
    strength[:max(200, train_start)] = 0
    fit = RidgeFit(alpha, train_start, train_stop, last_feature_index + HORIZON_BARS,
                   len(train_y), tuple(float(value) for value in beta))
    if fit.last_label_end >= train_stop:
        raise AssertionError("training label crossed the selection boundary")
    return strength, fit
