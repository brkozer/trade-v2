from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from tradev2.alpha.campaign import freeze, preregistration
from tradev2.alpha.candidates import candidate_grid, decisions, rsi_series
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import BAR_MS, Panel, aggregate_minutes
from tradev2.research.replay import money, paired_comparison, replay
from tradev2.research.statistics import day_block_bootstrap, holm_adjust
from tradev2.strategies.reference import wilder_rsi


def fixture_panel(count: int = 400) -> Panel:
    rng = np.random.default_rng(41)
    close = 100 * np.exp(np.cumsum(rng.normal(0, .005, (count, 4)), axis=0))
    values = np.stack((close, close * 1.001, close * .999, close,
                       np.ones_like(close) * 100), axis=2)
    return Panel(('A', 'B', 'C', 'D'), np.arange(count, dtype=np.int64) * BAR_MS, values, {})


def test_all_eighteen_candidates_are_prefix_causal() -> None:
    panel = fixture_panel()
    prefix = Panel(panel.symbols, panel.timestamps[:300].copy(), panel.values[:300].copy(), {})
    assert len(candidate_grid()) == 18
    for candidate in candidate_grid():
        full, _ = decisions(panel, candidate)
        partial, _ = decisions(prefix, candidate)
        np.testing.assert_array_equal(full[:300], partial)


def test_reference_scalar_vector_prefix_parity() -> None:
    close = fixture_panel().values[:, :, 3]
    for period in (4, 5):
        vector = rsi_series(close, period)
        for index in range(1, len(close)):
            assert vector[index, 0] == pytest.approx(wilder_rsi(close[:index + 1, 0], period))


def test_replay_next_open_costs_and_funding_unknown() -> None:
    panel = fixture_panel(20)
    economics = {s: SymbolEconomics(.0002, .00055, 3, .001, .001, 5, 10000,
                  np.array([[-BAR_MS, .0001], [100 * BAR_MS, .0001]]), 'synthetic')
                 for s in panel.symbols}
    signals = np.zeros((20, 4))
    signals[2, 0] = 1
    result = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals), economics, 1, 20, capture=True)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.decision_ms == trade.entry_ms == 3 * BAR_MS
    assert trade.entry_price != panel.values[2, 0, 3]
    assert trade.fees > 0 and trade.spread > 0 and trade.slippage > 0
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.fees - trade.funding - trade.spread - trade.slippage)
    assert paired_comparison(result, result)['paired_net_delta'] == 0
    assert money(.1) + money(.2) == Decimal('.3')
    economics['A'] = SymbolEconomics(.0002, .00055, 3, .001, .001, 5, 10000,
                                    np.array([[0, .0001], [5 * BAR_MS, .0001]]), 'short')
    with pytest.raises(ValueError, match='coverage incomplete'):
        replay(panel, candidate_grid()[0], signals, signals, economics, 1, 20)


def test_minute_gaps_rejected_and_outer_bin_trimmed() -> None:
    raw = np.array([[i * 60000, 1, 2, .5, 1, 10] for i in range(31)], dtype=float)
    assert aggregate_minutes(raw).shape == (2, 6)
    raw[10, 0] += 60000
    with pytest.raises(ValueError, match='consecutive'):
        aggregate_minutes(raw)


def test_inference_reproducible_and_multiplicity_retained() -> None:
    a = day_block_bootstrap(list(range(-60, 60)), seed=4)
    assert a == day_block_bootstrap(list(range(-60, 60)), seed=4)
    assert a.lower_95 is not None and a.lower_95 < 0
    assert holm_adjust([.01, .03, None]) == [.03, .06, None]


def test_ambiguous_bar_stop_first_and_minimum_rejection() -> None:
    values = np.ones((10, 1, 5), dtype=float) * 100
    values[3, 0, 1:3] = [110, 90]
    panel = Panel(('A',), np.arange(10, dtype=np.int64) * BAR_MS, values, {})
    signals = np.zeros((10, 1))
    signals[2, 0] = 1
    funding = np.array([[-BAR_MS, 0], [100 * BAR_MS, 0]])
    eco = SymbolEconomics(.0002, .00055, 3, .01, .01, 5, 10000, funding, 'test')
    result = replay(panel, candidate_grid()[0], signals, signals, {'A': eco}, 1, 10)
    assert result.trades[0].exit_reason == 'STOP_FIRST_IF_AMBIGUOUS'
    assert result.trades[0].net_pnl < 0
    rejected_eco = SymbolEconomics(.0002, .00055, 3, .01, .01, 100000, 10000, funding, 'test')
    rejected = replay(panel, candidate_grid()[0], signals, signals, {'A': rejected_eco}, 1, 10)
    assert not rejected.trades
    assert rejected.rejections == {'MINIMUM_RISK_REJECT': 1}


def test_preregistration_cannot_be_overwritten(tmp_path: Path) -> None:
    manifest = tmp_path / 'research/manifests/initial_campaign_preregistration.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"previous_search":"consumed"}', encoding='utf-8')
    with pytest.raises(FileExistsError, match='immutable'):
        freeze(tmp_path, tmp_path)
    assert 'consumed' in manifest.read_text(encoding='utf-8')
    declaration = preregistration()
    assert declaration['configuration_budget'] == len(declaration['candidates']) == 18
    assert declaration['promotion_gates']['required_fresh_independent_evidence']
