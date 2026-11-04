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



def _single(values: np.ndarray, funding: np.ndarray | None = None,
            min_qty: float = .01, min_notional: float = 5) -> tuple[Panel, dict]:
    panel = Panel(("A",), np.arange(len(values), dtype=np.int64) * BAR_MS, values, {})
    rates = funding if funding is not None else np.array([[-BAR_MS, 0], [100 * BAR_MS, 0]])
    return panel, {"A": SymbolEconomics(.0002, .00055, 3, .01, min_qty, min_notional, 10000,
                                        rates, "test")}


def test_open_beyond_target_exits_at_target_not_at_a_later_stop() -> None:
    values = np.ones((10, 1, 5), dtype=float) * 100
    # Bar 4 opens above the long target (about 102.8) and then trades through the stop.
    values[4, 0, :4] = [104, 104, 90, 95]
    panel, economics = _single(values)
    signals = np.zeros((10, 1))
    signals[2, 0] = 1
    trade = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                   economics, 1, 10).trades[0]
    assert trade.exit_reason == "TARGET_AT_OPEN"
    assert trade.gross_pnl > 0
    values = values.copy()  # the panel froze the previous array
    values[4, 0, :4] = [95, 99, 90, 95]  # an adverse gap through the stop fills at the open
    panel, economics = _single(values)
    stopped = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                     economics, 1, 10).trades[0]
    assert stopped.exit_reason == "STOP_FIRST_IF_AMBIGUOUS"
    assert stopped.exit_price < 95.01


def test_funding_inside_a_trade_is_charged_and_off_grid_fails_closed() -> None:
    values = np.ones((12, 1, 5), dtype=float) * 100
    signals = np.zeros((12, 1))
    signals[2, 0] = 1
    paid = np.array([[-BAR_MS, 0], [5 * BAR_MS, .001], [100 * BAR_MS, 0]])
    panel, economics = _single(values, paid)
    trade = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                   economics, 1, 12).trades[0]
    # A long pays positive funding; research Trade.funding is positive when paid.
    assert trade.funding == pytest.approx(trade.quantity * trade.entry_price * .001)
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.fees - trade.funding
                                          - trade.spread - trade.slippage)
    off_grid = np.array([[-BAR_MS, 0], [5 * BAR_MS + 1, .001], [100 * BAR_MS, 0]])
    panel, economics = _single(values, off_grid)
    with pytest.raises(ValueError, match="off the 15m bar grid"):
        replay(panel, candidate_grid()[0], signals, np.zeros_like(signals), economics, 1, 12)


def test_zero_quantity_is_rejected_not_filled() -> None:
    values = np.ones((10, 1, 5), dtype=float) * 100
    panel, _ = _single(values)
    economics = {"A": SymbolEconomics(.0002, .00055, 3, 1000, 0, 0, 10000,
                                      np.array([[-BAR_MS, 0], [100 * BAR_MS, 0]]), "coarse")}
    signals = np.zeros((10, 1))
    signals[2, 0] = 1
    result = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals), economics, 1, 10)
    assert result.trades == []
    assert result.rejections == {"MINIMUM_RISK_REJECT": 1}


def test_regime_label_follows_the_equal_weight_return_index() -> None:
    count = 120
    values = np.ones((count, 2, 5), dtype=float)
    values[:, 0, :4] = 50_000.0  # a flat, high-priced symbol must not dominate the label
    cheap = np.linspace(1.0, 0.8, count)
    values[:, 1, :4] = cheap[:, None]
    panel = Panel(("BIG", "CHEAP"), np.arange(count, dtype=np.int64) * BAR_MS, values, {})
    funding = np.array([[-BAR_MS, 0], [1000 * BAR_MS, 0]])
    economics = {name: SymbolEconomics(.0002, .00055, 3, .0001, .0001, 0.001, 1e9, funding, "t")
                 for name in panel.symbols}
    signals = np.zeros((count, 2))
    signals[110, 0] = 1
    trade = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                   economics, 1, count).trades[0]
    assert trade.regime == "down"


def test_paired_comparison_pairs_common_opportunities_with_missed_as_zero() -> None:
    from tradev2.research.costs import FRICTION

    panel = fixture_panel(60)
    economics = {s: SymbolEconomics(.0002, .00055, 3, .001, .001, 5, 10000,
                  np.array([[-BAR_MS, .0001], [100 * BAR_MS, .0001]]), "synthetic")
                 for s in panel.symbols}
    signals = np.zeros((60, 4))
    for row, column in ((2, 0), (10, 1), (20, 2), (30, 3), (40, 0)):
        signals[row, column] = 1
    base = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                  economics, 1, 60, capture=True)
    treated = replay(panel, candidate_grid()[0], signals, np.zeros_like(signals),
                     economics, 1, 60, FRICTION, capture=True)
    paired = paired_comparison(base, treated)
    common = ({row["opportunity_id"] for row in base.opportunities}
              & {row["opportunity_id"] for row in treated.opportunities})
    base_net = {t.opportunity_id: t.net_pnl for t in base.trades}
    treated_net = {t.opportunity_id: t.net_pnl for t in treated.trades}
    expected = sum(treated_net.get(key, 0.) - base_net.get(key, 0.) for key in common)
    assert paired["common_opportunities"] == len(common)
    assert paired["paired_net_delta"] == pytest.approx(expected)
    assert paired["paired_net_delta"] != 0


def test_legacy_ingestion_is_create_only(tmp_path: Path) -> None:
    from tradev2.research.datasets import ingest_legacy_public

    source = tmp_path / "source"
    source.mkdir()
    minutes = np.array([[i * 60000, 100, 101, 99, 100, 1] for i in range(60)], dtype=float)
    np.save(source / "AUSDT.npy", minutes)
    (source / "manifest.json").write_text('{"AUSDT": {}}', encoding="utf-8")
    target = tmp_path / "target"
    first = ingest_legacy_public(source, target, "rev")
    original = (target / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError, match="immutable"):
        ingest_legacy_public(source, target, "rev2")
    assert (target / "manifest.json").read_bytes() == original
    assert first["bars_per_symbol"] == 4
