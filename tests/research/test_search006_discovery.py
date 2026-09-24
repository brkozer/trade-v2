from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search006_discovery import (
    BUFFERS,
    HOLDING_BARS,
    _write_new,
    fit_hourly_edges,
    folds,
    signals,
)
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int = 1400) -> Panel:
    rng = np.random.default_rng(42)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, (size, 3)), axis=0))
    values = np.stack((close, close * 1.001, close * 0.999, close,
                       np.ones_like(close) * 100), axis=2)
    return Panel(("A", "B", "C"), np.arange(size, dtype=np.int64) * BAR_MS, values, {})


def economics(names: tuple[str, ...], size: int = 1400) -> dict[str, SymbolEconomics]:
    funding = np.asarray([[-BAR_MS, 0.0001], [size * BAR_MS, 0.0001]])
    return {name: SymbolEconomics(0.0002, 0.00055, 3.0, 0.001, 0.001, 5.0,
                                  1000.0, funding.copy(), "test") for name in names}


def test_hourly_fit_is_prefix_causal_and_market_demeaned() -> None:
    full = panel()
    left, counts = fit_hourly_edges(full, 0, 900)
    changed = full.values.copy()
    changed[900:, :, :4] *= np.asarray([1.5, 0.7, 1.2])[None, :, None]
    changed_panel = Panel(full.symbols, full.timestamps.copy(), changed, {})
    right, changed_counts = fit_hourly_edges(changed_panel, 0, 900)
    np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(counts, changed_counts)
    np.testing.assert_allclose(left.mean(axis=1), 0, atol=1e-15)


def test_signals_only_hourly_and_above_symbol_cost_hurdle() -> None:
    current = panel()
    known = economics(current.symbols)
    edges = np.zeros((24, 3))
    edges[:, 0] = 0.01
    result = signals(current, edges, known, BUFFERS[0], 200, 400)
    active = np.flatnonzero(result[:, 0])
    assert len(active) > 0
    assert all((int(current.timestamps[index]) + BAR_MS) % 3_600_000 == 0
               for index in active)
    assert np.all(result[:200] == 0) and np.all(result[400:] == 0)


def test_fit_purges_incomplete_forward_labels() -> None:
    current = panel()
    _, counts = fit_hourly_edges(current, 0, 900)
    expected_decisions = [index for index in range(0, 900 - HOLDING_BARS - 1)
                          if (int(current.timestamps[index]) + BAR_MS) % 3_600_000 == 0]
    assert int(counts.sum()) == len(expected_decisions) * len(current.symbols)


def test_folds_are_nested_chronological() -> None:
    current = panel(20159)
    rows = folds(current, economics(current.symbols, 20159))
    assert len(rows) == 4
    assert all(row["discovery_stop"] == row["selection_start"]
               and row["selection_stop"] == row["forward_start"]
               and row["forward_start"] < row["forward_stop"] for row in rows)


def test_artifacts_are_create_only(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    _write_new(target, {"evidence_role": "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"})
    with pytest.raises(FileExistsError):
        _write_new(target, {"changed": True})
