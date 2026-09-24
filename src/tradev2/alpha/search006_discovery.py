"""Discovery-only Search 006: cost-aware UTC-hour cross-sectional seasonality."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from tradev2.alpha.candidates import Candidate, Family
from tradev2.research.costs import BASE, WIDE, CostScenario, SymbolEconomics, load_economics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel, load_panel, sha256_file
from tradev2.research.replay import ReplayResult, Trade, replay, summarize
from tradev2.research.statistics import day_block_bootstrap

SEARCH_ID = "TRADEV2_DISCOVERY_006"
EVIDENCE_ROLE = "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
SEED = 20260924
HOUR_MS = 3_600_000
HOLDING_BARS = 4
MIN_HOUR_SAMPLES = 45
BUFFERS = (0.0, 0.0010)
SEVERE = CostScenario("severe_plausible", 2.0, 3.0, 5.0, 1, 0.5, 3)


def _write_new(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def folds(panel: Panel, economics: dict[str, SymbolEconomics]) -> list[dict[str, int]]:
    day_ms = 86_400_000
    start_ms = ((int(panel.timestamps[0]) + day_ms - 1) // day_ms) * day_ms
    last_funding = min(int(value.funding[-1, 0]) for value in economics.values())
    end_ms = (min(int(panel.timestamps[-1]) + BAR_MS, last_funding) // day_ms) * day_ms
    outer_days = 30
    fold_count = 4
    inner_days = 30
    discovery_days = (end_ms - start_ms) // day_ms - fold_count * outer_days
    if discovery_days < 60:
        raise ValueError("Search 006 needs at least 60 discovery plus 120 forward days")
    rows: list[dict[str, int]] = []
    for fold in range(fold_count):
        forward_start_ms = start_ms + (discovery_days + fold * outer_days) * day_ms
        selection_start_ms = forward_start_ms - inner_days * day_ms
        forward_stop_ms = forward_start_ms + outer_days * day_ms
        discovery_start, selection_start, forward_start, forward_stop = (
            int(np.searchsorted(panel.timestamps, value))
            for value in (start_ms, selection_start_ms, forward_start_ms, forward_stop_ms)
        )
        if not discovery_start < selection_start < forward_start < forward_stop:
            raise AssertionError("Search 006 windows overlap or are empty")
        rows.append({
            "fold": fold + 1,
            "discovery_start": discovery_start,
            "discovery_stop": selection_start,
            "selection_start": selection_start,
            "selection_stop": forward_start,
            "refit_start": discovery_start,
            "refit_stop": forward_start,
            "forward_start": forward_start,
            "forward_stop": forward_stop,
        })
    return rows


def fit_hourly_edges(panel: Panel, start: int, stop: int) -> tuple[FloatArray, FloatArray]:
    """Fit next-hour returns by UTC entry hour, purging incomplete labels."""
    if not 0 <= start < stop <= len(panel.timestamps):
        raise ValueError("invalid seasonal fit interval")
    sums = np.zeros((24, len(panel.symbols)), dtype=np.float64)
    counts = np.zeros((24, len(panel.symbols)), dtype=np.float64)
    opens = panel.values[:, :, 0]
    for decision in range(start, stop - HOLDING_BARS - 1):
        entry = decision + 1
        exit_index = entry + HOLDING_BARS
        entry_ms = int(panel.timestamps[decision]) + BAR_MS
        if entry_ms % HOUR_MS:
            continue
        hour = (entry_ms // HOUR_MS) % 24
        label = opens[exit_index] / opens[entry] - 1
        finite = np.isfinite(label)
        sums[hour, finite] += label[finite]
        counts[hour, finite] += 1
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    means[counts < MIN_HOUR_SAMPLES] = 0
    # Remove the equal-weight market component for the same UTC hour.
    edges = means - np.mean(means, axis=1, keepdims=True)
    edges[counts < MIN_HOUR_SAMPLES] = 0
    return edges, counts


def _base_roundtrip_cost(economics: SymbolEconomics) -> float:
    return 2 * economics.taker_rate + economics.spread_bps / 10_000 + 2 / 10_000


def signals(panel: Panel, edges: FloatArray, economics: dict[str, SymbolEconomics],
            buffer: float, start: int, stop: int) -> FloatArray:
    if buffer not in BUFFERS or edges.shape != (24, len(panel.symbols)):
        raise ValueError("unregistered Search 006 signal configuration")
    result = np.zeros((len(panel.timestamps), len(panel.symbols)), dtype=np.float64)
    hurdles = np.asarray([_base_roundtrip_cost(economics[symbol]) + buffer
                          for symbol in panel.symbols])
    for decision in range(start, stop):
        entry_ms = int(panel.timestamps[decision]) + BAR_MS
        if entry_ms % HOUR_MS:
            continue
        hour = (entry_ms // HOUR_MS) % 24
        expected = edges[hour]
        result[decision] = np.where(np.abs(expected) >= hurdles, expected, 0)
    return result


def _candidate(buffer: float) -> Candidate:
    return Candidate(
        f"SEARCH006_UTC_HOUR_COST_BUFFER_{int(buffer * 10000)}BP",
        cast(Family, "utc_hour_cross_sectional_seasonality"),
        24,
        buffer,
        HOLDING_BARS,
        None,
        0.025,
        10.0,
    )


def _metric(result: ReplayResult) -> dict[str, Any]:
    keys = (
        "trades", "days", "symbols_traded", "mean_net_r", "mean_gross_r",
        "total_net_pnl", "gross_pnl", "fees", "funding", "spread", "slippage",
        "turnover", "tail_loss_r", "max_drawdown_pct", "symbol_concentration",
        "day_concentration", "symbol_net_pnl", "regime_net_pnl", "rejections",
    )
    return {key: result.metrics.get(key) for key in keys}


def preregister(root: Path) -> Path:
    dataset = root / "data/public/completion_campaign"
    panel = load_panel(dataset)
    economics_bytes = (dataset / "economics.json").read_bytes()
    economics = load_economics(json.loads(economics_bytes), panel.symbols)
    target = root / "research/manifests/alpha_search_preregistration_006.json"
    payload = {
        "schema_version": 1,
        "search_id": SEARCH_ID,
        "evidence_role": EVIDENCE_ROLE,
        "frozen_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "id": panel.manifest["dataset_id"],
            "role": panel.manifest["evidence_role"],
            "prior_consumption": panel.manifest["prior_consumption"],
            "manifest_sha256": sha256_file(dataset / "manifest.json"),
            "candles_sha256": sha256_file(dataset / "candles_15m.npz"),
            "economics_sha256": hashlib.sha256(economics_bytes).hexdigest(),
            "symbols": list(panel.symbols),
            "first_open_ms": int(panel.timestamps[0]),
            "last_open_ms": int(panel.timestamps[-1]),
        },
        "hypothesis": {
            "family": "utc_hour_cross_sectional_seasonality",
            "mechanism": "Recurring global liquidity handoffs may create stable symbol-specific "
                         "one-hour excess returns by UTC hour.",
            "feature": "training-only mean next-hour return by symbol and UTC entry hour, "
                       "demeaned across symbols at that hour",
            "entry": "one signal at each UTC hour boundary; execute next open",
            "holding_bars": HOLDING_BARS,
            "minimum_hour_samples": MIN_HOUR_SAMPLES,
            "cost_buffers": list(BUFFERS),
            "failure": "seasonality is unstable, beta-like, concentrated, or smaller than friction",
        },
        "folds": folds(panel, economics),
        "trial_budget": 2,
        "planned_evaluations": {"inner_selection": 8, "base": 4, "wide": 4,
                                "severe": 4, "neighbor": 4, "total": 24},
        "selection": "highest 30-day inner mean net R with at least 30 trades; tie lower buffer",
        "costs": [asdict(value) for value in (BASE, WIDE, SEVERE)],
        "discovery_candidate_gates": {
            "minimum_forward_trades": 200,
            "minimum_symbols": 10,
            "positive_forward_folds": 3,
            "base_wide_severe_aggregate_net_positive": True,
            "neighbor_positive_folds": 3,
            "bootstrap_lower_above_zero": True,
            "bootstrap_pvalue_max": 0.05,
            "max_symbol_absolute_share": 0.35,
            "max_day_absolute_share": 0.20,
            "same_buffer_selected_folds": 3,
        },
        "inference": {"seed": SEED, "draws": 2000, "circular_block_days": 7,
                      "multiplicity": "one family path; both threshold trials retained"},
        "limitations": panel.manifest["limitations"] + json.loads(economics_bytes)["limitations"] + [
            "reused consumed data is not fresh validation",
            "calendar effects may be nonstationary and exchange-specific",
            "current fee, spread and instrument rules are historical approximations",
            "taker execution only; no maker or queue inference",
        ],
    }
    _write_new(target, payload)
    return target


def _score(result: ReplayResult) -> float:
    value = result.metrics["mean_net_r"]
    return float(value) if len(result.trades) >= 30 and value is not None else -float("inf")


def _aggregate(trades: list[Trade], daily: dict[int, float], max_drawdown: float) -> dict[str, Any]:
    result = summarize(trades, daily)
    result["max_drawdown_pct"] = max_drawdown
    return result


def run(root: Path) -> dict[str, Any]:
    registration_path = root / "research/manifests/alpha_search_preregistration_006.json"
    result_path = root / "research/results/DISCOVERY_SEARCH_006.json"
    if result_path.exists():
        raise FileExistsError("Search 006 result already consumed")
    registration_bytes = registration_path.read_bytes()
    frozen = json.loads(registration_bytes)
    dataset = root / "data/public/completion_campaign"
    panel = load_panel(dataset)
    economics_bytes = (dataset / "economics.json").read_bytes()
    economics = load_economics(json.loads(economics_bytes), panel.symbols)
    if (frozen["search_id"] != SEARCH_ID or frozen["evidence_role"] != EVIDENCE_ROLE
            or sha256_file(dataset / "manifest.json") != frozen["dataset"]["manifest_sha256"]
            or sha256_file(dataset / "candles_15m.npz") != frozen["dataset"]["candles_sha256"]
            or hashlib.sha256(economics_bytes).hexdigest() != frozen["dataset"]["economics_sha256"]
            or frozen["hypothesis"]["cost_buffers"] != list(BUFFERS)):
        raise ValueError("Search 006 preregistration or dataset drift")
    zero_exit = np.zeros((len(panel.timestamps), len(panel.symbols)), dtype=np.float64)
    trials: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    base_trades: list[Trade] = []
    base_daily: dict[int, float] = {}
    max_drawdown = 0.0
    for fold in frozen["folds"]:
        inner_edges, inner_counts = fit_hourly_edges(
            panel, fold["discovery_start"], fold["discovery_stop"])
        ranking: list[tuple[float, float]] = []
        for buffer in BUFFERS:
            candidate = _candidate(buffer)
            current_signals = signals(panel, inner_edges, economics, buffer,
                                      fold["selection_start"], fold["selection_stop"])
            evaluated = replay(panel, candidate, current_signals, zero_exit, economics,
                               fold["selection_start"], fold["selection_stop"])
            metric = _metric(evaluated)
            trials.append({"fold": fold["fold"], "stage": "SELECTION", "cost": BASE.name,
                           "buffer": buffer, "candidate": candidate.payload(),
                           "training_period": [fold["discovery_start"], fold["discovery_stop"]],
                           "period": [fold["selection_start"], fold["selection_stop"]],
                           "minimum_hour_samples_observed": float(inner_counts.min()),
                           "result": metric})
            ranking.append((_score(evaluated), -buffer))
        winner = max(range(len(ranking)), key=lambda index: ranking[index])
        selected = BUFFERS[winner]
        outer_edges, outer_counts = fit_hourly_edges(panel, fold["refit_start"], fold["refit_stop"])
        current_signals = signals(panel, outer_edges, economics, selected,
                                  fold["forward_start"], fold["forward_stop"])
        candidate = _candidate(selected)
        arms: dict[str, dict[str, Any]] = {}
        baseline_result: ReplayResult | None = None
        for scenario in (BASE, WIDE, SEVERE):
            evaluated = replay(panel, candidate, current_signals, zero_exit, economics,
                               fold["forward_start"], fold["forward_stop"], scenario)
            if scenario == BASE:
                baseline_result = evaluated
                base_trades.extend(evaluated.trades)
                base_daily.update(evaluated.daily_pnl)
                max_drawdown = max(max_drawdown, float(evaluated.metrics["max_drawdown_pct"]))
            arms[scenario.name] = _metric(evaluated)
            trials.append({"fold": fold["fold"], "stage": "FORWARD", "cost": scenario.name,
                           "buffer": selected, "candidate": candidate.payload(),
                           "training_period": [fold["refit_start"], fold["refit_stop"]],
                           "period": [fold["forward_start"], fold["forward_stop"]],
                           "minimum_hour_samples_observed": float(outer_counts.min()),
                           "result": arms[scenario.name]})
        if baseline_result is None:
            raise AssertionError("base arm missing")
        neighbor = BUFFERS[1 - winner]
        neighbor_signals = signals(panel, outer_edges, economics, neighbor,
                                   fold["forward_start"], fold["forward_stop"])
        neighbor_result = replay(panel, _candidate(neighbor), neighbor_signals, zero_exit,
                                 economics, fold["forward_start"], fold["forward_stop"])
        neighbor_metric = _metric(neighbor_result)
        trials.append({"fold": fold["fold"], "stage": "NEIGHBOR", "cost": BASE.name,
                       "buffer": neighbor, "candidate": _candidate(neighbor).payload(),
                       "training_period": [fold["refit_start"], fold["refit_stop"]],
                       "period": [fold["forward_start"], fold["forward_stop"]],
                       "result": neighbor_metric})
        rows.append({"fold": fold["fold"], "selected_buffer": selected,
                     "arms": arms, "neighbor": neighbor_metric})
    aggregate = _aggregate(base_trades, base_daily, max_drawdown)
    bootstrap = asdict(day_block_bootstrap([base_daily[key] for key in sorted(base_daily)],
                                           seed=SEED))
    cost_totals = {scenario.name: sum(float(row["arms"][scenario.name]["total_net_pnl"])
                                               for row in rows)
                   for scenario in (BASE, WIDE, SEVERE)}
    selected_counts = Counter(float(row["selected_buffer"]) for row in rows)
    neighbor_positive = sum(float(row["neighbor"]["total_net_pnl"]) > 0 for row in rows)
    positive_folds = sum(float(row["arms"][BASE.name]["total_net_pnl"]) > 0 for row in rows)
    gates = frozen["discovery_candidate_gates"]
    passed = (
        int(aggregate["trades"]) >= int(gates["minimum_forward_trades"])
        and int(aggregate["symbols_traded"]) >= int(gates["minimum_symbols"])
        and positive_folds >= int(gates["positive_forward_folds"])
        and all(value > 0 for value in cost_totals.values())
        and neighbor_positive >= int(gates["neighbor_positive_folds"])
        and bootstrap["lower_95"] is not None and float(bootstrap["lower_95"]) > 0
        and bootstrap["positive_pvalue"] is not None
        and float(bootstrap["positive_pvalue"]) <= float(gates["bootstrap_pvalue_max"])
        and float(aggregate["symbol_concentration"] or 0) <= float(gates["max_symbol_absolute_share"])
        and float(aggregate["day_concentration"] or 0) <= float(gates["max_day_absolute_share"])
        and max(selected_counts.values()) >= int(gates["same_buffer_selected_folds"])
    )
    chosen_buffer = sorted(selected_counts, key=lambda value: (-selected_counts[value], value))[0]
    frozen_model = None
    if passed:
        final_edges, final_counts = fit_hourly_edges(panel, frozen["folds"][0]["discovery_start"],
                                                     frozen["folds"][-1]["forward_stop"])
        frozen_model = {"buffer": chosen_buffer, "edges": final_edges.tolist(),
                        "counts": final_counts.tolist(), "symbols": list(panel.symbols)}
    result = {
        "schema_version": 1,
        "search_id": SEARCH_ID,
        "complete": True,
        "evidence_role": EVIDENCE_ROLE,
        "finished_at": datetime.now(UTC).isoformat(),
        "preregistration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "dataset": frozen["dataset"],
        "family": frozen["hypothesis"]["family"],
        "mechanism": frozen["hypothesis"]["mechanism"],
        "trial_count": frozen["trial_budget"],
        "evaluation_count": len(trials),
        "status": ("DISCOVERY_CANDIDATE_AWAITING_FRESH_VALIDATION" if passed
                   else "REJECTED_DISCOVERY_ONLY"),
        "aggregate_base": aggregate,
        "bootstrap": bootstrap,
        "positive_folds": positive_folds,
        "neighbor_positive_folds": neighbor_positive,
        "selected_buffer_counts": {str(key): value for key, value in selected_counts.items()},
        "cost_total_net_pnl": cost_totals,
        "folds": rows,
        "trials": trials,
        "frozen_candidate": frozen_model,
        "promotion": "NONE; discovery-only cannot satisfy fresh validation",
    }
    _write_new(result_path, result)
    _write_new(root / "research/manifests/alpha_search_completion_006.json", {
        "search_id": SEARCH_ID,
        "evidence_role": EVIDENCE_ROLE,
        "result_sha256": sha256_file(result_path),
        "preregistration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "evaluations": len(trials),
        "completed_at": result["finished_at"],
    })
    return result


def write_report(root: Path, result: dict[str, Any]) -> Path:
    path = root / "research/results/DISCOVERY_SEARCH_006.md"
    aggregate = result["aggregate_base"]
    costs = result["cost_total_net_pnl"]
    text = f"""# Discovery Search 006 — UTC-hour cross-sectional seasonality

