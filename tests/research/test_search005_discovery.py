from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search005_discovery import IDEA, _write_new, folds, signal
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int = 1200) -> Panel:
    timestamps = np.arange(size, dtype=np.int64) * BAR_MS
    close = np.full((size, 2), 100.0)
    values = np.stack((close, close, close, close, np.ones_like(close)), axis=2)
    return Panel(("A", "B"), timestamps, values, {})


def economics(size: int = 1200) -> dict[str, SymbolEconomics]:
    funding = np.asarray([
        [0, 0.00006],
        [32 * BAR_MS, 0.00007],
        [64 * BAR_MS, -0.00020],
        [96 * BAR_MS, -0.00011],
        [size * BAR_MS, 0.00010],
    ])
    return {symbol: SymbolEconomics(0.0002, 0.00055, 2.0, 0.001, 0.001, 5.0,
                                    1000.0, funding.copy(), "test")
            for symbol in ("A", "B")}


def test_signal_uses_only_consecutive_settled_rates_and_receiving_side() -> None:
    current = panel()
    values = signal(current, economics(), IDEA.thresholds[0])
    assert np.all(values[:200] == 0)
    assert values[32, 0] == 0  # warmup deliberately suppresses this otherwise-valid short
    assert values[64, 0] == 0  # sign changed
    # Add two later same-sign negative settlements after warmup: receiver is long.
    known = economics()
    known["A"] = SymbolEconomics(0.0002, 0.00055, 2.0, 0.001, 0.001, 5.0, 1000.0,
        np.asarray([[0, 0.0001], [192 * BAR_MS, -0.0001],
                    [224 * BAR_MS, -0.00011], [1200 * BAR_MS, 0.0001]]), "test")
    values = signal(current, known, IDEA.thresholds[0])
    assert values[224, 0] > 0


def test_signal_is_prefix_causal_when_future_funding_changes() -> None:
    full = panel()
    short = Panel(full.symbols, full.timestamps[:500].copy(), full.values[:500].copy(), {})
    known = economics()
    known["A"] = SymbolEconomics(0.0002, 0.00055, 2.0, 0.001, 0.001, 5.0, 1000.0,
        np.asarray([[0, 0.0001], [96 * BAR_MS, -0.0001],
                    [600 * BAR_MS, -0.0002], [1200 * BAR_MS, 0.0001]]), "test")
    left = signal(short, known, IDEA.thresholds[0])
    known["A"].funding[2, 1] = 0.0002
    right = signal(full, known, IDEA.thresholds[0])
    np.testing.assert_array_equal(left, right[:500])


def test_folds_are_chronological_and_tail_is_reserved() -> None:
    entries = folds(panel(1384))
    assert len(entries) == 3
    assert all(row["selection_stop"] == row["forward_start"]
               and row["forward_start"] < row["forward_stop"] for row in entries)
    assert entries[-1]["forward_stop"] < 1384


def test_artifacts_are_create_only(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    _write_new(target, {"evidence_role": "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"})
    with pytest.raises(FileExistsError):
        _write_new(target, {"changed": True})
