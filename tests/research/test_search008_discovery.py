from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search008_discovery import (
    COST_MULTIPLES,
    DAY_MS,
    _write_new,
    folds,
    signals,
)
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int = 20_159) -> Panel:
    rng = np.random.default_rng(29)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.0005, (size, 4)), axis=0))
    values = np.stack((close, close * 1.001, close * 0.999, close,
                       np.ones_like(close) * 100), axis=2)
    return Panel(("BTCUSDT", "ETHUSDT", "A", "B"),
                 np.arange(size, dtype=np.int64) * BAR_MS, values, {})


def economics(names: tuple[str, ...], size: int = 20_159) -> dict[str, SymbolEconomics]:
    funding = np.asarray([[-BAR_MS, 0.0001], [size * BAR_MS, 0.0001]])
    return {name: SymbolEconomics(0.0002, 0.00055, 3.0, 0.001, 0.001, 5.0,
                                  1000.0, funding.copy(), "test") for name in names}


def test_signal_requires_low_volume_wide_extreme_close_and_reverses() -> None:
    current = panel(400)
    values = current.values.copy()
    values[250, 2] = np.asarray([100.0, 104.0, 99.0, 103.8, 10.0])
    altered = Panel(current.symbols, current.timestamps.copy(), values, {})
    result = signals(altered, economics(altered.symbols, 400), COST_MULTIPLES[0])
    assert result[250, 2] < 0
    assert np.count_nonzero(result[250]) == 1


def test_signal_is_prefix_causal() -> None:
    current = panel(800)
    known = economics(current.symbols, 800)
    left = signals(current, known, COST_MULTIPLES[0])
    changed = current.values.copy()
    changed[500:, :, :4] *= np.asarray([1.2, 0.8, 1.4, 0.7])[None, :, None]
    altered = Panel(current.symbols, current.timestamps.copy(), changed, {})
    right = signals(altered, known, COST_MULTIPLES[0])
    np.testing.assert_array_equal(left[:500], right[:500])


def test_folds_are_disjoint_final_thirty_day_windows() -> None:
    current = panel()
    rows = folds(current, economics(current.symbols))
    assert len(rows) == 4
    assert all(row["stop_ms"] - row["start_ms"] == 30 * DAY_MS for row in rows)
    assert all(rows[index]["forward_stop"] == rows[index + 1]["forward_start"]
               for index in range(3))


def test_unregistered_cost_multiple_is_rejected() -> None:
    current = panel(400)
    with pytest.raises(ValueError):
        signals(current, economics(current.symbols, 400), 2.0)


def test_artifacts_are_create_only(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    _write_new(target, {"evidence_role": "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"})
    with pytest.raises(FileExistsError):
        _write_new(target, {"changed": True})
