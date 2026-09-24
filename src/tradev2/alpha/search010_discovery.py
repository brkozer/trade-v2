"""Discovery-only Search 010: cross-sectional downside-beta defensiveness."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from tradev2.alpha.candidates import Candidate, Family, lag, rolling_mean
from tradev2.alpha.search009_discovery import (
    _aggregate,
    _market_attribution,
    _metric,
    _write_new,
    folds,
)
from tradev2.research.costs import BASE, WIDE, CostScenario, load_economics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel, load_panel, sha256_file
from tradev2.research.replay import Trade, replay
from tradev2.research.statistics import day_block_bootstrap, holm_adjust

SEARCH_ID = "TRADEV2_DISCOVERY_010"
EVIDENCE_ROLE = "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
SEED = 20260924
DAY_MS = 86_400_000
LOOKBACKS = (14 * 96, 28 * 96)
HOLDING_BARS = 96
LEG_COUNT = 2
MIN_DOWNSIDE_FRACTION = 0.20
SEVERE = CostScenario("severe_plausible", 2.0, 3.0, 5.0, 1, 0.5, 3)


def downside_beta(panel: Panel, lookback: int) -> FloatArray:
    """Rolling beta conditional on negative BTC returns, using closed bars only."""
    if lookback not in LOOKBACKS:
        raise ValueError("unregistered Search 010 lookback")
    close = panel.values[:, :, 3]
    returns = close / lag(close, 1) - 1
    btc = returns[:, panel.symbols.index("BTCUSDT")][:, None]
    mask = np.isfinite(btc) & (btc < 0)
    weights = np.broadcast_to(mask, returns.shape).astype(np.float64)
    fraction = rolling_mean(weights, lookback)
    safe_fraction = np.where(fraction > 0, fraction, np.nan)
    btc_matrix = np.broadcast_to(btc, returns.shape)
    mean_y = rolling_mean(np.where(mask, returns, 0), lookback) / safe_fraction
    mean_b = rolling_mean(np.where(mask, btc_matrix, 0), lookback) / safe_fraction
    mean_yb = rolling_mean(np.where(mask, returns * btc, 0), lookback) / safe_fraction
    mean_bb = rolling_mean(np.where(mask, btc_matrix * btc, 0), lookback) / safe_fraction
    covariance = mean_yb - mean_y * mean_b
    variance = mean_bb - mean_b * mean_b
    result: FloatArray = np.asarray(
        np.divide(covariance, variance, out=np.full_like(covariance, np.nan),
                  where=variance > 1e-16), dtype=np.float64)
    result[fraction < MIN_DOWNSIDE_FRACTION] = np.nan
    return result


def signals(panel: Panel, lookback: int) -> FloatArray:
    """Daily long-low/short-high downside-beta altcoin portfolio."""
    feature = downside_beta(panel, lookback)
    result = np.zeros((len(panel.timestamps), len(panel.symbols)), dtype=np.float64)
    excluded = {panel.symbols.index("BTCUSDT"), panel.symbols.index("ETHUSDT")}
    for decision in range(lookback, len(panel.timestamps)):
        entry_ms = int(panel.timestamps[decision]) + BAR_MS
        if entry_ms % DAY_MS:
            continue
        eligible = [index for index in range(len(panel.symbols))
                    if index not in excluded and np.isfinite(feature[decision, index])]
        if len(eligible) < 2 * LEG_COUNT:
            continue
        ordered = sorted(eligible, key=lambda index: (feature[decision, index],
                                                       panel.symbols[index]))
        for rank, index in enumerate(ordered[:LEG_COUNT]):
            result[decision, index] = float(LEG_COUNT - rank)
        for rank, index in enumerate(reversed(ordered[-LEG_COUNT:])):
            result[decision, index] = -float(LEG_COUNT - rank)
    return result


def _candidate(lookback: int) -> Candidate:
    return Candidate(
        f"SEARCH010_DOWNSIDE_BETA_{lookback // 96}D",
        cast(Family, "cross_sectional_downside_beta_defensiveness"),
        lookback,
        float(LEG_COUNT),
        HOLDING_BARS,
        None,
        0.10,
        10.0,
    )


def preregister(root: Path) -> Path:
    dataset = root / "data/public/completion_campaign"
    panel = load_panel(dataset)
    economics_bytes = (dataset / "economics.json").read_bytes()
    economics = load_economics(json.loads(economics_bytes), panel.symbols)
    target = root / "research/manifests/alpha_search_preregistration_010.json"
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
            "family": "cross_sectional_downside_beta_defensiveness",
            "mechanism": "Leverage constraints and forced deleveraging may make altcoins with high conditional BTC downside beta persistently underperform low-downside-beta peers.",
            "discriminator": "Unlike residual trend, total residual variance or positive-tail MAX, this isolates covariance specifically during negative BTC returns.",
            "feature": "rolling covariance beta to BTC using only negative BTC 15-minute returns and at least 20% downside observations",
            "portfolio": "daily long two lowest- and short two highest-downside-beta non-BTC/ETH symbols at equal risk settings",
            "entry": "rank on the prior closed UTC-day bar; execute next open",
            "holding_bars": HOLDING_BARS,
            "lookbacks": list(LOOKBACKS),
            "minimum_downside_fraction": MIN_DOWNSIDE_FRACTION,
            "failure": "downside-beta defensiveness is absent, unstable, concentrated, market-exposed or consumed by turnover",
        },
        "folds": folds(panel, economics),
        "trial_budget": len(LOOKBACKS),
        "planned_evaluations": {"base": 8, "wide": 8, "severe": 8, "total": 24},
        "selection": "no within-search winner selection; both lookbacks evaluated on every forward fold and Holm-corrected",
        "costs": [asdict(value) for value in (BASE, WIDE, SEVERE)],
        "discovery_candidate_gates": {
            "minimum_forward_trades": 200,
            "minimum_symbols": 10,
            "positive_forward_folds": 3,
            "base_wide_severe_aggregate_net_positive": True,
            "other_lookback_positive_folds": 3,
            "bootstrap_lower_above_zero": True,
            "holm_pvalue_max": 0.05,
            "max_symbol_absolute_share": 0.35,
            "max_day_absolute_share": 0.20,
            "max_absolute_btc_daily_beta": 0.25,
            "max_absolute_btc_daily_correlation": 0.30,
        },
        "inference": {"seed": SEED, "draws": 2000, "circular_block_days": 7,
                      "multiplicity": "Holm correction across both frozen lookback variants"},
        "limitations": panel.manifest["limitations"] + json.loads(economics_bytes)["limitations"] + [
            "reused consumed data is not fresh validation",
            "current universe selection creates survivorship bias",
            "conditional beta is an estimated historical exposure, not liquidation telemetry",
            "current fees, spreads and instrument rules approximate history",
            "daily taker turnover is deliberately charged; no maker or queue inference",
        ],
    }
    _write_new(target, payload)
    return target


def run(root: Path) -> dict[str, Any]:
    registration_path = root / "research/manifests/alpha_search_preregistration_010.json"
    result_path = root / "research/results/DISCOVERY_SEARCH_010.json"
    if result_path.exists():
        raise FileExistsError("Search 010 result already consumed")
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
            or frozen["hypothesis"]["lookbacks"] != list(LOOKBACKS)
            or frozen["hypothesis"]["minimum_downside_fraction"] != MIN_DOWNSIDE_FRACTION):
        raise ValueError("Search 010 preregistration or dataset drift")
    zero_exit = np.zeros((len(panel.timestamps), len(panel.symbols)), dtype=np.float64)
    trials: list[dict[str, Any]] = []
    configurations: list[dict[str, Any]] = []
    for lookback in LOOKBACKS:
        current_signals = signals(panel, lookback)
        candidate = _candidate(lookback)
        all_trades: list[Trade] = []
        all_daily: dict[int, float] = {}
        maximum_drawdown = 0.0
        cost_totals = {scenario.name: 0.0 for scenario in (BASE, WIDE, SEVERE)}
        fold_rows: list[dict[str, Any]] = []
        for fold in frozen["folds"]:
            arms: dict[str, dict[str, Any]] = {}
            for scenario in (BASE, WIDE, SEVERE):
                evaluated = replay(panel, candidate, current_signals, zero_exit, economics,
                                   fold["forward_start"], fold["forward_stop"], scenario)
                metric = _metric(evaluated)
                arms[scenario.name] = metric
                cost_totals[scenario.name] += float(metric["total_net_pnl"])
                trials.append({"lookback": lookback, "fold": fold["fold"],
                               "stage": "FORWARD", "cost": scenario.name,
                               "candidate": candidate.payload(),
                               "period": [fold["forward_start"], fold["forward_stop"]],
                               "result": metric})
                if scenario == BASE:
                    all_trades.extend(evaluated.trades)
                    all_daily.update(evaluated.daily_pnl)
                    maximum_drawdown = max(maximum_drawdown,
                                           float(metric["max_drawdown_pct"]))
            fold_rows.append({"fold": fold["fold"], "arms": arms})
        aggregate = _aggregate(all_trades, all_daily, maximum_drawdown)
        bootstrap = asdict(day_block_bootstrap(
            [all_daily[key] for key in sorted(all_daily)], seed=SEED + lookback))
        configurations.append({
            "lookback": lookback,
            "aggregate_base": aggregate,
            "bootstrap": bootstrap,
            "market_attribution": _market_attribution(panel, all_daily),
            "positive_folds": sum(float(row["arms"][BASE.name]["total_net_pnl"]) > 0
                                  for row in fold_rows),
            "cost_total_net_pnl": cost_totals,
            "folds": fold_rows,
        })
    adjusted = holm_adjust([row["bootstrap"]["positive_pvalue"] for row in configurations])
    gates = frozen["discovery_candidate_gates"]
    for index, row in enumerate(configurations):
        aggregate = row["aggregate_base"]
        attribution = row["market_attribution"]
        other = configurations[1 - index]
        row["holm_pvalue"] = adjusted[index]
        row["passed"] = (
            int(aggregate["trades"]) >= int(gates["minimum_forward_trades"])
            and int(aggregate["symbols_traded"]) >= int(gates["minimum_symbols"])
            and int(row["positive_folds"]) >= int(gates["positive_forward_folds"])
            and all(float(value) > 0 for value in row["cost_total_net_pnl"].values())
            and int(other["positive_folds"]) >= int(gates["other_lookback_positive_folds"])
            and row["bootstrap"]["lower_95"] is not None
            and float(row["bootstrap"]["lower_95"]) > 0
            and row["holm_pvalue"] is not None
            and float(row["holm_pvalue"]) <= float(gates["holm_pvalue_max"])
            and float(aggregate["symbol_concentration"] or 0) <= float(gates["max_symbol_absolute_share"])
            and float(aggregate["day_concentration"] or 0) <= float(gates["max_day_absolute_share"])
            and attribution["btc_daily_beta"] is not None
            and abs(float(attribution["btc_daily_beta"])) <= float(gates["max_absolute_btc_daily_beta"])
            and attribution["btc_daily_correlation"] is not None
            and abs(float(attribution["btc_daily_correlation"])) <= float(gates["max_absolute_btc_daily_correlation"])
        )
    survivors = [row for row in configurations if row["passed"]]
    frozen_candidate = None
    if survivors:
        winner = max(survivors, key=lambda row: float(row["aggregate_base"]["mean_net_r"]))
        frozen_candidate = {
            "family": frozen["hypothesis"]["family"],
            "lookback": winner["lookback"],
            "holding_bars": HOLDING_BARS,
            "leg_count": LEG_COUNT,
            "rebalance": "daily 00:00 UTC",
            "execution": frozen["hypothesis"]["entry"],
            "risk": {"stop_pct": 0.10, "target_r": 10.0},
        }
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
        "status": ("DISCOVERY_CANDIDATE_AWAITING_FRESH_VALIDATION" if survivors
                   else "REJECTED_DISCOVERY_ONLY"),
        "configurations": configurations,
        "trials": trials,
        "frozen_candidate": frozen_candidate,
        "promotion": "NONE; discovery-only cannot satisfy fresh validation",
    }
    _write_new(result_path, result)
    _write_new(root / "research/manifests/alpha_search_completion_010.json", {
        "search_id": SEARCH_ID,
        "evidence_role": EVIDENCE_ROLE,
        "result_sha256": sha256_file(result_path),
        "preregistration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "evaluations": len(trials),
        "completed_at": result["finished_at"],
    })
    return result


def write_report(root: Path, result: dict[str, Any]) -> Path:
    path = root / "research/results/DISCOVERY_SEARCH_010.md"
    rows = []
    for row in result["configurations"]:
        aggregate = row["aggregate_base"]
        costs = row["cost_total_net_pnl"]
        rows.append(
            f"| {row['lookback'] // 96}d | {aggregate['trades']} | "
            f"{aggregate['mean_gross_r']:.4f} | {aggregate['mean_net_r']:.4f} | "
            f"{row['positive_folds']}/4 | {costs[BASE.name]:.2f} | "
            f"{costs[WIDE.name]:.2f} | {costs[SEVERE.name]:.2f} | "
            f"{row['holm_pvalue']} | {row['market_attribution']['btc_daily_beta']:.4f} | "
            f"{'PASS' if row['passed'] else 'FAIL'} |"
        )
    text = f"""# Discovery Search 010 — cross-sectional downside-beta defensiveness

Evidence role: **{EVIDENCE_ROLE}**

Search identity: `{SEARCH_ID}`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

This experiment tested whether forced deleveraging makes altcoins with high
conditional BTC downside beta underperform defensive peers. At each UTC day
boundary it ranked non-BTC/ETH symbols by beta estimated only during negative
BTC 15-minute returns, went long the two lowest and short the two highest, and
held one day. Frozen 14- and 28-day lookbacks ran through four disjoint 30-day
forward folds under base, wide and severe costs. There was no outcome-based
winner selection; all 24 evaluations were retained.

## Result

Status: **{result['status']}**

| Lookback | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | BTC beta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(rows)}

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.
"""
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preregister", "run"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    if arguments.action == "preregister":
        print(preregister(arguments.root))
    else:
        completed = run(arguments.root)
        print(write_report(arguments.root, completed))
