import json

import numpy as np
import pytest

from tradev2.alpha.completion import _family_search, _folds, _gate, _json_bytes
from tradev2.alpha.factors import FactorSpec, signals
from tradev2.alpha.ml import features, fit_signals
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel


def panel_fixture(bars: int = 800) -> tuple[Panel, dict[str, SymbolEconomics]]:
    symbols = ("BTCUSDT", "ETHUSDT", "ALT0USDT", "ALT1USDT", "ALT2USDT", "ALT3USDT")
    times = np.arange(bars, dtype=np.int64) * BAR_MS
    values = np.zeros((bars, len(symbols), 5), dtype=np.float64)
    index = np.arange(bars)
    for column in range(len(symbols)):
        close = 100 + column * 10 + index * (.01 + column * .001) + np.sin(index / (6 + column))
        values[:, column, 0] = close * .999
        values[:, column, 1] = close * 1.002
        values[:, column, 2] = close * .998
        values[:, column, 3] = close
        values[:, column, 4] = 100 + column * 5 + np.sin(index / 4) * 10
    panel = Panel(symbols, times, values, {"dataset_id": "synthetic"})
    funding = np.asarray([[0., .0001], [float(times[-1] + 86_400_000), -.0002]])
    economics = {symbol: SymbolEconomics(.0002, .00055, 3., .001, .001, 5.,
                                         1000., funding, "synthetic") for symbol in symbols}
    return panel, economics


def test_factor_is_closed_bar_and_funding_never_uses_future_settlement() -> None:
    panel, economics = panel_fixture()
    baseline = signals(panel, FactorSpec("btc_lead_lag", 4, .001, 8), economics)
    altered = panel.values.copy()
    altered[700:, :, :4] *= 1.1
    changed = Panel(panel.symbols, panel.timestamps.copy(), altered, panel.manifest)
    candidate = signals(changed, FactorSpec("btc_lead_lag", 4, .001, 8), economics)
    assert np.array_equal(baseline[:699], candidate[:699])
    assert np.isfinite(candidate).all()
    funding_signal = signals(panel, FactorSpec("funding_crowding", 48, .00015, 16), economics)
    assert np.all(funding_signal[:200] == 0)
    assert np.isfinite(funding_signal).all()


def test_ridge_training_is_purged_and_independent_of_future_values() -> None:
    panel, economics = panel_fixture()
    _, fit = fit_signals(panel, features(panel), economics, 7, 500, 10.)
    altered = panel.values.copy()
    altered[500:, :, :4] *= 1.2
    changed = Panel(panel.symbols, panel.timestamps.copy(), altered, panel.manifest)
    _, new_fit = fit_signals(changed, features(changed), economics, 7, 500, 10.)
    assert fit.last_label_end < 500
    assert fit.coefficients == new_fit.coefficients


def test_nested_windows_are_disjoint() -> None:
    panel, economics = panel_fixture(20_159)
    folds = _folds(panel, economics)
    assert len(folds) == 4
    for fold in folds:
        assert (fold["discovery_start"] < fold["discovery_stop"]
                == fold["selection_start"] < fold["selection_stop"]
                == fold["forward_start"] < fold["forward_stop"])
        assert fold["forward_stop"] - fold["forward_start"] == 30 * 96
    assert all(left["forward_stop"] == right["forward_start"]
               for left, right in zip(folds, folds[1:], strict=False))


def test_bad_economics_never_promotes_a_family() -> None:
    row = {"forward": {"trades": 300, "total_net_pnl": -1., "mean_net_r": -.001,
                       "max_fold_drawdown_pct": 1.},
           "folds": [{"forward": {"total_net_pnl": -1.}, "selection_eligible": True}] * 4,
           "bootstrap": {"lower_95": -.1},
           "concentration": {"best_symbol_absolute_share": .2},
           "stress_total_net_pnl": {"wide_costs": -2., "severe_plausible": -3.},
           "parameter_stability": {"neighbor_positive_folds": 0}}
    _gate(row, 1.)
    assert row["status"] == "REJECTED"
    assert not row["historical_gates_passed"]
    assert "nonpositive forward net economics" in row["reasons"]


def test_numpy_scalar_result_is_persistable_without_changing_value() -> None:
    assert _json_bytes({"eligible": np.bool_(True), "score": np.float64(-.1)}) == (
        b'{\n  "eligible": true,\n  "score": -0.1\n}\n')


def test_ridge_refuses_insufficient_temporal_samples() -> None:
    panel, economics = panel_fixture(180)
    with pytest.raises(ValueError, match="insufficient chronological"):
        fit_signals(panel, features(panel), economics, 7, 160, 10.)


@pytest.mark.parametrize("family", ["trend_persistence", "ridge_ohlcv"])
def test_nested_family_search_records_all_trials_on_synthetic_data(family: str) -> None:
    panel, economics = panel_fixture(20_159)
    result = _family_search(panel, economics, family, _folds(panel, economics), 9)
    assert len(result["trials"]) == 8
    assert len(result["folds"]) == 4
    assert result["evaluation_count"] == 24
    assert result["forward"]["days"] == 120
    assert all(row["selection_eligible"] is not None for row in result["folds"])
    assert json.loads(_json_bytes(result))["family"] == family
