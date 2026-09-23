import hashlib
import json
from pathlib import Path


def test_completed_final_search_is_sealed_and_search_budget_is_accounted() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "research/results/FINAL_ALPHA_SEARCH_003.json"
    manifest = root / "research/manifests/final_search_completion_003.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    completion = json.loads(manifest.read_text(encoding="utf-8"))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == completion["result_sha256"]
    assert result["complete"] is True
    assert result["search_budget"]["configurations"] == 28
    assert result["search_budget"]["selection_evaluations"] == 112
    assert result["search_budget"]["total_replays"] == 336
    assert sum(family["evaluation_count"] for family in result["families"]) == 336
    assert len(result["families"]) == 14
    assert result["promoted_candidates"] == []
    assert all(family["status"] == "REJECTED" for family in result["families"])
    assert all(len(family["trials"]) == 8 and len(family["folds"]) == 4
               for family in result["families"])
    assert "NO_UNTOUCHED_HISTORICAL_HOLDOUT" in result["final_holdout_state"]
    assert "prior_aborted_search" in json.loads(
        (root / "research/manifests/final_search_preregistration_003.json").read_text())
