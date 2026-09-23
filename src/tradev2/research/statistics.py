"""Day-block inference counts correlated intraday observations as clustered evidence."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BootstrapResult:
    mean: float
    lower_95: float | None
    upper_95: float | None
    positive_pvalue: float | None
    blocks: int
    draws: int


def day_block_bootstrap(values: Sequence[float], *, seed: int, draws: int = 2000,
                        block_days: int = 7) -> BootstrapResult:
    data = np.asarray(values, dtype=np.float64)
    if not len(data) or not np.all(np.isfinite(data)):
        raise ValueError("bootstrap requires finite daily values")
    count = len(data) // block_days
    if count < 4:
        return BootstrapResult(float(data.mean()), None, None, None, count, draws)
    # Circular moving blocks retain within-week dependence and all calendar days.
    rng = np.random.default_rng(seed)
    blocks_per_draw = (len(data) + block_days - 1) // block_days
    starts = rng.integers(0, len(data), (draws, blocks_per_draw))
    indices = (starts[:, :, None] + np.arange(block_days)) % len(data)
    sampled = data[indices.reshape(draws, -1)[:, :len(data)]]
    means = sampled.mean(axis=1)
    null_means = means - data.mean()
    pvalue = (1 + int(np.count_nonzero(null_means >= data.mean()))) / (draws + 1)
    return BootstrapResult(float(data.mean()), float(np.quantile(means, .025)),
                           float(np.quantile(means, .975)), pvalue, count, draws)


def holm_adjust(pvalues: Sequence[float | None]) -> list[float | None]:
    tested = sorted((p, i) for i, p in enumerate(pvalues) if p is not None)
    results: list[float | None] = [None] * len(pvalues)
    previous = 0.
    for rank, (pvalue, index) in enumerate(tested):
        previous = max(previous, min(1., pvalue * (len(pvalues) - rank)))
        results[index] = previous
    return results
