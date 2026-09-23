from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.search004 import IDEAS, Idea, _new, folds, signal
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel(size: int) -> Panel:
    timestamps = np.arange(size, dtype=np.int64) * BAR_MS
    values = np.empty((size, 3, 5), dtype=np.float64)
    for column in range(3):
        close = 100 + np.arange(size) * (.01 + column*.002)
        values[:, column, 0] = close
        values[:, column, 1] = close
        values[:, column, 2] = close
        values[:, column, 3] = close
        values[:, column, 4] = 10 + column
    return Panel(("BTCUSDT", "ETHUSDT", "SOLUSDT"), timestamps, values, {})


def economics(names: tuple[str, ...]) -> dict[str, SymbolEconomics]:
    funding = np.asarray([[0., .0001], [2000*BAR_MS, -.0001]])
    return {name: SymbolEconomics(.0002, .00055, 2., .001, .001, 5., 100.,
                                  funding, "test") for name in names}


@pytest.mark.parametrize("idea", IDEAS, ids=lambda idea: idea.family)
def test_search004_signals_do_not_use_future_candles(idea: Idea) -> None:
    family = idea.family
    threshold = idea.thresholds[0]
    whole, prefix = panel(1200), panel(800)
    known = economics(whole.symbols)
    left = signal(prefix, family, threshold, known)
    right = signal(whole, family, threshold, known)
    np.testing.assert_array_equal(left, right[:800])
    assert np.all(left[:200] == 0)


def test_search004_folds_are_chronological_and_tail_reserved() -> None:
    entries = folds(panel(1384))
    assert len(entries) == 3
    assert all(row["train_stop"] == row["selection_start"] and
               row["selection_stop"] == row["forward_start"] and
               row["forward_start"] < row["forward_stop"] for row in entries)
    assert entries[-1]["forward_stop"] < 1384


def test_search004_artifacts_are_create_only(tmp_path: Path) -> None:
    path = tmp_path / "new.json"
    _new(path, {"search_id": "004"})
    with pytest.raises(FileExistsError):
        _new(path, {"search_id": "changed"})
