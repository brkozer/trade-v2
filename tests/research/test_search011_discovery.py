from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search011_discovery import (
    DAY_MS,
    LOOKBACKS,
    _write_new,
    flow_pressure,
    folds,
    momentum_overlap,
    signals,
)
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int = 20_159) -> Panel:
    rng = np.random.default_rng(44)
    returns = rng.normal(0, 0.001, (size, 6))
    close = 100 * np.exp(np.cumsum(returns, axis=0))
    high_distance = np.asarray([0.0005, 0.0005, 0.0001, 0.0002, 0.0010, 0.0009])
    low_distance = np.asarray([0.0005, 0.0005, 0.0010, 0.0009, 0.0001, 0.0002])
    high = close * (1 + high_distance[None, :])
    low = close * (1 - low_distance[None, :])
    volume = np.ones_like(close) * np.asarray([100, 100, 300, 200, 300, 200])
    values = np.stack((close, high, low, close, volume), axis=2)
    symbols = ("BTCUSDT", "ETHUSDT", "BUY1", "BUY2", "SELL1", "SELL2")
    return Panel(symbols, np.arange(size, dtype=np.int64) * BAR_MS, values, {})


def economics(names: tuple[str, ...], size: int = 20_159) -> dict[str, SymbolEconomics]:
    funding = np.asarray([[-BAR_MS, 0.0001], [size * BAR_MS, 0.0001]])
    return {
        name: SymbolEconomics(
            0.0002,
            0.00055,
            3.0,
            0.001,
            0.001,
            5.0,
            1000.0,
            funding.copy(),
            "test",
        )
        for name in names
    }


def test_flow_pressure_is_prefix_causal_bounded_and_orders_pressure() -> None:
    current = panel()
    left = flow_pressure(current, LOOKBACKS[0])
    changed = current.values.copy()
    changed[5000:, :, 1] *= 1.02
    altered = Panel(current.symbols, current.timestamps.copy(), changed, {})
    right = flow_pressure(altered, LOOKBACKS[0])
    np.testing.assert_array_equal(left[:5000], right[:5000])
    assert np.nanmax(np.abs(left)) <= 1
    assert left[4999, 2] > left[4999, 5]


def test_signals_are_daily_balanced_directional_and_exclude_factors() -> None:
    current = panel()
    result = signals(current, LOOKBACKS[0])
    active_rows = np.flatnonzero(np.any(result, axis=1))
    assert len(active_rows) > 100
    for index in active_rows:
        assert (int(current.timestamps[index]) + BAR_MS) % DAY_MS == 0
        assert np.count_nonzero(result[index] > 0) == 2
        assert np.count_nonzero(result[index] < 0) == 2
        assert result[index, 2] > 0 and result[index, 5] < 0
        assert result[index, 0] == 0 and result[index, 1] == 0


def test_momentum_overlap_is_forward_bounded_and_finite() -> None:
    current = panel()
    feature = flow_pressure(current, LOOKBACKS[0])
    value = momentum_overlap(current, feature, LOOKBACKS[0], 10_000, 15_000)
    assert value["days"] == 52
    assert value["median_daily_spearman"] is not None
    assert 0 <= float(value["median_absolute_daily_spearman"]) <= 1


def test_folds_are_disjoint_final_thirty_day_windows() -> None:
    current = panel()
    rows = folds(current, economics(current.symbols))
    assert len(rows) == 4
    assert all(row["stop_ms"] - row["start_ms"] == 30 * DAY_MS for row in rows)
    assert all(
        rows[index]["forward_stop"] == rows[index + 1]["forward_start"]
        for index in range(3)
    )


def test_unregistered_lookback_is_rejected() -> None:
    with pytest.raises(ValueError):
        flow_pressure(panel(), 96)


def test_artifacts_are_create_only(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    _write_new(target, {"evidence_role": "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"})
    with pytest.raises(FileExistsError):
        _write_new(target, {"changed": True})
