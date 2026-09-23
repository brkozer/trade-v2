"""One-shot, resumable final historical search on explicitly reused public data."""

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from tradev2.alpha.candidates import Candidate, Family
from tradev2.alpha.factors import MECHANISMS, FactorSpec, registry, signals
from tradev2.alpha.ml import HORIZON_BARS, features, fit_signals
from tradev2.research.costs import BASE, WIDE, CostScenario, SymbolEconomics, load_economics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel, load_panel, sha256_file
from tradev2.research.replay import ReplayResult, Trade, paired_comparison, replay, summarize
from tradev2.research.statistics import day_block_bootstrap, holm_adjust

SEARCH_ID = "TRADEV2_FINAL_ALPHA_003"
SEED = 20260923
INNER_DAYS = 20
FORWARD_DAYS = 30
FOLDS = 4
MIN_INNER_TRADES = 30
SEVERE = CostScenario("severe_plausible", 2., 3., 5., 1, .5, 3)
RESULT_NAME = "FINAL_ALPHA_SEARCH_003.json"


def _json_bytes(value: Any) -> bytes:
    def native(item: Any) -> Any:
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(f"non-JSON result type: {type(item).__name__}")

    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False,
                       default=native) + "\n").encode("utf-8")


def _create(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_json_bytes(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _software(root: Path) -> dict[str, Any]:
    paths = ["src/tradev2/alpha/completion.py", "src/tradev2/alpha/factors.py",
             "src/tradev2/alpha/ml.py", "src/tradev2/alpha/candidates.py",
             "src/tradev2/research/replay.py", "src/tradev2/research/costs.py",
             "src/tradev2/research/datasets.py", "src/tradev2/research/statistics.py"]
    files = {name: sha256_file(root / name) for name in paths}
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return {"git_sha": sha, "files": files, "research_code_sha256": _digest(files)}


def _folds(panel: Panel, economics: dict[str, SymbolEconomics]) -> list[dict[str, int]]:
    day_ms = 86_400_000
    start_ms = ((int(panel.timestamps[0]) + day_ms - 1) // day_ms) * day_ms
    last_funding = min(int(e.funding[-1, 0]) for e in economics.values())
    end_ms = (min(int(panel.timestamps[-1]) + BAR_MS, last_funding) // day_ms) * day_ms
    discovery_days = (end_ms - start_ms) // day_ms - FOLDS * FORWARD_DAYS
    if discovery_days < 60:
        raise ValueError("at least 60 discovery plus 120 forward days required")
    rows: list[dict[str, int]] = []
    for fold in range(FOLDS):
        train_stop_ms = start_ms + (discovery_days + fold * FORWARD_DAYS) * day_ms
        inner_start_ms = train_stop_ms - INNER_DAYS * day_ms
        validation_stop_ms = train_stop_ms + FORWARD_DAYS * day_ms
        train_start, inner_start, train_stop, validation_stop = (
            int(np.searchsorted(panel.timestamps, ms))
            for ms in (start_ms, inner_start_ms, train_stop_ms, validation_stop_ms))
        if not train_start < inner_start < train_stop < validation_stop:
            raise AssertionError("walk-forward windows overlap or are empty")
        rows.append({"fold": fold + 1, "discovery_start": train_start,
                     "discovery_stop": inner_start, "selection_start": inner_start,
                     "selection_stop": train_stop, "forward_start": train_stop,
                     "forward_stop": validation_stop,
                     "discovery_start_ms": start_ms, "selection_start_ms": inner_start_ms,
                     "forward_start_ms": train_stop_ms, "forward_stop_ms": validation_stop_ms})
    return rows


def _candidate(spec: FactorSpec) -> Candidate:
    # Existing replay uses a typed immutable candidate envelope; only this new
    # registry supplies the additional family names, never the frozen legacy grid.
    return Candidate(spec.candidate_id, cast(Family, spec.family), spec.lookback,
                     spec.threshold, spec.holding_bars, None, spec.stop_pct, spec.target_r)


def preregistration(root: Path, dataset: Path) -> dict[str, Any]:
    panel = load_panel(dataset)
    economics_bytes = (dataset / "economics.json").read_bytes()
    economics = load_economics(json.loads(economics_bytes), panel.symbols)
    grid = registry()
    return {
        "schema_version": 1, "search_id": SEARCH_ID, "seed": SEED,
        "prior_aborted_search": {"search_id": "TRADEV2_FINAL_ALPHA_002",
                                 "evaluations": 24,
                                 "reason": "NumPy boolean checkpoint serialization failed after first family; no parameters, data, cost or gate changed"},
        "families": MECHANISMS | {"ridge_ohlcv": "Regularized linear prediction of four-bar return, thresholded above execution costs."},
        "parameter_space": [s.payload() for s in grid] + [
            {"family": "ridge_ohlcv", "alpha": a, "horizon_bars": HORIZON_BARS}
            for a in (10., 1000.)],
        "configuration_budget": len(grid) + 2,
        "planned_evaluations": {"inner_selection": (len(grid) + 2) * FOLDS,
                                "forward": (len(MECHANISMS) + 1) * FOLDS,
                                "neighbor_forward": (len(MECHANISMS) + 1) * FOLDS,
                                "stress": (len(MECHANISMS) + 1) * FOLDS * 2},
        "selection_metric": "inner-forward mean net R; minimum 30 trades; tie by candidate ID",
        "validation_design": {"method": "nested expanding discovery / 20-day inner selection / next 30-day outer forward; positions flat at boundaries",
                              "folds": _folds(panel, economics), "purge_bars_for_ml": HORIZON_BARS},
        "cost_scenarios": [asdict(s) for s in (BASE, WIDE, SEVERE)],
        "search_correction": "7-day block bootstrap and Holm over all 14 family forward paths; all 28 configurations disclosed",
        "promotion_gates": {"minimum_forward_trades": 200, "positive_folds": 3,
                            "holm_pvalue_max": .05, "bootstrap_lower_above": 0,
                            "max_drawdown_pct": 10, "max_symbol_absolute_share": .35,
                            "wide_and_severe_net_positive": True,
                            "neighbor_majority_positive": True},
        "dataset": {"id": panel.manifest["dataset_id"], "role": "REUSED_HISTORICAL_DISCOVERY",
                    "manifest_sha256": sha256_file(dataset / "manifest.json"),
                    "candles_sha256": sha256_file(dataset / "candles_15m.npz"),
                    "economics_sha256": hashlib.sha256(economics_bytes).hexdigest(),
                    "first_open_ms": int(panel.timestamps[0]),
                    "last_open_ms": int(panel.timestamps[-1]), "symbols": list(panel.symbols)},
        "holdout_state": "NO_UNTOUCHED_HISTORICAL_HOLDOUT; PROSPECTIVE_PUBLIC_DATA_REQUIRED",
        "limitations": ["previously consumed 2026 public OHLCV and funding; forward folds are not fresh final OOS",
                        "current symbol universe and fee/minimum snapshots may differ historically",
                        "no historical L2 queue or trade-flow data; primary executions are taker/taker",
                        "funding uses settlement timestamps and entry-notional approximation",
                        "OHLC stop takes precedence over ambiguous target", "ML uses OHLCV only"],
        "software": _software(root),
    }


def freeze(root: Path, dataset: Path) -> Path:
    path = root / "research/manifests/final_search_preregistration_003.json"
    _create(path, preregistration(root, dataset) | {"frozen_at": datetime.now(UTC).isoformat()})
    return path


def _score(result: ReplayResult) -> float:
    value = result.metrics["mean_net_r"]
    return float(value) if len(result.trades) >= MIN_INNER_TRADES and value is not None else -float("inf")


def _scenario(result: ReplayResult, baseline: ReplayResult) -> dict[str, Any]:
    return {"metrics": result.metrics, "paired": paired_comparison(baseline, result)}


def _concentration(trades: list[Trade], daily_pnl: dict[int, float]) -> dict[str, float | None]:
    by_symbol: dict[str, float] = defaultdict(float)
    by_regime: dict[str, float] = defaultdict(float)
    for trade in trades:
        by_symbol[trade.symbol] += trade.net_pnl
        by_regime[trade.regime] += trade.net_pnl

    def share(values: list[float], count: int) -> float | None:
        denominator = sum(abs(value) for value in values)
        return sum(sorted((abs(value) for value in values), reverse=True)[:count]) / denominator if denominator else None

    return {"best_symbol_absolute_share": share(list(by_symbol.values()), 1),
            "top_three_symbol_absolute_share": share(list(by_symbol.values()), 3),
            "best_day_absolute_share": share(list(daily_pnl.values()), 1),
            "top_five_day_absolute_share": share(list(daily_pnl.values()), 5),
            "best_regime_absolute_share": share(list(by_regime.values()), 1)}


def _beta_attribution(panel: Panel, days: dict[int, float]) -> dict[str, Any]:
    values = panel.values[:, :, 3]
    result: dict[str, Any] = {"method": "descriptive day-level PnL slope versus BTC/ETH close-to-close returns; not causal or hedged"}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        close = values[:, panel.symbols.index(symbol)]
        daily_close: dict[int, float] = {}
        for index, price in enumerate(close):
            daily_close[int(panel.timestamps[index] // 86_400_000)] = float(price)
        ordered = sorted(daily_close)
        by_day = {today: daily_close[today] / daily_close[yesterday] - 1
                  for yesterday, today in zip(ordered, ordered[1:], strict=False)}
        common = sorted(set(days) & set(by_day))
        strategy = np.asarray([days[day] for day in common])
        market = np.asarray([by_day[day] for day in common])
        variance = float(np.var(market)) if len(common) > 1 else 0.
        result[symbol] = {"days": len(common),
                          "pnl_slope_per_unit_market_return":
                          float(np.cov(market, strategy)[0, 1] / variance)
                          if variance > 1e-12 else None,
                          "correlation": float(np.corrcoef(market, strategy)[0, 1])
                          if variance > 1e-12 and float(np.var(strategy)) > 1e-12 else None}
    return result


def _family_search(panel: Panel, economics: dict[str, SymbolEconomics],
                   family: str, folds: list[dict[str, int]], seed: int) -> dict[str, Any]:
    specs = [spec for spec in registry() if spec.family == family]
    signal_cache = {spec.candidate_id: signals(panel, spec, economics) for spec in specs}
    ml_features = features(panel) if family == "ridge_ohlcv" else None
    exit_marker = np.zeros(panel.values.shape[:2], dtype=np.float64)
    trials: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    all_trades: list[Trade] = []
    all_days: dict[int, float] = {}
    stresses: dict[str, float] = defaultdict(float)
    neighbor_positive = 0
    selected_ids: list[str] = []
    evaluation_count = 0
    for fold in folds:
        inner: list[tuple[float, str, Candidate, FloatArray, dict[str, Any]]] = []
        members: list[tuple[str, Candidate, FloatArray, dict[str, Any]]] = []
        if family == "ridge_ohlcv":
            assert ml_features is not None
            for alpha in (10., 1000.):
                spec = FactorSpec("ridge_ohlcv", 32, alpha, 16)
                candidate = _candidate(spec)
                strength, fitted = fit_signals(panel, ml_features, economics,
                                               fold["discovery_start"], fold["discovery_stop"], alpha)
                members.append((candidate.candidate_id, candidate, strength, asdict(fitted)))
        else:
            members = [(spec.candidate_id, _candidate(spec), signal_cache[spec.candidate_id], {})
                       for spec in specs]
        for identifier, candidate, strength, model in members:
            result = replay(panel, candidate, strength, exit_marker, economics,
                            fold["selection_start"], fold["selection_stop"])
            evaluation_count += 1
            score = _score(result)
            trial = {"fold": fold["fold"], "family": family, "candidate_id": identifier,
                     "parameters": asdict(candidate), "model_fit": model,
                     "phase": "INNER_SELECTION", "score": score if np.isfinite(score) else None,
                     "metrics": result.metrics}
            trials.append(trial)
            inner.append((score, identifier, candidate, strength, model))
        selected = sorted(inner, key=lambda row: (-row[0], row[1]))[0]
        _, identifier, candidate, strength, model = selected
        selected_ids.append(identifier)
        if family == "ridge_ohlcv":
            assert ml_features is not None
            strength, fitted = fit_signals(panel, ml_features, economics,
                                           fold["discovery_start"], fold["forward_start"], candidate.threshold)
            model = asdict(fitted)
        base = replay(panel, candidate, strength, exit_marker, economics,
                      fold["forward_start"], fold["forward_stop"], capture=True)
        evaluation_count += 1
        all_trades.extend(base.trades)
        all_days.update(base.daily_pnl)
        stress_rows: dict[str, Any] = {}
        for scenario in (WIDE, SEVERE):
            other = replay(panel, candidate, strength, exit_marker, economics,
                           fold["forward_start"], fold["forward_stop"], scenario, capture=True)
            evaluation_count += 1
            stress_rows[scenario.name] = _scenario(other, base)
            stresses[scenario.name] += float(other.metrics["total_net_pnl"])
        alternate = next(row for row in inner if row[1] != identifier)
        _, alt_id, alt_candidate, alt_signal, _ = alternate
        if family == "ridge_ohlcv":
            assert ml_features is not None
            alt_signal, _ = fit_signals(panel, ml_features, economics,
                                        fold["discovery_start"], fold["forward_start"], alt_candidate.threshold)
        neighbor = replay(panel, alt_candidate, alt_signal, exit_marker, economics,
                          fold["forward_start"], fold["forward_stop"])
        evaluation_count += 1
        neighbor_positive += neighbor.metrics["total_net_pnl"] > 0
        fold_rows.append({"fold": fold["fold"], "candidate_id": identifier,
                          "selection_eligible": np.isfinite(selected[0]),
                          "inner_score": selected[0] if np.isfinite(selected[0]) else None,
                          "fit": model, "forward": base.metrics,
                          "stress": stress_rows,
                          "neighbor": {"candidate_id": alt_id, "metrics": neighbor.metrics},
                          "opportunities": len(base.opportunities)})
        print(f"{family} fold {fold['fold']}: {identifier}, "
              f"trades={len(base.trades)}, net={base.metrics['total_net_pnl']:.2f}", flush=True)
    forward = summarize(all_trades, all_days)
    forward["max_fold_drawdown_pct"] = max(row["forward"]["max_drawdown_pct"] for row in fold_rows)
    bootstrap = asdict(day_block_bootstrap(list(all_days.values()), seed=seed))
    return {"family": family, "mechanism": (MECHANISMS | {"ridge_ohlcv":
            "Ridge OHLCV return forecast clears a declared cost hurdle."})[family],
            "trials": trials, "folds": fold_rows, "selected_candidates": selected_ids,
            "forward": forward, "daily_pnl": all_days,
            "discovery": {"inner_selection_trades": sum(t["metrics"]["trades"] for t in trials),
                          "eligible_trials": sum(t["score"] is not None for t in trials),
                          "note": "overlapping inner periods; descriptive, not independent forward evidence"},
            "stress_total_net_pnl": dict(stresses),
            "parameter_stability": {"distinct_selected": len(set(selected_ids)),
                                    "neighbor_positive_folds": neighbor_positive,
                                    "neighbor_folds": len(folds)},
            "concentration": _concentration(all_trades, all_days),
            "beta_attribution": _beta_attribution(panel, all_days),
            "bootstrap": bootstrap, "evaluation_count": evaluation_count}


def _gate(family: dict[str, Any], adjusted_p: float | None) -> None:
    m = family["forward"]
    failures: list[str] = []
    if m["trades"] < 200:
        failures.append("fewer than 200 forward trades")
    if m["total_net_pnl"] <= 0 or m["mean_net_r"] is None or m["mean_net_r"] <= 0:
        failures.append("nonpositive forward net economics")
    if sum(row["forward"]["total_net_pnl"] > 0 for row in family["folds"]) < 3:
        failures.append("fewer than three positive forward folds")
    if family["bootstrap"]["lower_95"] is None or family["bootstrap"]["lower_95"] <= 0:
        failures.append("day-block lower confidence bound not positive")
    if adjusted_p is None or adjusted_p > .05:
        failures.append("Holm-adjusted family test not significant")
    if m["max_fold_drawdown_pct"] > 10:
        failures.append("fold drawdown above 10%")
    share = family["concentration"]["best_symbol_absolute_share"]
    if share is None or share > .35:
        failures.append("symbol contribution concentrated")
    if any(value <= 0 for value in family["stress_total_net_pnl"].values()):
        failures.append("wide or severe execution stress loses money")
    if family["parameter_stability"]["neighbor_positive_folds"] < 3:
        failures.append("neighboring parameter/model not positive in three folds")
    if any(not row["selection_eligible"] for row in family["folds"]):
        failures.append("inner selection lacks minimum trades")
    family["adjusted_pvalue"] = adjusted_p
    family["historical_gates_passed"] = not failures
    family["status"] = "INSUFFICIENT_EVIDENCE" if m["trades"] < 200 else "REJECTED" if failures else "PROSPECTIVE_SHADOW"
    family["reasons"] = failures + ["previously consumed source history is not an untouched final holdout"]


def _report(result: dict[str, Any]) -> str:
    budget = result["search_budget"]
    dataset = result["dataset"]
    lines = ["# Final Alpha Factory historical search", "",
             f"Search `{SEARCH_ID}` is complete. This is **reused historical discovery**, not a fresh final holdout.",
             "No result below establishes a deployable edge or authorizes live/testnet trading.", "",
             f"Dataset `{dataset['id']}`: {len(dataset['symbols'])} symbols; candles SHA-256 "
             f"`{dataset['candles_sha256']}`; economics SHA-256 `{dataset['economics_sha256']}`.",
             f"Coverage in UTC milliseconds: {dataset['first_open_ms']} to {dataset['last_open_ms']} (bar opens).",
             f"{budget['configurations']} configurations, {budget['selection_evaluations']} recorded inner trials, "
             f"{budget['total_replays']} total replay evaluations, 14 economically distinct families.",
             "Four nested expanding folds each use a 20-day inner selection interval and a following 30-day forward interval.",
             "ML labels end before each training boundary; an outer fold never selects its own parameters.",
             "Seven-day block bootstrap and Holm adjustment cover all 14 family paths; prior campaigns add selection history.", "",
             "Primary execution is taker/taker with measured/current symbol-specific fees, spread, minimums, "
             "one basis point per-side slippage, settled funding, and next-open availability.",
             "Wide and severe scenarios worsen fees/spread/slippage; severe also delays and misses/partials fills.",
             "Maker non-fill and queue priority cannot be inferred from these OHLCV bars.", "",
             "| Family | Forward trades | Net R/trade | Net USDT | Cost USDT | Positive folds | Wide net | Severe net | Status |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in result["families"]:
        m = row["forward"]
        cost = sum(float(m[key]) for key in ("fees", "funding", "spread", "slippage"))
        positive = sum(f["forward"]["total_net_pnl"] > 0 for f in row["folds"])
        mean_r = "Unknown" if m["mean_net_r"] is None else f"{m['mean_net_r']:.4f}"
        lines.append(f"| {row['family']} | {m['trades']} | {mean_r} | {m['total_net_pnl']:.2f} | "
                     f"{cost:.2f} | {positive}/4 | {row['stress_total_net_pnl']['wide_costs']:.2f} | "
                     f"{row['stress_total_net_pnl']['severe_plausible']:.2f} | {row['status']} |")
    lines += ["", "## Candidate decisions", ""]
    for row in result["families"]:
        lines.append(f"- `{row['family']}` — **{row['status']}**: {'; '.join(row['reasons'])}. "
                     f"Selected {row['selected_candidates']}; Holm p={row['adjusted_pvalue']}; "
                     f"best-symbol absolute share={row['concentration']['best_symbol_absolute_share']}; "
                     f"neighbor positive folds={row['parameter_stability']['neighbor_positive_folds']}/4.")
    lines += ["", "Beta slopes/correlations, regime and day attribution, complete inner trials, fold costs, "
              "paired stress comparisons and model coefficients are retained in the JSON artifact.",
              f"Promoted to prospective shadow: {result['promoted_candidates'] or 'NONE'}.",
              "Historical no-survivor status does not end prospective data collection.", ""]
    return "\n".join(lines)


def run(root: Path, dataset: Path) -> dict[str, Any]:
    prereg_path = root / "research/manifests/final_search_preregistration_003.json"
    frozen = json.loads(prereg_path.read_text(encoding="utf-8"))
    expected = preregistration(root, dataset)
    for name, value in expected.items():
        if name == "software":
            if value["research_code_sha256"] != frozen[name]["research_code_sha256"]:
                raise ValueError("completion research code changed after freeze")
        elif frozen.get(name) != value:
            raise ValueError(f"preregistration/dataset drift: {name}")
    result_path = root / "research/results" / RESULT_NAME
    if result_path.exists():
        raise FileExistsError("completed final search is immutable")
    marker = root / "research/manifests/final_search_consumption_003.json"
    identity = {"search_id": SEARCH_ID, "preregistration_sha256": sha256_file(prereg_path),
                "research_code_sha256": expected["software"]["research_code_sha256"]}
    if marker.exists():
        prior = json.loads(marker.read_text(encoding="utf-8"))
        if any(prior[key] != value for key, value in identity.items()):
            raise ValueError("consumed search identity mismatch")
    else:
        _create(marker, identity | {"started_at": datetime.now(UTC).isoformat()})
    panel = load_panel(dataset)
    economics = load_economics(json.loads((dataset / "economics.json").read_text()), panel.symbols)
    families: list[dict[str, Any]] = []
    checkpoint_dir = root / "data/public/final_campaign_003/checkpoints"
    for family_index, family_name in enumerate(expected["families"]):
        checkpoint = checkpoint_dir / f"{family_name}.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if saved["identity"] != identity:
                raise ValueError("checkpoint identity mismatch")
            family = cast(dict[str, Any], saved["family"])
        else:
            family = _family_search(panel, economics, family_name,
                                    expected["validation_design"]["folds"], SEED + family_index)
            _create(checkpoint, {"identity": identity, "family": family})
        families.append(family)
    adjusted = holm_adjust([family["bootstrap"]["positive_pvalue"] for family in families])
    for family, pvalue in zip(families, adjusted, strict=True):
        _gate(family, pvalue)
    viable = sorted((family for family in families if family["historical_gates_passed"]),
                    key=lambda row: (-row["forward"]["mean_net_r"], row["family"]))
    promoted = [row["family"] for row in viable[:3]]
    for row in viable[3:]:
        row["status"] = "REJECTED"
        row["reasons"].append("maximum three prospectively testable candidates")
    result = {"schema_version": 1, "search_id": SEARCH_ID, "complete": True,
              "generated_at": datetime.now(UTC).isoformat(),
              "preregistration_sha256": sha256_file(prereg_path),
              "software": frozen["software"], "dataset": frozen["dataset"],
              "validation_design": frozen["validation_design"],
              "cost_assumptions": {"scenarios": frozen["cost_scenarios"],
                                   "economics_sha256": frozen["dataset"]["economics_sha256"]},
              "search_budget": {"configurations": frozen["configuration_budget"],
                                "selection_evaluations": sum(len(row["trials"]) for row in families),
                                "total_replays": sum(row["evaluation_count"] for row in families),
                                "planned": frozen["planned_evaluations"]},
              "multiple_testing": frozen["search_correction"],
              "families": families, "promoted_candidates": promoted,
              "final_holdout_state": frozen["holdout_state"],
              "limitations": frozen["limitations"]}
    _create(result_path, result)
    report_path = root / "research/results/FINAL_ALPHA_SEARCH.md"
    with report_path.open("x", encoding="utf-8", newline="\n") as report:
        report.write(_report(result))
    _create(root / "research/manifests/final_search_completion_003.json",
            {"search_id": SEARCH_ID, "completed_at": result["generated_at"],
             "result_sha256": sha256_file(result_path),
             "configurations": result["search_budget"]["configurations"],
             "evaluations": result["search_budget"]["total_replays"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = (args.dataset or root / "data/public/completion_campaign").resolve()
    if args.freeze:
        print(freeze(root, dataset))
    else:
        result = run(root, dataset)
        print(json.dumps({"search_id": result["search_id"],
                          "evaluations": result["search_budget"]["total_replays"],
                          "outcomes": {row["family"]: row["status"] for row in result["families"]}},
                         indent=2))


if __name__ == "__main__":
    main()
