import json
import shutil
from pathlib import Path

from tradev2.evidence.sealed_research import load_sealed_searches, resolve_search_id

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ORDER = ["TRADEV2_INITIAL_ALPHA_001", "TRADEV2_FINAL_ALPHA_003", "TRADEV2_ALPHA_SEARCH_004",
                  "TRADEV2_DISCOVERY_005", "TRADEV2_DISCOVERY_006", "TRADEV2_DISCOVERY_007",
                  "TRADEV2_DISCOVERY_008", "TRADEV2_DISCOVERY_009"]


def test_repository_sealed_searches_verify_and_order_by_completion() -> None:
    errors: list[str] = []
    sealed = load_sealed_searches(ROOT, errors)
    assert errors == []
    assert [item.search_id for item in sealed][:len(EXPECTED_ORDER)] == EXPECTED_ORDER
    by_id = {item.search_id: item for item in sealed}
    final = by_id["TRADEV2_FINAL_ALPHA_003"].summary()
    assert final["kind"] == "campaign"
    assert (final["configurations"], final["evaluations"], final["promoted"]) == (28, 336, 0)
    assert (final["family_count"], final["rejected_count"]) == (14, 14)
    discovery = by_id["TRADEV2_DISCOVERY_009"].summary()
    assert discovery["kind"] == "discovery"
    assert discovery["evidence_role"] == "DISCOVERY_ONLY_NOT_FRESH_VALIDATION"
    assert discovery["status"] == "REJECTED_DISCOVERY_ONLY"
    assert (discovery["configurations"], discovery["evaluations"], discovery["promoted"]) == (2, 24, 0)
    assert discovery["frozen_candidate"] is False
    assert discovery["family"] == "cross_sectional_idiosyncratic_max_effect"
    assert (discovery["family_count"], discovery["rejected_count"]) == (1, 1)
    carry_summary = by_id["TRADEV2_DISCOVERY_005"].summary()
    assert (carry_summary["family_count"], carry_summary["rejected_count"]) == (1, 1)
    assert carry_summary["configurations"] == 2 and carry_summary["evaluations"] == 18
    rows = by_id["TRADEV2_DISCOVERY_009"].candidate_rows()
    assert [row["label"] for row in rows] == ["lookback=1344", "lookback=2688"]
    assert all(row["status"] == "DISCOVERY_GATES_FAILED" and row["forward_trades"] == 464 for row in rows)
    carry = by_id["TRADEV2_DISCOVERY_005"].candidate_rows()
    assert len(carry) == 1 and carry[0]["forward_trades"] == 72
    assert carry[0]["status"] == "REJECTED_DISCOVERY_ONLY" and carry[0]["positive_folds"] == 0
    assert len(by_id["TRADEV2_FINAL_ALPHA_003"].candidate_rows()) == 14
    assert len(by_id["TRADEV2_DISCOVERY_009"].experiment_rows()) == 24
    assert len(by_id["TRADEV2_DISCOVERY_005"].experiment_rows()) == 18
    assert len(by_id["TRADEV2_ALPHA_SEARCH_004"].experiment_rows()) == 108
    assert len(by_id["TRADEV2_FINAL_ALPHA_003"].experiment_rows()) == 112
    experiment = by_id["TRADEV2_DISCOVERY_009"].experiment_rows()[0]
    assert experiment["ci"] is None and experiment["mean_paired_delta"] is None
    assert experiment["status"] == "FORWARD" and experiment["treatment"] == "base_taker"


def test_aliases_and_identities_resolve_without_guessing() -> None:
    sealed = load_sealed_searches(ROOT, [])
    assert resolve_search_id("initial", sealed) == "TRADEV2_INITIAL_ALPHA_001"
    assert resolve_search_id("final", sealed) == "TRADEV2_FINAL_ALPHA_003"
    assert resolve_search_id("004", sealed) == "TRADEV2_ALPHA_SEARCH_004"
    assert resolve_search_id("009", sealed) == "TRADEV2_DISCOVERY_009"
    assert resolve_search_id("TRADEV2_DISCOVERY_007", sealed) == "TRADEV2_DISCOVERY_007"
    assert resolve_search_id("002", sealed) is None
    assert resolve_search_id("latest", sealed) is None


def _copy_discovery(tmp_path: Path) -> tuple[Path, Path]:
    results = tmp_path / "research/results"
    manifests = tmp_path / "research/manifests"
    results.mkdir(parents=True)
    manifests.mkdir(parents=True)
    result = results / "DISCOVERY_SEARCH_009.json"
    seal = manifests / "alpha_search_completion_009.json"
    shutil.copy(ROOT / "research/results/DISCOVERY_SEARCH_009.json", result)
    shutil.copy(ROOT / "research/manifests/alpha_search_completion_009.json", seal)
    return result, seal


def test_tampered_unsealed_or_incomplete_artifacts_are_not_served(tmp_path: Path) -> None:
    result, seal = _copy_discovery(tmp_path)
    errors: list[str] = []
    assert [item.search_id for item in load_sealed_searches(tmp_path, errors)] == ["TRADEV2_DISCOVERY_009"]
    assert errors == []
    original = result.read_bytes()
    result.write_bytes(original.replace(b"REJECTED_DISCOVERY_ONLY", b"PROMOTED_DISCOVERY_ONLY", 1))
    errors = []
    assert load_sealed_searches(tmp_path, errors) == []
    assert errors == ["CAMPAIGN_INTEGRITY_FAILED:DISCOVERY_SEARCH_009.json"]
    result.write_bytes(original)
    sealed_payload = json.loads(seal.read_text(encoding="utf-8"))
    seal.write_text(json.dumps(sealed_payload | {"search_id": "TRADEV2_DISCOVERY_010"}), encoding="utf-8")
    errors = []
    assert load_sealed_searches(tmp_path, errors) == [] and len(errors) == 1
    seal.unlink()
    errors = []
    assert load_sealed_searches(tmp_path, errors) == []
    assert errors == ["CAMPAIGN_INTEGRITY_FAILED:DISCOVERY_SEARCH_009.json"]
    (tmp_path / "research/results/DISCOVERY_SEARCH_notanumber.json").write_text("{}", encoding="utf-8")
    errors = []
    assert load_sealed_searches(tmp_path, errors) == [] and len(errors) == 1
