"""Reproducible, preregistered search with expanding chronological validation."""

import argparse
import gzip
import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from tradev2.alpha.candidates import MECHANISMS, candidate_grid, decisions
from tradev2.research.costs import BASE, FRICTION, WIDE, load_economics
from tradev2.research.datasets import BAR_MS, json_write, load_panel, sha256_file
from tradev2.research.replay import Trade, paired_comparison, replay, summarize, trade_payload
from tradev2.research.statistics import day_block_bootstrap, holm_adjust

SEARCH_ID = "TRADEV2_INITIAL_ALPHA_001"
SEED = 20260922


def preregistration() -> dict[str, Any]:
    return {"schema_version": 1, "search_id": SEARCH_ID, "seed": SEED,
            "families": MECHANISMS, "candidates": [c.payload() for c in candidate_grid()],
            "configuration_budget": 18, "folds": 4, "validation_days_per_fold": 30,
            "selection_metric": "training mean daily net PnL minus 0.5 daily PnL standard deviation; at least 50 trades",
            "tie_break": "candidate_id ascending", "warmup_bars": 200,
            "portfolio": {"initial_equity": 10000, "risk_fraction": .0025,
                          "max_positions": 4, "max_gross_fraction": .8, "max_symbol_fraction": .2},
            "scenarios": [asdict(s) for s in (BASE, WIDE, FRICTION)],
            "inference": {"bootstrap_draws": 2000, "circular_block_days": 7,
                          "multiplicity": "Holm across six family-level walk-forward paths; full 18-trial history retained"},
            "promotion_gates": {"validation_trades_min": 200, "validation_days_min": 90,
                                "symbols_min": 10, "positive_folds_min": 3,
                                "bootstrap_lower_above": 0, "holm_pvalue_max": .05,
                                "max_symbol_absolute_contribution": .35,
                                "max_drawdown_pct": 10, "both_stress_pnl_positive": True,
                                "required_fresh_independent_evidence": True},
            "evidence_role": "REUSED_HISTORICAL_DISCOVERY",
            "final_holdout_state": "NOT_ACQUIRED_NOT_CONSUMED",
            "prohibited": ["reading sealed/final/prospective legacy payloads", "post-outcome retuning",
                           "claiming this reused history is fresh final OOS", "live trading"],
            "data_policy": "all37 available OHLCV symbols; exact complete 15m bins; complete UTC days inside common funding coverage; no interpolation",
            "limitations": ["fixed current survivor universe", "OHLC intrabar ambiguity: stop first",
                            "maker fill quality not measured; all primary fills charged taker",
                            "current minimums and historical spread/fee snapshots are assumptions",
                            "all thresholds fixed before results; regimes descriptive only"]}


def code_identity(root: Path) -> dict[str, Any]:
    paths = [*sorted((root / "src" / "tradev2" / "alpha").glob("*.py")),
             *sorted((root / "src" / "tradev2" / "research").glob("*.py")),
             *sorted((root / "src" / "tradev2" / "strategies").glob("*.py"))]
    hashes = {str(path.relative_to(root)).replace("\\", "/"): sha256_file(path) for path in paths}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return {"git_sha": sha, "research_code_sha256": digest, "files": hashes}


def freeze(root: Path, dataset: Path) -> dict[str, Any]:
    path = root / "research" / "manifests" / "initial_campaign_preregistration.json"
    if path.exists():
        raise FileExistsError("preregistration is immutable; use a new search identity for a successor")
    payload = preregistration() | {"frozen_at": datetime.now(UTC).isoformat(),
                "software": code_identity(root),
                "dataset_manifest_sha256": sha256_file(dataset / "manifest.json"),
                "dataset_sha256": sha256_file(dataset / "candles_15m.npz"),
                "economics_sha256": sha256_file(dataset / "economics.json")}
    json_write(path, payload)
    return payload


