"""Preregistered, one-shot Search 004 on new post-003 public observations.

This short slice is research evidence, never sufficient by itself for promotion.
No previously consumed result is opened for optimization or overwritten.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from tradev2.alpha.candidates import Candidate, Family, lag, rolling_mean
from tradev2.alpha.search004_data import SEARCH_ID, load_fresh
from tradev2.research.costs import BASE, WIDE, CostScenario, load_economics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel, sha256_file
from tradev2.research.replay import ReplayResult, replay

SEVERE = CostScenario("severe_plausible", 2., 3., 5., 1, .5, 3)
MIN_PROMOTION_DAYS = 28  # independent daily blocks needed even to estimate uncertainty
MAX_PROMOTIONS = 3


@dataclass(frozen=True)
class Idea:
    family: str
    mechanism: str
    observable: str
    horizon: str
    execution: str
    failure: str
    thresholds: tuple[float, float]
    lookback: int = 48
    holding_bars: int = 8
    stop_pct: float = .025
    target_r: float = 1.5


IDEAS = (
    Idea("breadth_transition", "A broad directional participation shock may persist across the next sessions.",
         "closed 8-bar cross-sectional returns and breadth", "2h", "next-bar taker",
         "broad impulse immediately mean-reverts", (.65, .75)),
    Idea("dispersion_exhaustion", "Exceptional relative dispersion may represent temporary forced deleveraging.",
         "closed 4-bar return dispersion versus lagged 48-bar baseline", "2h", "next-bar taker",
         "new information makes dispersion persistent", (1.4, 1.8)),
    Idea("volatility_term_release", "Volatility compression followed by a jump may indicate a new information regime.",
         "closed 8/48-bar realized absolute returns and current move", "3h", "next-bar taker",
         "jump is a one-bar liquidation wick", (.65, .85), holding_bars=12),
    Idea("funding_price_disagreement", "A newly settled crowded side with opposite price drift may unwind.",
         "last settled funding and closed 4-bar return", "2h", "next-bar taker",
         "funding sign does not proxy positioning", (.00015, .00030)),
    Idea("volume_breadth_confirmation", "Broad directional flow with broad volume participation may underreact.",
         "closed cross-sectional breadth and volume relative to lagged 48 bars", "2h", "next-bar taker",
         "volume is uninformed churn", (1.2, 1.6)),
    Idea("residual_trend_low_beta", "Idiosyncratic drift with low market beta may persist independent of BTC.",
         "closed BTC returns, lagged beta and residual momentum", "3h", "next-bar taker",
         "residual estimate is unstable or BTC beta dominates", (.008, .014), holding_bars=12),
)

UNSUPPORTED = {
    "multi_horizon_trend_continuation": "Earlier trend paths consumed; no distinct untested mechanism specified",
    "pullback_in_trend": "Earlier trend pullback paths consumed",
    "volatility_breakout": "Earlier range breakout paths consumed",
    "volatility_expansion_continuation": "Earlier expansion paths consumed",
    "volatility_expansion_reversal": "Only one short fresh regime; insufficient volatility episodes",
    "short_term_cross_sectional_reversal": "Earlier reversal paths consumed",
    "cross_sectional_momentum": "Earlier momentum paths consumed",
    "btc_residual_reversion": "Earlier BTC residual paths consumed",
    "btc_eth_residual_model": "Earlier two-factor residual paths consumed",
    "lead_lag_relationships": "Earlier BTC lead-lag paths consumed",
    "orderbook_imbalance": "Only seconds-long prospective book samples, no matched outcomes",
    "trade_flow_imbalance": "Only seconds-long prospective trade samples, no matched outcomes",
    "depth_asymmetry": "Only collection-time depth, no historical depth sequence",
    "short_horizon_microstructure": "Seconds-long recorder samples cannot support chronological folds",
    "maker_adverse_selection": "No calibrated queue position or maker fill outcomes",
    "spread_liquidity_conditioned": "Historical point-in-time spread/depth series unavailable",
    "meta_labeling": "No independent labeled fill/outcome sample of adequate duration",
    "candidate_ranking": "Too few independent prospective folds to train and validate a meta-ranker",
}


def _settled_rates(panel: Panel, economics: dict[str, Any]) -> FloatArray:
    result = np.zeros((len(panel.timestamps), len(panel.symbols)))
    close_times = panel.timestamps + BAR_MS
    for column, symbol in enumerate(panel.symbols):
        history = economics[symbol].funding
        index = np.searchsorted(history[:, 0], close_times, side="right") - 1
        if np.any(index < 0):
            raise ValueError("funding unavailable before decision")
        result[:, column] = history[index, 1]
    return result


def signal(panel: Panel, family: str, threshold: float,
           economics: dict[str, Any]) -> FloatArray:
    close, volume = panel.values[:, :, 3], panel.values[:, :, 4]
    ret = close / lag(close, 1) - 1
    r4 = close / lag(close, 4) - 1
    r8 = close / lag(close, 8) - 1
    if family == "breadth_transition":
        breadth = np.mean(r8 > 0, axis=1)[:, None]
        direction = np.where(breadth >= threshold, 1.,
                    np.where(breadth <= 1-threshold, -1., 0.))
        value = np.where((np.abs(r8) < .03) & (np.abs(r8) > .002),
                         direction * np.abs(r8), 0.)
    elif family == "dispersion_exhaustion":
        dispersion = np.std(r4, axis=1)[:, None]
        baseline = lag(rolling_mean(np.broadcast_to(dispersion, r4.shape), 48), 1)
        edge = r4 - np.mean(r4, axis=1)[:, None]
        value = np.where((dispersion > threshold * baseline) &
                         (np.abs(edge) > .008), -edge, 0.)
    elif family == "volatility_term_release":
        recent = lag(rolling_mean(np.abs(ret), 8), 1)
        baseline = lag(rolling_mean(np.abs(ret), 48), 1)
        value = np.where((recent < threshold * baseline) &
                         (np.abs(ret) > .006), ret, 0.)
    elif family == "funding_price_disagreement":
        funding = _settled_rates(panel, economics)
        value = np.where((np.abs(funding) >= threshold) &
                         (np.sign(funding) != np.sign(r4)) & (np.abs(r4) > .003),
                         -funding, 0.)
    elif family == "volume_breadth_confirmation":
        typical = lag(rolling_mean(volume, 48), 1)
        participation = volume / typical
        breadth = np.mean((r4 > 0) & (participation > threshold), axis=1)[:, None]
        negative = np.mean((r4 < 0) & (participation > threshold), axis=1)[:, None]
        value = np.where(breadth >= .55, np.maximum(r4, 0),
                         np.where(negative >= .55, np.minimum(r4, 0), 0.))
    elif family == "residual_trend_low_beta":
        btc = ret[:, panel.symbols.index("BTCUSDT")][:, None]
        beta = lag((rolling_mean(ret*btc, 48) - rolling_mean(ret, 48)*rolling_mean(btc, 48)) /
                   (rolling_mean(btc*btc, 48) - rolling_mean(btc, 48)**2), 1)
        residual = ret - beta*btc
        residual_move = rolling_mean(residual, 8)*8
        value = np.where((np.abs(beta) < 1.5) & (np.abs(residual_move) >= threshold),
                         residual_move, 0.)
        value[:, panel.symbols.index("BTCUSDT")] = 0
    else:
        raise ValueError("unregistered Search 004 family")
    value = np.asarray(value, dtype=np.float64)
    value[~np.isfinite(value)] = 0
    value[:200] = 0
    return value


def folds(panel: Panel) -> list[dict[str, int]]:
    # Three expanding discovery windows, each with a one-day inner selection and
    # two-day frozen forward window; the remaining tail is uninspected/reserved.
    day = 96
    if len(panel.timestamps) < 12*day:
        raise ValueError("Search 004 requires at least twelve fresh full days")
    return [{"fold": index+1, "train_start": 0,
             "train_stop": (3+3*index)*day,
             "selection_start": (3+3*index)*day,
             "selection_stop": (4+3*index)*day,
             "forward_start": (4+3*index)*day,
             "forward_stop": (6+3*index)*day}
            for index in range(3)]


def _new(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def preregister(root: Path) -> Path:
    panel = load_fresh(root)
    target = root / "research/manifests/alpha_search_preregistration_004.json"
    if target.exists():
        raise FileExistsError("Search 004 registration is immutable")
    source = root / "data/public/alpha_search_004"
    manifest = {"search_id": SEARCH_ID, "frozen_at": datetime.now(UTC).isoformat(),
        "dataset_id": panel.manifest["dataset_id"],
        "dataset_manifest_sha256": sha256_file(source / "manifest.json"),
        "candles_sha256": sha256_file(source / "candles_15m.npz"),
        "economics_sha256": sha256_file(source / "economics.json"),
        "first_open_ms": int(panel.timestamps[0]), "last_open_ms": int(panel.timestamps[-1]),
        "symbols": list(panel.symbols), "families": [asdict(idea) for idea in IDEAS],
        "unsupported_plans": UNSUPPORTED, "folds": folds(panel),
        "trial_budget": len(IDEAS)*2,
        "planned_evaluations": {"selection": len(IDEAS)*2*3, "forward": len(IDEAS)*3,
            "wide": len(IDEAS)*3, "severe": len(IDEAS)*3,
            "neighbor": len(IDEAS)*3},
        "selection": "highest one-day net R among two preregistered thresholds; tie lower threshold",
        "costs": [asdict(value) for value in (BASE, WIDE, SEVERE)],
        "promotion_gates": {"min_forward_trades": 200, "min_positive_folds": 3,
            "min_independent_forward_days": MIN_PROMOTION_DAYS,
            "base_wide_severe_net_positive": True, "neighbor_majority_positive": True,
            "max_symbol_absolute_share": .35, "max_day_absolute_share": .30,
            "max_promotions": MAX_PROMOTIONS},
        "multiple_testing": "six family paths; no inferential claim with fewer than 28 independent days",
        "prior_searches": ["TRADEV2_INITIAL_ALPHA", "TRADEV2_FINAL_ALPHA_002_ABORTED",
                           "TRADEV2_FINAL_ALPHA_003"],
        "limitations": panel.manifest["limitations"] +
            ["14-day fresh slice cannot satisfy 28 independent forward days",
             "no calibrated historical queue/maker adverse selection"]}
    _new(target, manifest)
    return target


def _candidate(idea: Idea, threshold: float) -> Candidate:
    return Candidate(f"SEARCH004_{idea.family}_{threshold:g}",
                     cast(Family, idea.family), idea.lookback, threshold,
                     idea.holding_bars, None, idea.stop_pct, idea.target_r)


def _metric(result: ReplayResult) -> dict[str, Any]:
    return {key: result.metrics.get(key) for key in ("trades", "mean_net_r", "total_net_pnl",
        "fees", "spread", "slippage", "funding", "max_drawdown_pct",
        "symbol_concentration", "day_concentration", "regime_net_pnl", "rejections")}


def run(root: Path) -> dict[str, Any]:
    prereg_path = root / "research/manifests/alpha_search_preregistration_004.json"
    result_path = root / "research/results/ALPHA_SEARCH_004.json"
    if result_path.exists():
        raise FileExistsError("Search 004 result already consumed")
    prereg_bytes = prereg_path.read_bytes()
    frozen = json.loads(prereg_bytes)
    panel = load_fresh(root)
    source = root / "data/public/alpha_search_004"
    if (sha256_file(source / "manifest.json") != frozen["dataset_manifest_sha256"]
            or sha256_file(source / "candles_15m.npz") != frozen["candles_sha256"]
            or sha256_file(source / "economics.json") != frozen["economics_sha256"]
            or frozen["families"] != json.loads(json.dumps([asdict(idea) for idea in IDEAS]))):
        raise ValueError("Search 004 preregistration or dataset drift")
    economics = load_economics(json.loads((source / "economics.json").read_text(
        encoding="utf-8")), panel.symbols)
    zero_exit = np.zeros((len(panel.timestamps), len(panel.symbols)))
    rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for idea in IDEAS:
        cached = {threshold: signal(panel, idea.family, threshold, economics)
                  for threshold in idea.thresholds}
        results = []
        for fold in frozen["folds"]:
            selected: list[tuple[float, float, ReplayResult]] = []
            for threshold in idea.thresholds:
                candidate = _candidate(idea, threshold)
                trial = replay(panel, candidate, cached[threshold], zero_exit,
                    economics, fold["selection_start"], fold["selection_stop"])
                metric = _metric(trial)
                ledger.append({"search_id": SEARCH_ID, "family": idea.family,
                    "trial_id": candidate.candidate_id, "parameters": candidate.payload(),
                    "dataset": panel.manifest["dataset_id"], "fold": fold["fold"],
                    "selection_period": [fold["selection_start"], fold["selection_stop"]],
                    "validation_period": [fold["forward_start"], fold["forward_stop"]],
                    "cost": BASE.name, "result": metric, "status": "SELECTION"})
                score = metric["mean_net_r"] if metric["mean_net_r"] is not None else -float("inf")
                selected.append((score, -threshold, trial))
            winner_index = max(range(len(selected)), key=lambda i: selected[i][:2])
            chosen = idea.thresholds[winner_index]
            candidate = _candidate(idea, chosen)
            arms = {}
            for scenario in (BASE, WIDE, SEVERE):
                result = replay(panel, candidate, cached[chosen], zero_exit, economics,
                    fold["forward_start"], fold["forward_stop"], scenario)
                arms[scenario.name] = _metric(result)
                ledger.append({"search_id": SEARCH_ID, "family": idea.family,
                    "trial_id": candidate.candidate_id, "parameters": candidate.payload(),
                    "dataset": panel.manifest["dataset_id"], "fold": fold["fold"],
                    "selection_period": [fold["selection_start"], fold["selection_stop"]],
                    "validation_period": [fold["forward_start"], fold["forward_stop"]],
                    "cost": scenario.name, "result": arms[scenario.name], "status": "FORWARD"})
            neighbor = idea.thresholds[1-winner_index]
            neighbor_result = replay(panel, _candidate(idea, neighbor), cached[neighbor],
                zero_exit, economics, fold["forward_start"], fold["forward_stop"])
            ledger.append({"search_id": SEARCH_ID, "family": idea.family,
                "trial_id": _candidate(idea, neighbor).candidate_id,
                "parameters": _candidate(idea, neighbor).payload(),
                "dataset": panel.manifest["dataset_id"], "fold": fold["fold"],
                "selection_period": [fold["selection_start"], fold["selection_stop"]],
                "validation_period": [fold["forward_start"], fold["forward_stop"]],
                "cost": BASE.name, "result": _metric(neighbor_result), "status": "NEIGHBOR"})
            results.append({"fold": fold["fold"], "selected_threshold": chosen,
                "arms": arms, "neighbor": _metric(neighbor_result)})
        bases = [row["arms"][BASE.name] for row in results]
        net_r = sum(row["mean_net_r"] * row["trades"] for row in bases
                    if row["mean_net_r"] is not None) / max(1, sum(row["trades"] for row in bases))
        trades = sum(row["trades"] for row in bases)
        positives = sum(row["total_net_pnl"] > 0 for row in bases)
        robust = all(sum(row["arms"][scenario]["total_net_pnl"] for row in results) > 0
                     for scenario in (WIDE.name, SEVERE.name))
        neighbor_positive = sum(row["neighbor"]["total_net_pnl"] > 0 for row in results)
        status = "REJECTED" if net_r <= 0 or not robust else "INSUFFICIENT_EVIDENCE"
        rows.append({"family": idea.family, "mechanism": idea.mechanism,
            "observable": idea.observable, "horizon": idea.horizon, "execution": idea.execution,
            "failure": idea.failure, "status": status,
            "reason": "Nonpositive net expectancy or cost failure" if status == "REJECTED"
                      else "Only six fresh forward days; promotion minimum 28 independent days",
            "best_discovery": max((entry["result"] for entry in ledger
                if entry["family"] == idea.family and entry["status"] == "SELECTION"),
                key=lambda item: item["mean_net_r"] if item["mean_net_r"] is not None else -float("inf")),
            "forward_mean_net_r": net_r if trades else None, "forward_trades": trades,
            "positive_folds": positives, "max_drawdown_pct": max(row["max_drawdown_pct"] for row in bases),
            "costs": {scenario.name: sum(row["arms"][scenario.name]["total_net_pnl"]
                for row in results) for scenario in (BASE, WIDE, SEVERE)},
            "neighbor_positive_folds": neighbor_positive,
            "max_symbol_concentration": max((row["symbol_concentration"] or 0) for row in bases),
            "max_day_concentration": max((row["day_concentration"] or 0) for row in bases),
            "beta_attribution": "UNESTIMATED_SHORT_SAMPLE", "folds": results})
    rows += [{"family": family, "status": "UNSUPPORTED_WITH_CURRENT_DATA", "reason": reason,
              "forward_mean_net_r": None, "forward_trades": 0}
             for family, reason in UNSUPPORTED.items()]
    completed = {"schema_version": 1, "search_id": SEARCH_ID, "complete": True,
        "finished_at": datetime.now(UTC).isoformat(), "dataset": panel.manifest,
        "preregistration_sha256": hashlib.sha256(prereg_bytes).hexdigest(),
        "validation_design": frozen["folds"], "cost_assumptions": frozen["costs"],
        "trial_count": frozen["trial_budget"], "evaluation_count": len(ledger),
        "families": rows, "trials": ledger, "promoted_candidates": [],
        "promotion_note": "No candidate can meet 28 independent forward days from this new slice",
        "reserved_tail_bars": len(panel.timestamps)-frozen["folds"][-1]["forward_stop"]}
    _new(result_path, completed)
    _new(root / "research/manifests/alpha_search_completion_004.json",
         {"search_id": SEARCH_ID, "result_sha256": sha256_file(result_path),
          "preregistration_sha256": hashlib.sha256(prereg_bytes).hexdigest(),
          "evaluations": len(ledger), "completed_at": completed["finished_at"]})
    return completed
