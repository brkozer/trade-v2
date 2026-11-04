"""Verified read-only access to sealed research artifacts.

A sealed search is a complete result file whose SHA-256 matches its completion
manifest. Campaign searches (initial, final, 004) and discovery-only searches
(DISCOVERY_SEARCH_*.json) are discovered from disk, so a newly sealed search
becomes inspectable without code changes. Nothing here writes or reruns anything.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DISCOVERY_ROLE = "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
FIXED_PAIRS: tuple[tuple[str, str], ...] = (
    ("campaign.json", "initial_campaign_completion.json"),
    ("FINAL_ALPHA_SEARCH_003.json", "final_search_completion_003.json"),
    ("ALPHA_SEARCH_004.json", "alpha_search_completion_004.json"),
)
DISCOVERY_PREFIX = "DISCOVERY_SEARCH_"
ALIASES = {"initial": "TRADEV2_INITIAL_ALPHA_001", "final": "TRADEV2_FINAL_ALPHA_003"}
CONFIGURATION_SUMMARY_KEYS = frozenset({"passed", "positive_folds", "holm_pvalue"})


@dataclass(frozen=True)
class SealedSearch:
    search_id: str
    result_name: str
    evidence: dict[str, Any]
    seal: dict[str, Any]

    @property
    def kind(self) -> str:
        return "discovery" if self.evidence.get("evidence_role") == DISCOVERY_ROLE else "campaign"

    @property
    def completed_at(self) -> str:
        value = (self.seal.get("completed_at") or self.evidence.get("finished_at")
                 or self.evidence.get("generated_at"))
        return str(value) if value is not None else ""

    def summary(self) -> dict[str, Any]:
        evidence = self.evidence
        dataset = evidence.get("dataset") or {}
        budget = evidence.get("search_budget") or {}
        families = evidence.get("families") or []
        if families:
            family_count: int | None = len(families)
            rejected_count: int | None = sum(
                1 for row in families if str(row.get("status", "")).startswith("REJECTED"))
        elif self.kind == "discovery" and evidence.get("family"):
            # A discovery search tests one family; its configurations are counted separately.
            family_count = 1
            rejected_count = int(str(evidence.get("status", "")).startswith("REJECTED"))
        else:
            family_count = rejected_count = None
        return {
            "search_id": self.search_id,
            "kind": self.kind,
            "generated_at": evidence.get("generated_at") or evidence.get("finished_at"),
            "completed_at": self.completed_at,
            "dataset": dataset.get("id") or dataset.get("dataset_id"),
            "dataset_role": dataset.get("role") or dataset.get("evidence_role"),
            "evidence_role": evidence.get("evidence_role"),
            "status": evidence.get("status"),
            "family": evidence.get("family"),
            "configurations": budget.get("configurations") or evidence.get("trial_count"),
            "evaluations": budget.get("total_replays") or evidence.get("evaluation_count"),
            "family_count": family_count,
            "rejected_count": rejected_count,
            "promoted": len(evidence.get("promoted_candidates") or []),
            "frozen_candidate": (evidence.get("frozen_candidate") is not None
                                 if "frozen_candidate" in evidence else None),
            "holdout_state": (evidence.get("final_holdout_state") or evidence.get("promotion_note")
                              or evidence.get("promotion")),
            "complete": True,
        }

    def candidate_rows(self) -> list[dict[str, Any]]:
        evidence = self.evidence
        families = evidence.get("families")
        if isinstance(families, list):
            return [row for row in families if isinstance(row, dict)]
        if self.kind != "discovery":
            return []
        family = str(evidence.get("family"))
        common = {"family": family, "mechanism": evidence.get("mechanism"),
                  "search_status": evidence.get("status"), "evidence_role": DISCOVERY_ROLE,
                  "frozen_candidate": evidence.get("frozen_candidate")}
        configurations = evidence.get("configurations")
        if isinstance(configurations, list) and configurations:
            rows: list[dict[str, Any]] = []
            for configuration in configurations:
                if not isinstance(configuration, dict):
                    continue
                aggregate = configuration.get("aggregate_base") or {}
                parameters = {key: value for key, value in configuration.items()
                              if not isinstance(value, dict | list)
                              and key not in CONFIGURATION_SUMMARY_KEYS}
                label = ",".join(f"{key}={value}" for key, value in sorted(parameters.items()))
                rows.append({**common, "configuration": parameters, "label": label,
                             "status": ("DISCOVERY_GATES_PASSED" if configuration.get("passed")
                                        else "DISCOVERY_GATES_FAILED"),
                             "forward_trades": aggregate.get("trades"),
                             "forward_mean_net_r": aggregate.get("mean_net_r"),
                             "forward_mean_gross_r": aggregate.get("mean_gross_r"),
                             "positive_folds": configuration.get("positive_folds"),
                             "costs": configuration.get("cost_total_net_pnl"),
                             "holm_pvalue": configuration.get("holm_pvalue"),
                             "bootstrap": configuration.get("bootstrap"),
                             "market_attribution": configuration.get("market_attribution"),
                             "max_drawdown_pct": aggregate.get("max_drawdown_pct"),
                             "max_symbol_concentration": aggregate.get("symbol_concentration"),
                             "max_day_concentration": aggregate.get("day_concentration"),
                             "folds": configuration.get("folds")})
            return rows
        return [{**common, "configuration": None, "label": family, "status": evidence.get("status"),
                 "forward_trades": evidence.get("forward_trades"),
                 "forward_mean_net_r": evidence.get("forward_mean_net_r"),
                 "forward_mean_gross_r": evidence.get("forward_mean_gross_r"),
                 "positive_folds": evidence.get("positive_folds"),
                 "neighbor_positive_folds": evidence.get("neighbor_positive_folds"),
                 "costs": evidence.get("cost_total_net_pnl"),
                 "holm_pvalue": None, "bootstrap": evidence.get("bootstrap"),
                 "market_attribution": None,
                 "max_drawdown_pct": (evidence.get("aggregate_base") or {}).get("max_drawdown_pct"),
                 "max_symbol_concentration": evidence.get("max_symbol_concentration"),
                 "max_day_concentration": evidence.get("max_day_concentration"),
                 "folds": evidence.get("folds")}]

    def experiment_rows(self) -> list[dict[str, Any]]:
        evidence = self.evidence
        if self.search_id == "TRADEV2_ALPHA_SEARCH_004":
            return [{"hypothesis": row["family"], "baseline": "preregistered_thresholds",
                     "treatment": row["cost"], "sample_unit": "chronological_fold_replay",
                     "n": row["result"]["trades"], "mean_paired_delta": None,
                     "ci": None, "multiple_testing_family": self.search_id,
                     "checkpoint": row["fold"], "status": row["status"],
                     "trial_id": row["trial_id"], "net_r": row["result"]["mean_net_r"]}
                    for row in evidence.get("trials", [])]
        if self.kind == "discovery":
            rows: list[dict[str, Any]] = []
            for trial in evidence.get("trials", []):
                if not isinstance(trial, dict):
                    continue
                candidate = trial.get("candidate")
                cost = trial.get("cost")
                treatment = cost.get("name") if isinstance(cost, dict) else cost
                result = trial.get("result") or {}
                hypothesis = (candidate.get("candidate_id") if isinstance(candidate, dict)
                              else None) or evidence.get("family")
                rows.append({"hypothesis": hypothesis,
                             "baseline": "preregistered_frozen_design", "treatment": treatment,
                             "sample_unit": "chronological_fold_replay", "n": result.get("trades"),
                             "mean_paired_delta": None, "ci": None,
                             "multiple_testing_family": self.search_id,
                             "checkpoint": trial.get("fold"), "status": trial.get("stage"),
                             "trial_id": f"{hypothesis}:{trial.get('fold')}:{treatment}:{trial.get('stage')}",
                             "net_r": result.get("mean_net_r")})
            return rows
        rows = []
        for family in evidence.get("families", []):
            for fold in family.get("folds", []):
                for treatment, result in fold.get("stress", {}).items():
                    paired = result.get("paired")
                    if not isinstance(paired, dict):
                        continue
                    rows.append({"hypothesis": family["family"], "baseline": "base_taker",
                                 "treatment": treatment, "sample_unit": "common_opportunity_intent",
                                 "n": paired.get("common_opportunities"),
                                 "paired_net_delta": paired.get("paired_net_delta"),
                                 "mean_paired_delta": paired.get("mean_paired_delta"),
                                 "ci": None, "multiple_testing_family": self.search_id,
                                 "checkpoint": fold.get("fold"), "status": "DESCRIPTIVE_ONLY",
                                 "unpaired_portfolio_delta": paired.get("unpaired_portfolio_delta")})
        return rows


def _pairs(root: Path) -> list[tuple[Path, Path]]:
    results = root / "research/results"
    manifests = root / "research/manifests"
    pairs = [(results / name, manifests / marker) for name, marker in FIXED_PAIRS]
    if results.is_dir():
        for path in sorted(results.glob(f"{DISCOVERY_PREFIX}*.json")):
            suffix = path.stem[len(DISCOVERY_PREFIX):]
            if suffix.isdigit():
                pairs.append((path, manifests / f"alpha_search_completion_{suffix}.json"))
    return pairs


def load_sealed_searches(root: Path, errors: list[str]) -> list[SealedSearch]:
    """Return verified sealed searches ordered by completion time; record failures."""
    sealed: list[SealedSearch] = []
    for path, completion in _pairs(root):
        if not path.exists():
            continue
        try:
            if (not path.resolve().is_relative_to(root.resolve())
                    or not completion.resolve().is_relative_to(root.resolve())
                    or not completion.is_file()):
                raise ValueError("research artifact outside target or completion missing")
            content = path.read_bytes()
            evidence = json.loads(content.decode("utf-8"))
            seal = json.loads(completion.read_text(encoding="utf-8"))
            if (not isinstance(evidence, dict) or not isinstance(seal, dict)
                    or evidence.get("complete") is not True
                    or hashlib.sha256(content).hexdigest() != seal["result_sha256"]
                    or not isinstance(evidence.get("search_id"), str)
                    or seal.get("search_id") != evidence["search_id"]):
                raise ValueError("campaign checksum, identity or completeness invalid")
            sealed.append(SealedSearch(evidence["search_id"], path.name, evidence, seal))
        except (OSError, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            errors.append(f"CAMPAIGN_INTEGRITY_FAILED:{path.name}")
    sealed.sort(key=lambda item: (item.completed_at, item.search_id))
    return sealed


def resolve_search_id(token: str, sealed: list[SealedSearch]) -> str | None:
    """Map an alias (initial, final, 004, 009) or an exact identity to a sealed search."""
    if token in ALIASES:
        return ALIASES[token]
    identities = [item.search_id for item in sealed]
    if token in identities:
        return token
    if token.isdigit():
        matches = [identity for identity in identities if identity.rsplit("_", 1)[-1] == token]
        if len(matches) == 1:
            return matches[0]
    return None