Evidence role: **{EVIDENCE_ROLE}**

Search identity: `{SEARCH_ID}`. The 210-day dataset was already consumed by
earlier research. This result is not fresh validation and cannot satisfy the
prospective acceptance gate.

## Frozen mechanism and design

Training-only mean next-hour returns were estimated for every symbol/UTC-hour
cell and demeaned across symbols at that hour. Signals occurred once per hour
and were admitted only when predicted gross excess return cleared the symbol's
base taker/spread/slippage hurdle plus a frozen 0 or 10 bp buffer. Four nested
expanding folds used a 30-day inner selection and the next 30 days as untouched
within-search forward data. All 24 planned evaluations were retained.

## Result

Status: **{result['status']}**

- Forward trades: {aggregate['trades']}
- Symbols traded: {aggregate['symbols_traded']}
- Mean gross/net R: {aggregate['mean_gross_r']} / {aggregate['mean_net_r']}
- Positive folds: {result['positive_folds']}/4
- Base/wide/severe net PnL: {costs[BASE.name]:.6f} /
  {costs[WIDE.name]:.6f} / {costs[SEVERE.name]:.6f} USDT
- Neighbor-positive folds: {result['neighbor_positive_folds']}/4
- Symbol/day concentration: {aggregate['symbol_concentration']} /
  {aggregate['day_concentration']}
- Weekly-block bootstrap 95% interval and positive p-value:
  [{result['bootstrap']['lower_95']}, {result['bootstrap']['upper_95']}],
  p={result['bootstrap']['positive_pvalue']}
- Selected buffer counts: {result['selected_buffer_counts']}

No live, testnet, paper or prospective-shadow authority is granted. The machine
result retains every selection, forward-cost and neighboring-buffer evaluation.
"""
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
