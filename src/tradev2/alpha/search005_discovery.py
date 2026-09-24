"""Bounded discovery-only Search 005: persistent funding-settlement carry.

This search deliberately reuses the consumed Search 004 panel. Its output is
never fresh validation and cannot satisfy the prospective acceptance gate.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from tradev2.alpha.candidates import Candidate, Family
from tradev2.alpha.search004 import Idea
from tradev2.alpha.search004_data import load_fresh
from tradev2.research.costs import BASE, WIDE, CostScenario, SymbolEconomics, load_economics
from tradev2.research.datasets import FloatArray, Panel, sha256_file
from tradev2.research.replay import ReplayResult, replay

SEARCH_ID = "TRADEV2_DISCOVERY_005"
EVIDENCE_ROLE = "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
SEVERE = CostScenario("severe_plausible", 2.0, 3.0, 5.0, 1, 0.5, 3)
IDEA = Idea(
    "funding_settlement_carry",
    "Two consecutive same-sign settled funding rates may indicate persistent demand "
    "to hold the paying side; taking the receiving side may collect the next settlement.",
    "two consecutive settled funding signs and the latest absolute settled rate",
    "through the next expected eight-hour settlement",
    "next-bar taker entry and taker exit after 32 bars",
    "price drift and round-trip friction exceed the received funding",
    (0.00005, 0.00010),
    lookback=2,
    holding_bars=32,
    stop_pct=0.025,
    target_r=10.0,
)


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def folds(panel: Panel) -> list[dict[str, int]]:
    """Three expanding selections followed by disjoint two-day forward folds."""
    day = 96
    if len(panel.timestamps) < 12 * day:
        raise ValueError("Search 005 requires at least twelve full days")
    return [
        {
            "fold": index + 1,
            "train_start": 0,
            "train_stop": (3 + 3 * index) * day,
            "selection_start": (3 + 3 * index) * day,
            "selection_stop": (4 + 3 * index) * day,
            "forward_start": (4 + 3 * index) * day,
            "forward_stop": (6 + 3 * index) * day,
        }
        for index in range(3)
    ]


def signal(panel: Panel, economics: dict[str, SymbolEconomics], threshold: float) -> FloatArray:
    """Signal after a settlement bar closes; never infer or use the next rate."""
    if threshold not in IDEA.thresholds:
        raise ValueError("unregistered Search 005 threshold")
    values = np.zeros((len(panel.timestamps), len(panel.symbols)), dtype=np.float64)
    for column, symbol in enumerate(panel.symbols):
        settled = {int(timestamp): float(rate) for timestamp, rate in economics[symbol].funding}
        previous: float | None = None
        for index, opened in enumerate(panel.timestamps):
            current = settled.get(int(opened))
            if current is None:
                continue
            if (previous is not None and current != 0 and np.sign(current) == np.sign(previous)
                    and abs(current) >= threshold):
                # Positive funding is paid by longs, so the receiving side is short.
                values[index, column] = -np.sign(current) * abs(current)
            previous = current
    values[:200] = 0
    return values


def _candidate(threshold: float) -> Candidate:
    return Candidate(
        f"SEARCH005_FUNDING_CARRY_{threshold:.5f}",
        cast(Family, IDEA.family),
        IDEA.lookback,
        threshold,
        IDEA.holding_bars,
        None,
        IDEA.stop_pct,
        IDEA.target_r,
    )


def _metric(result: ReplayResult) -> dict[str, Any]:
    keys = (
        "trades", "mean_net_r", "mean_gross_r", "total_net_pnl", "gross_pnl",
        "fees", "spread", "slippage", "funding", "turnover", "tail_loss_r",
        "max_drawdown_pct", "symbol_concentration", "day_concentration",
        "symbol_net_pnl", "regime_net_pnl", "rejections",
    )
    return {key: result.metrics.get(key) for key in keys}


def preregister(root: Path) -> Path:
    panel = load_fresh(root)
    source = root / "data/public/alpha_search_004"
    target = root / "research/manifests/alpha_search_preregistration_005.json"
    manifest = {
        "schema_version": 1,
        "search_id": SEARCH_ID,
        "evidence_role": EVIDENCE_ROLE,
        "frozen_at": datetime.now(UTC).isoformat(),
        "dataset_id": panel.manifest["dataset_id"],
        "dataset_manifest_sha256": sha256_file(source / "manifest.json"),
        "candles_sha256": sha256_file(source / "candles_15m.npz"),
        "economics_sha256": sha256_file(source / "economics.json"),
        "dataset_prior_consumption": "Consumed by Search 004; reused for discovery only",
        "hypothesis": asdict(IDEA),
        "folds": folds(panel),
        "trial_budget": 2,
        "planned_evaluations": {"selection": 6, "base": 3, "wide": 3, "severe": 3,
                                "neighbor": 3, "total": 18},
        "selection": "highest one-day base-cost mean net R; tie lower threshold",
        "costs": [asdict(value) for value in (BASE, WIDE, SEVERE)],
        "discovery_candidate_gates": {
            "min_forward_trades": 60,
            "positive_forward_folds": 3,
            "base_wide_severe_aggregate_net_positive": True,
            "neighbor_positive_folds": 2,
            "max_symbol_absolute_share": 0.35,
            "max_day_absolute_share": 0.30,
        },
        "multiple_testing": "one family, two thresholds; descriptive only, no inferential claim",
        "limitations": panel.manifest["limitations"] + [
            "reused consumed data is not fresh validation",
            "only six forward days are evaluated",
            "settled funding persistence does not reveal the next funding rate",
            "current spread, fee and instrument rules are not historical snapshots",
            "taker execution only; no queue or maker-fill inference",
        ],
    }
    _write_new(target, manifest)
    return target


def _weighted_mean(metrics: list[dict[str, Any]], field: str) -> float | None:
    count = sum(int(row["trades"]) for row in metrics)
    if count == 0:
        return None
    return sum(float(row[field]) * int(row["trades"]) for row in metrics
               if row[field] is not None) / count


def run(root: Path) -> dict[str, Any]:
    registration_path = root / "research/manifests/alpha_search_preregistration_005.json"
    result_path = root / "research/results/DISCOVERY_SEARCH_005.json"
    if result_path.exists():
        raise FileExistsError("Search 005 result already consumed")
    registration_bytes = registration_path.read_bytes()
    frozen = json.loads(registration_bytes)
    panel = load_fresh(root)
    source = root / "data/public/alpha_search_004"
    if (frozen["search_id"] != SEARCH_ID or frozen["evidence_role"] != EVIDENCE_ROLE
            or frozen["hypothesis"] != json.loads(json.dumps(asdict(IDEA)))
            or sha256_file(source / "manifest.json") != frozen["dataset_manifest_sha256"]
            or sha256_file(source / "candles_15m.npz") != frozen["candles_sha256"]
            or sha256_file(source / "economics.json") != frozen["economics_sha256"]):
        raise ValueError("Search 005 preregistration or dataset drift")
    economics = load_economics(json.loads((source / "economics.json").read_text(
        encoding="utf-8")), panel.symbols)
    zero_exit = np.zeros((len(panel.timestamps), len(panel.symbols)))
    cached = {threshold: signal(panel, economics, threshold) for threshold in IDEA.thresholds}
    trials: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for fold in frozen["folds"]:
        selections: list[tuple[float, float]] = []
        for threshold in IDEA.thresholds:
            candidate = _candidate(threshold)
            evaluated = replay(panel, candidate, cached[threshold], zero_exit, economics,
                               fold["selection_start"], fold["selection_stop"])
            metric = _metric(evaluated)
            trials.append({"fold": fold["fold"], "stage": "SELECTION", "cost": BASE.name,
                           "threshold": threshold, "candidate": candidate.payload(),
                           "period": [fold["selection_start"], fold["selection_stop"]],
                           "result": metric})
            score = float(metric["mean_net_r"]) if metric["mean_net_r"] is not None else -np.inf
            selections.append((score, -threshold))
        winner = max(range(len(selections)), key=lambda index: selections[index])
        selected = IDEA.thresholds[winner]
        candidate = _candidate(selected)
        arms: dict[str, dict[str, Any]] = {}
        for scenario in (BASE, WIDE, SEVERE):
            evaluated = replay(panel, candidate, cached[selected], zero_exit, economics,
                               fold["forward_start"], fold["forward_stop"], scenario)
            arms[scenario.name] = _metric(evaluated)
            trials.append({"fold": fold["fold"], "stage": "FORWARD", "cost": scenario.name,
                           "threshold": selected, "candidate": candidate.payload(),
                           "period": [fold["forward_start"], fold["forward_stop"]],
                           "result": arms[scenario.name]})
        neighbor = IDEA.thresholds[1 - winner]
        neighbor_result = replay(panel, _candidate(neighbor), cached[neighbor], zero_exit,
                                 economics, fold["forward_start"], fold["forward_stop"])
        neighbor_metric = _metric(neighbor_result)
        trials.append({"fold": fold["fold"], "stage": "NEIGHBOR", "cost": BASE.name,
                       "threshold": neighbor, "candidate": _candidate(neighbor).payload(),
                       "period": [fold["forward_start"], fold["forward_stop"]],
                       "result": neighbor_metric})
        results.append({"fold": fold["fold"], "selected_threshold": selected,
                        "arms": arms, "neighbor": neighbor_metric})
    base = [entry["arms"][BASE.name] for entry in results]
    trades = sum(int(row["trades"]) for row in base)
    cost_totals = {scenario.name: sum(float(entry["arms"][scenario.name]["total_net_pnl"])
                                               for entry in results)
                   for scenario in (BASE, WIDE, SEVERE)}
    positive_folds = sum(float(row["total_net_pnl"]) > 0 for row in base)
    neighbor_positive = sum(float(entry["neighbor"]["total_net_pnl"]) > 0 for entry in results)
    max_symbol = max(float(row["symbol_concentration"] or 0) for row in base)
    max_day = max(float(row["day_concentration"] or 0) for row in base)
    gates = frozen["discovery_candidate_gates"]
    passed = (
        trades >= int(gates["min_forward_trades"])
        and positive_folds == int(gates["positive_forward_folds"])
        and all(value > 0 for value in cost_totals.values())
        and neighbor_positive >= int(gates["neighbor_positive_folds"])
        and max_symbol <= float(gates["max_symbol_absolute_share"])
        and max_day <= float(gates["max_day_absolute_share"])
    )
    status = ("DISCOVERY_CANDIDATE_AWAITING_FRESH_VALIDATION" if passed
              else "REJECTED_DISCOVERY_ONLY")
    completed = {
        "schema_version": 1,
        "search_id": SEARCH_ID,
        "complete": True,
        "evidence_role": EVIDENCE_ROLE,
        "finished_at": datetime.now(UTC).isoformat(),
        "dataset": panel.manifest,
        "preregistration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "family": IDEA.family,
        "mechanism": IDEA.mechanism,
        "trial_count": frozen["trial_budget"],
        "evaluation_count": len(trials),
        "status": status,
        "forward_trades": trades,
        "forward_mean_net_r": _weighted_mean(base, "mean_net_r"),
        "forward_mean_gross_r": _weighted_mean(base, "mean_gross_r"),
        "positive_folds": positive_folds,
        "cost_total_net_pnl": cost_totals,
        "neighbor_positive_folds": neighbor_positive,
        "max_symbol_concentration": max_symbol,
        "max_day_concentration": max_day,
        "folds": results,
        "trials": trials,
        "frozen_candidate": _candidate(IDEA.thresholds[0]).payload() if passed else None,
        "promotion": "NONE; discovery-only cannot satisfy fresh validation",
    }
    _write_new(result_path, completed)
    _write_new(root / "research/manifests/alpha_search_completion_005.json", {
        "search_id": SEARCH_ID,
        "evidence_role": EVIDENCE_ROLE,
        "result_sha256": sha256_file(result_path),
        "preregistration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "evaluations": len(trials),
        "completed_at": completed["finished_at"],
    })
    return completed


def write_report(root: Path, result: dict[str, Any]) -> Path:
    path = root / "research/results/DISCOVERY_SEARCH_005.md"
    if path.exists():
        raise FileExistsError("Search 005 report already exists")
    costs = result["cost_total_net_pnl"]
    text = f"""# Discovery Search 005 — funding-settlement carry

