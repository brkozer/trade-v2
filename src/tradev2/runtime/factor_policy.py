"""Load only research-promoted factors into public-data simulation."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from tradev2.alpha.factors import FactorSpec, registry, signals
from tradev2.config.models import Mode
from tradev2.domain.market import Candle
from tradev2.research.costs import SymbolEconomics
from tradev2.research.datasets import Panel


def approved_factor(root: Path, candidate_id: str,
                    mode: Mode = Mode.SHADOW) -> tuple[FactorSpec, str]:
    spec = next((item for item in registry() if item.candidate_id == candidate_id), None)
    if spec is None:
        raise ValueError("candidate is not a registered factor")
    selection_path = root / "research/manifests" / f"prospective_{candidate_id}.json"
    if not selection_path.is_file():
        raise PermissionError("candidate lacks frozen prospective selection")
    selection: dict[str, Any] = json.loads(selection_path.read_text(encoding="utf-8"))
    stage = selection.get("stage")
    if (selection.get("candidate_id") != candidate_id
            or stage not in {"PROSPECTIVE_SHADOW", "PAPER_EXECUTION_VALIDATED"}
            or selection.get("parameters") != spec.payload()):
        raise PermissionError("prospective candidate manifest disagrees with registered parameters")
    if mode == Mode.PAPER and stage != "PAPER_EXECUTION_VALIDATED":
        raise PermissionError("candidate is not approved for paper runtime")
    if mode not in {Mode.PAPER, Mode.SHADOW}:
        raise PermissionError("candidate is not approved for this runtime mode")
    if stage == "PAPER_EXECUTION_VALIDATED":
        paper_path = root / "research/manifests" / f"paper_acceptance_{candidate_id}.json"
        if (not paper_path.is_file() or selection.get("paper_acceptance_sha256") !=
                hashlib.sha256(paper_path.read_bytes()).hexdigest()):
            raise PermissionError("paper acceptance evidence missing or changed")
    results = root / "research/results"
    for path in sorted(results.glob("FINAL_ALPHA_SEARCH_*.json")):
        suffix = path.stem.removeprefix("FINAL_ALPHA_SEARCH_")
        marker = root / "research/manifests" / f"final_search_completion_{suffix}.json"
        if not marker.is_file():
            continue
        seal: dict[str, Any] = json.loads(marker.read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != seal.get("result_sha256"):
            raise ValueError("candidate research artifact integrity failed")
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if result.get("complete") is not True:
            raise ValueError("candidate research artifact incomplete")
        approved = result.get("promoted_candidates", [])
        family = next((row for row in result.get("families", [])
                       if row.get("family") == spec.family), None)
        if (selection.get("result_sha256") == seal["result_sha256"]
                and selection.get("search_id") == result.get("search_id")
                and spec.family in approved and family is not None
                and family.get("status") == "PROSPECTIVE_SHADOW"
                and family.get("historical_gates_passed") is True
                and candidate_id in family.get("selected_candidates", [])):
            return spec, stage
    raise PermissionError("factor is not research-promoted for prospective simulation")


def latest_factor_scores(candles: dict[str, list[Candle]], spec: FactorSpec,
                         economics: dict[str, SymbolEconomics] | None = None) -> dict[str, float]:
    """Replay and simulation call the same frozen factor function on closed bars.

    No gap filling, cross-symbol forward filling or same-close order fill is allowed.
    The caller must independently verify quote time >= the final bar close.
    """
    symbols = tuple(sorted(candles))
    if not symbols:
        raise ValueError("factor universe empty")
    size = len(candles[symbols[0]])
    if size < max(202, spec.lookback + 3):
        raise ValueError("insufficient closed factor history")
    baseline = tuple(bar.start_ms for bar in candles[symbols[0]])
    for symbol in symbols:
        bars = candles[symbol]
        if len(bars) != size or tuple(bar.start_ms for bar in bars) != baseline:
            raise ValueError("factor universe candle alignment failed")
        if any(not bar.confirmed or bar.symbol != symbol for bar in bars):
            raise ValueError("factor inputs must be confirmed and correctly identified")
    values = np.asarray([[[float(bar.open), float(bar.high), float(bar.low),
                           float(bar.close), float(bar.volume)]
                          for symbol in symbols for bar in (candles[symbol][index],)]
                         for index in range(size)], dtype=np.float64)
    panel = Panel(symbols=symbols, timestamps=np.asarray(baseline, dtype=np.int64),
                  values=values, manifest={"source": "closed_public_runtime"})
    if spec.family == "funding_crowding" and (
        economics is None or set(economics) != set(symbols)
    ):
        raise ValueError("funding factor requires complete settled economics")
    result = signals(panel, spec, economics or {})[-1]
    return {symbol: float(result[index]) for index, symbol in enumerate(symbols)}
