import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tradev2.alpha.factors import registry
from tradev2.config.models import Mode
from tradev2.domain.market import Candle
from tradev2.runtime.factor_policy import approved_factor, latest_factor_scores


def candles(symbol: str, *, gap: bool = False) -> list[Candle]:
    result: list[Candle] = []
    for index in range(210):
        start = index * 900_000 + (900_000 if gap and index >= 100 else 0)
        close = Decimal("100") + Decimal(index) / 10
        result.append(Candle(symbol=symbol, start_ms=start, interval_ms=900_000,
                             open=close, high=close, low=close, close=close,
                             volume=Decimal("10"), confirmed=True))
    return result


def test_factor_runtime_uses_frozen_replay_signal_and_rejects_gaps() -> None:
    spec = next(item for item in registry() if item.family == "trend_persistence")
    result = latest_factor_scores({"BTCUSDT": candles("BTCUSDT")}, spec)
    assert result["BTCUSDT"] > 0
    with pytest.raises(ValueError, match="continuous"):
        latest_factor_scores({"BTCUSDT": candles("BTCUSDT", gap=True)}, spec)


def test_unpromoted_factor_cannot_enter_simulation(tmp_path: Path) -> None:
    spec = registry()[0]
    with pytest.raises(PermissionError, match="lacks frozen"):
        approved_factor(tmp_path, spec.candidate_id)


def test_sealed_promoted_family_and_parameter_selection_required(tmp_path: Path) -> None:
    spec = registry()[0]
    result_dir = tmp_path / "research/results"
    manifest_dir = tmp_path / "research/manifests"
    result_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    result = {"complete": True, "search_id": "synthetic_004",
              "promoted_candidates": [spec.family], "families": [
                  {"family": spec.family, "status": "PROSPECTIVE_SHADOW",
                   "historical_gates_passed": True,
                   "selected_candidates": [spec.candidate_id]}]}
    path = result_dir / "FINAL_ALPHA_SEARCH_004.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (manifest_dir / "final_search_completion_004.json").write_text(
        json.dumps({"result_sha256": digest}), encoding="utf-8")
    selection = {"candidate_id": spec.candidate_id, "stage": "PROSPECTIVE_SHADOW",
                 "parameters": spec.payload(), "result_sha256": digest,
                 "search_id": "synthetic_004"}
    frozen = manifest_dir / f"prospective_{spec.candidate_id}.json"
    frozen.write_text(json.dumps(selection), encoding="utf-8")
    assert approved_factor(tmp_path, spec.candidate_id) == (spec, "PROSPECTIVE_SHADOW")
    with pytest.raises(PermissionError, match="paper"):
        approved_factor(tmp_path, spec.candidate_id, Mode.PAPER)
    selection["parameters"]["threshold"] = .99
    frozen.write_text(json.dumps(selection), encoding="utf-8")
    with pytest.raises(PermissionError, match="disagrees"):
        approved_factor(tmp_path, spec.candidate_id)
