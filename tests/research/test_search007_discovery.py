from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search007_discovery import (
    DAY_MS,
    LOOKBACKS,
    _write_new,
    folds,
    residual_volatility,
    signals,
)
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int = 20_159) -> Panel:
    rng = np.random.default_rng(17)
    market = rng.normal(0, 0.001, size)
    returns = np.column_stack((
        market,
        0.8 * market + rng.normal(0, 0.0005, size),
        market + rng.normal(0, 0.0002, size),
        market + rng.normal(0, 0.0004, size),
        market + rng.normal(0, 0.0015, size),
        market + rng.normal(0, 0.0030, size),
    ))
    close = 100 * np.exp(np.cumsum(returns, axis=0))
    values = np.stack((close, close * 1.001, close * 0.999, close,
                       np.ones_like(close) * 100), axis=2)
    symbols = ("BTCUSDT", "ETHUSDT", "LOW1", "LOW2", "HIGH1", "HIGH2")
    return Panel(symbols, np.arange(size, dtype=np.int64) * BAR_MS, values, {})


def economics(names: tuple[str, ...], size: int = 20_159) -> dict[str, SymbolEconomics]:
    funding = np.asarray([[-BAR_MS, 0.0001], [size * BAR_MS, 0.0001]])
    return {name: SymbolEconomics(0.0002, 0.00055, 3.0, 0.001, 0.001, 5.0,
                                  1000.0, funding.copy(), "test") for name in names}


def test_residual_volatility_is_prefix_causal_and_ranks_noise() -> None:
    current = panel()
    left = residual_volatility(current, LOOKBACKS[0])
    changed = current.values.copy()
    changed[5000:, :, :4] *= np.asarray([1, 1, 1.2, 0.8, 1.4, 0.7])[None, :, None]
    altered = Panel(current.symbols, current.timestamps.copy(), changed, {})
    right = residual_volatility(altered, LOOKBACKS[0])
    np.testing.assert_array_equal(left[:5000], right[:5000])
    assert left[4999, current.symbols.index("LOW1")] < left[4999, current.symbols.index("HIGH2")]


def test_signals_are_weekly_balanced_and_exclude_factors() -> None:
    current = panel()
    result = signals(current, LOOKBACKS[0])
    active_rows = np.flatnonzero(np.any(result, axis=1))
    assert len(active_rows) > 0
    for index in active_rows:
        entry_ms = int(current.timestamps[index]) + BAR_MS
        assert entry_ms % DAY_MS == 0 and (entry_ms // DAY_MS + 3) % 7 == 0
        assert np.count_nonzero(result[index] > 0) == 2
        assert np.count_nonzero(result[index] < 0) == 2
        assert result[index, 0] == 0 and result[index, 1] == 0


def test_folds_are_disjoint_final_thirty_day_windows() -> None:
    current = panel()
    rows = folds(current, economics(current.symbols))
    assert len(rows) == 4
    assert all(row["stop_ms"] - row["start_ms"] == 30 * DAY_MS for row in rows)
    assert all(rows[index]["forward_stop"] == rows[index + 1]["forward_start"]
               for index in range(3))


def test_unregistered_lookback_is_rejected() -> None:
    with pytest.raises(ValueError):
        residual_volatility(panel(), 96)


def test_artifacts_are_create_only(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    _write_new(target, {"evidence_role": "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"})
    with pytest.raises(FileExistsError):
        _write_new(target, {"changed": True})