Evidence role: **{EVIDENCE_ROLE}**

Search identity: `{SEARCH_ID}`. This bounded search reused the consumed Search
004 panel. It is not fresh validation and cannot satisfy prospective acceptance.

## Frozen mechanism and design

Two consecutive same-sign settled funding rates were treated as a persistence
condition. At the close of the settlement-opening bar, the strategy takes the
funding-receiving side at the next bar open and holds for 32 bars, subject to
the standard portfolio, stop, fee, spread, slippage and funding ledger. Two
absolute-rate thresholds (0.5 and 1.0 bp) were frozen. Three one-day selections
were followed by disjoint two-day forward folds. All 18 planned evaluations
were retained.

## Result

Status: **{result['status']}**

- Forward trades: {result['forward_trades']}
- Mean gross R: {result['forward_mean_gross_r']}
- Mean net R: {result['forward_mean_net_r']}
- Positive folds: {result['positive_folds']}/3
- Base net PnL: {costs[BASE.name]:.6f} USDT
- Wide net PnL: {costs[WIDE.name]:.6f} USDT
- Severe net PnL: {costs[SEVERE.name]:.6f} USDT
- Neighbor-positive folds: {result['neighbor_positive_folds']}/3
- Maximum symbol/day absolute shares: {result['max_symbol_concentration']:.3f} /
  {result['max_day_concentration']:.3f}

No live, testnet, paper or prospective-shadow authority is granted. The exact
fold arms and every selection, forward-cost and neighbor trial are retained in
the machine result.
"""
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