def run_campaign(root: Path, dataset: Path) -> dict[str, Any]:
    prereg_path = root / "research" / "manifests" / "initial_campaign_preregistration.json"
    frozen: dict[str, Any] = json.loads(prereg_path.read_text(encoding="utf-8"))
    for key, value in preregistration().items():
        if frozen[key] != value:
            raise ValueError(f"preregistration drift in {key}")
    software = code_identity(root)
    if software["research_code_sha256"] != frozen["software"]["research_code_sha256"]:
        raise ValueError("research code changed after freeze")
    for filename, key in (("manifest.json", "dataset_manifest_sha256"),
                          ("candles_15m.npz", "dataset_sha256"), ("economics.json", "economics_sha256")):
        if sha256_file(dataset / filename) != frozen[key]:
            raise ValueError(f"frozen evidence hash mismatch: {filename}")
    output = root / "research" / "results"
    output.mkdir(parents=True, exist_ok=True)
    marker = root / "research" / "manifests" / "initial_campaign_consumption.json"
    # Exclusive create makes even interrupted searches visibly consumed, never silently rerun.
    with marker.open("x", encoding="utf-8") as handle:
        json.dump({"search_id": SEARCH_ID, "started_at": datetime.now(UTC).isoformat(),
                   "preregistration_sha256": sha256_file(prereg_path), "software": software}, handle, indent=2)
    panel = load_panel(dataset)
    economics_payload = json.loads((dataset / "economics.json").read_text(encoding="utf-8"))
    economics = load_economics(economics_payload, panel.symbols)
    day_ms = 86_400_000
    start_ms = ((int(panel.timestamps[0]) + day_ms - 1) // day_ms) * day_ms
    last_funding = min(int(e.funding[-1, 0]) for e in economics.values())
    end_ms = (min(int(panel.timestamps[-1]) + BAR_MS, last_funding) // day_ms) * day_ms
    total_days = (end_ms - start_ms) // day_ms
    train_days = total_days - 120
    if train_days < 60:
        raise ValueError("campaign requires at least60 discovery+120 validation days")
    folds: list[dict[str, int]] = []
    for number in range(4):
        split_ms = start_ms + (train_days + number * 30) * day_ms
        folds.append({"fold": number + 1,
                      "train_start": int(np.searchsorted(panel.timestamps, start_ms)),
                      "train_stop": int(np.searchsorted(panel.timestamps, split_ms)),
                      "validation_start": int(np.searchsorted(panel.timestamps, split_ms)),
                      "validation_stop": int(np.searchsorted(panel.timestamps, split_ms + 30 * day_ms)),
                      "train_start_ms": start_ms, "train_stop_ms": split_ms,
                      "validation_start_ms": split_ms, "validation_stop_ms": split_ms + 30 * day_ms})
    grid = candidate_grid()
    trials: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    ledger_path = dataset / "initial_campaign_opportunities.jsonl.gz"
    trades_path = dataset / "initial_campaign_trades.jsonl.gz"
    # Full ledgers are local public-research artifacts; hashes and aggregate results are tracked.
    with gzip.open(ledger_path, "wt", encoding="utf-8") as ledger, gzip.open(trades_path, "wt", encoding="utf-8") as trade_log:
        for family_index, (family_name, mechanism) in enumerate(MECHANISMS.items()):
            members = [c for c in grid if c.family == family_name]
            cached = {c.candidate_id: decisions(panel, c) for c in members}
            all_trades: list[Trade] = []
            all_days: dict[int, float] = defaultdict(float)
            family_folds: list[dict[str, Any]] = []
            stress_totals: dict[str, float] = defaultdict(float)
            train_choices: list[dict[str, Any]] = []
            rejections: dict[str, int] = defaultdict(int)
            max_drawdown = 0.
            for fold in folds:
                ranking: list[tuple[float, str, dict[str, Any]]] = []
                for candidate in members:
                    signal, exit_rsi = cached[candidate.candidate_id]
                    training = replay(panel, candidate, signal, exit_rsi, economics,
                                      fold["train_start"], fold["train_stop"])
                    daily = np.asarray(list(training.daily_pnl.values()))
                    eligible = len(training.trades) >= 50
                    score = float(daily.mean() - .5 * daily.std(ddof=1)) if eligible else None
                    trial = {"search_id": SEARCH_ID, "family": family_name, "candidate_id": candidate.candidate_id,
                             "fold": fold["fold"], "parameters": candidate.payload(), "score": score,
                             "eligible": eligible, "metrics": training.metrics,
                             "train_start_ms": fold["train_start_ms"], "train_stop_ms": fold["train_stop_ms"]}
                    trials.append(trial)
                    ranking.append((score if score is not None else -float("inf"), candidate.candidate_id, training.metrics))
                ranking.sort(key=lambda row: (-row[0], row[1]))
                choice = ranking[0]
                selected = next(c for c in members if c.candidate_id == choice[1])
                train_choices.append(choice[2])
                signal, exit_rsi = cached[selected.candidate_id]
                baseline = replay(panel, selected, signal, exit_rsi, economics,
                                  fold["validation_start"], fold["validation_stop"], capture=True)
                for opportunity in baseline.opportunities:
                    ledger.write(json.dumps(opportunity | {"family": family_name, "fold": fold["fold"]}) + "\n")
                for trade in baseline.trades:
                    trade_log.write(json.dumps(trade_payload(trade) | {"family": family_name,
                                     "fold": fold["fold"], "scenario": BASE.name}) + "\n")
                all_trades.extend(baseline.trades)
                all_days.update(baseline.daily_pnl)
                max_drawdown = max(max_drawdown, baseline.metrics["max_drawdown_pct"])
                for reason, count in baseline.rejections.items():
                    rejections[reason] += count
                stress: dict[str, Any] = {}
                for scenario in (WIDE, FRICTION):
                    treatment = replay(panel, selected, signal, exit_rsi, economics,
                                       fold["validation_start"], fold["validation_stop"], scenario, capture=True)
                    for opportunity in treatment.opportunities:
                        ledger.write(json.dumps(opportunity | {"family": family_name, "fold": fold["fold"]}) + "\n")
                    for trade in treatment.trades:
                        trade_log.write(json.dumps(trade_payload(trade) | {"family": family_name,
                                         "fold": fold["fold"], "scenario": scenario.name}) + "\n")
                    stress[scenario.name] = {"metrics": treatment.metrics,
                                             "paired": paired_comparison(baseline, treatment)}
                    stress_totals[scenario.name] += treatment.metrics["total_net_pnl"]
                family_folds.append({"fold": fold["fold"], "candidate_id": selected.candidate_id,
                                     "selection_eligible": choice[0] != -float("inf"),
                                     "train": choice[2], "validation": baseline.metrics, "stress": stress})
                print(f"{family_name} fold{fold['fold']}: selected {selected.candidate_id}; "
                      f"n={len(baseline.trades)} net={baseline.metrics['total_net_pnl']:.2f}", flush=True)
            oos = summarize(all_trades, dict(all_days)) | {"max_drawdown_pct": max_drawdown,
                                                          "rejections": dict(rejections)}
            bootstrap_result = day_block_bootstrap(list(all_days.values()), seed=SEED + family_index)
            discovery_n = sum(m["trades"] for m in train_choices)
            discovery = {"mean_net_r": sum((m["mean_net_r"] or 0) * m["trades"] for m in train_choices) / discovery_n if discovery_n else None,
                         "trades": discovery_n, "note": "overlapping training windows; aggregate is descriptive, not independent evidence"}
            families.append({"family": family_name, "mechanism": mechanism, "discovery": discovery,
                             "selected_candidates": [f["candidate_id"] for f in family_folds],
                             "oos": oos, "bootstrap": asdict(bootstrap_result), "folds": family_folds,
                             "stress": dict(stress_totals), "daily_pnl": dict(all_days)})
            # Incremental checkpoint preserves failed/partial searches; never overwritten as success.
            json_write(output / "campaign.checkpoint.json", {"search_id": SEARCH_ID, "complete": False,
                                                           "families": families, "trials": trials})
    adjusted = holm_adjust([f["bootstrap"]["positive_pvalue"] for f in families])
    for family, pvalue in zip(families, adjusted, strict=True):
        oos, boot = family["oos"], family["bootstrap"]
        family["adjusted_pvalue"] = pvalue
        positive_folds = sum(f["validation"]["total_net_pnl"] > 0 for f in family["folds"])
        failures = []
        if oos["total_net_pnl"] <= 0:
            failures.append("negative aggregate validation economics")
        if boot["lower_95"] is None or boot["lower_95"] <= 0:
            failures.append("day-block bootstrap lower bound does not exceed zero")
        if pvalue is None or pvalue > .05:
            failures.append("family-level multiplicity gate failed")
        if positive_folds < 3:
            failures.append("fewer than3 positive validation folds")
        if oos["trades"] < 200 or oos["symbols_traded"] < 10:
            failures.append("insufficient trade count or symbol breadth")
        if oos["symbol_concentration"] is None or oos["symbol_concentration"] > .35:
            failures.append("symbol concentration gate failed")
        if oos["max_drawdown_pct"] > 10:
            failures.append("drawdown gate failed")
        if any(value <= 0 for value in family["stress"].values()):
            failures.append("execution/cost stress gate failed")
        if not all(f["selection_eligible"] for f in family["folds"]):
            failures.append("some training selections lacked50 trades")
        family["historical_gates_passed"] = not failures
        family["status"] = "REJECTED" if failures and oos["trades"] >= 200 else "INSUFFICIENT"
        family["reasons"] = failures + ["reused legacy history and uncalibrated execution cannot supply fresh independent acceptance"]
        family["positive_folds"] = positive_folds
    ranked = sorted(families, key=lambda f: (-(f["oos"]["mean_net_r"] or -999), f["family"]))
    for rank, family in enumerate(ranked, 1):
        family["rank"] = rank
    result = {"schema_version": 1, "search_id": SEARCH_ID, "complete": True,
              "generated_at": datetime.now(UTC).isoformat(), "software": software,
              "source_revision": panel.manifest["source_revision"],
              "dataset": {"id": panel.manifest["dataset_id"], "sha256": panel.manifest["sha256"],
                          "role": panel.manifest["evidence_role"], "symbols": list(panel.symbols),
                          "first_open_ms": int(panel.timestamps[0]), "last_open_ms": int(panel.timestamps[-1]),
                          "bars_per_symbol": len(panel.timestamps)},
              "search_budget": {"configurations": len(grid), "selection_evaluations": len(trials),
                                "validation_evaluations": 24, "stress_evaluations": 48,
                                "total_replays": len(trials) + 72},
              "validation_design": {"method": "expanding training / four30-day forward validations; flat fold boundaries",
                                    "initial_train_days": train_days, "folds": folds,
                                    "warning": "Chronological validation on previously consumed legacy research history, not fresh OOS"},
              "cost_assumptions": {"scenarios": [asdict(s) for s in (BASE, WIDE, FRICTION)],
                                   "economics_sha256": frozen["economics_sha256"],
                                   "limitations": economics_payload["limitations"],
                                   "fee_tiers_bps": {s: {"maker": e.maker_rate * 10000, "taker": e.taker_rate * 10000,
                                                         "spread": e.spread_bps} for s, e in economics.items()}},
              "families": families, "trials": trials, "promoted_candidates": [],
              "final_holdout_state": frozen["final_holdout_state"],
              "preregistration_sha256": sha256_file(prereg_path),
              "ledgers": [{"path": str(p.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(p),
                           "bytes": p.stat().st_size} for p in (ledger_path, trades_path)],
              "next_milestone": "Independent dataset and prospective execution calibration for new or surviving hypotheses"}
    json_write(output / "campaign.json", result)
    json_write(root / "research" / "manifests" / "initial_campaign_completion.json",
               {"search_id": SEARCH_ID, "completed_at": result["generated_at"],
                "result_sha256": sha256_file(output / "campaign.json"), "trial_count": len(trials)})
    write_report(output / "INITIAL_ALPHA_CAMPAIGN.md", result)
    return result


def write_report(path: Path, result: dict[str, Any]) -> None:
    dataset = result["dataset"]
    lines = ["# Initial Alpha Factory campaign", "", f"Search: `{result['search_id']}`.", "",
             "This is a reproducible historical discovery experiment. All source candles were previously",
             "inspected in legacy research. Chronological validation here is **not untouched final OOS**.", "",
             f"Dataset: `{dataset['id']}`, {len(dataset['symbols'])} symbols, {dataset['bars_per_symbol']} 15m bars each.",
             f"UTC coverage: {datetime.fromtimestamp(dataset['first_open_ms'] / 1000, UTC).isoformat()} to "
             f"{datetime.fromtimestamp(dataset['last_open_ms'] / 1000, UTC).isoformat()} (bar opens).", "",
             "All37 source symbols were retained. Exact consecutive minute bins were aggregated without imputation.",
             f"Search budget: {result['search_budget']}. All failed trials remain in campaign.json.", "",
             "Four expanding training windows each choose one of three predefined configurations per family.",
             "The following30-day interval measures that frozen choice; no validation outcome tunes the next",
             "grid. Earlier validation naturally enters later expanding training. Fold boundaries close all positions.",
             "Selection penalizes daily PnL volatility and requires50 training trades. Weekly block bootstrap",
             "and Holm adjustment across six family paths supplement, but cannot repair, prior-history contamination.", "",
             "| Family | Discovery net R | Validation trades | Validation net R | Net USDT | Fees | Funding | Spread + slip | Status |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for family in result["families"]:
        m = family["oos"]
        discovery = family["discovery"]["mean_net_r"]
        lines.append(f"| {family['family']} | {discovery if discovery is not None else 'unknown'} | {m['trades']} | "
                     f"{m['mean_net_r'] if m['mean_net_r'] is not None else 'unknown'} | {m['total_net_pnl']:.2f} | "
                     f"{m['fees']:.2f} | {m['funding']:.2f} | {m['spread'] + m['slippage']:.2f} | {family['status']} |")
    lines += ["", "Each fold starts with10,000 simulated USDT. Total PnL combines four independently reset folds;",
              "it is not a compounded deployable account return. Rejections, regime/symbol concentration, tails,",
              "daily equity changes, stress arms and opportunity-paired deltas are in campaign.json.", "",
              "## Costs and execution", "", "Primary replay uses taker/taker fees: dated measured5.5bps per side",
              "for34 symbols and11bps for HEMI/USELESS/VVV, plus at least3bps roundtrip spread and1bps slippage",
              "per side. Actual settled funding times apply with entry-notional approximation. Quotes, queue",
              "priority and historical mark prices are unavailable. Current public venue quantity/minimum rules",
              "constrain sizing; a minimum too large for the risk budget rejects the opportunity.", "",
              "Wide-cost stress increases fees1.5x, spread2x and slippage to3bps per side. Friction stress delays",
              "entries by one15m bar, fills half size and deterministically misses one quarter of eligible IDs.",
              "These are declared sensitivity scenarios, not empirically calibrated fill probabilities.",
              "All variants fully re-simulate portfolio slot contention. Stop wins an ambiguous OHLC bar."]
    # Keep reporting text separate from numerical artifacts to avoid rounding being used for decisions.
    lines[-1] = "All variants fully re-simulate portfolio slot contention. Stop wins an ambiguous OHLC bar."
    lines += ["Closed-bar decisions execute at the next available open. Intrabar fill timestamps remain unknown.", "",
              "## Family decisions", ""]
    for family in result["families"]:
        lines += [f"- **{family['family']} — {family['status']}**: " + "; ".join(family["reasons"]) + ".",
                  f"  Selected: {', '.join(family['selected_candidates'])}. Positive folds: {family['positive_folds']}/4; "
                  f"Holm p={family['adjusted_pvalue']}; stress net={family['stress']}."]
    lines += ["", "## Holdouts and next experiments", "", "No final, sealed or prospective legacy payload was opened.",
              "No candidate receives live or scientific acceptance. No candidates were promoted automatically.",
              "Next: predeclare independent historical data and public prospective execution calibration."]
    lines[-1] = "Next: predeclare independent historical data and public prospective execution calibration."
    lines += ["BTC/ETH residuals, L2 imbalance, aggressive flow and funding-state features remain separate hypotheses",
              "requiring their own justified data. The implemented residual family uses an equal-weight market basket.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = args.dataset or root / "data" / "public" / "initial_campaign"
    if args.freeze:
        freeze(root, dataset)
        print("Preregistration frozen; commit it before running the one-shot campaign.")
    else:
        result = run_campaign(root, dataset)
        print(json.dumps({"search_id": result["search_id"], "outcomes": {
            row["family"]: row["status"] for row in result["families"]}}, indent=2))


if __name__ == "__main__":
    main()
