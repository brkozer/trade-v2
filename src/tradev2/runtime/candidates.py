"""Controlled, immutable candidate policies shared by paper and shadow.

Research fixtures are explicitly labeled and cannot claim economic promotion.
The registry contains no config-supplied Python imports or executable names.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from tradev2.alpha.factors import FactorSpec, registry
from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.market import Candle
from tradev2.research.costs import SymbolEconomics
from tradev2.runtime.factor_policy import approved_factor, latest_factor_scores
from tradev2.strategies.reference import (
    REFERENCE_PARAMS,
    reference_entry,
    reference_exit,
    wilder_rsi,
)


@dataclass(frozen=True)
class CandidateSignal:
    strength: float
    side: Literal["Buy", "Sell"] | None
    features: dict[str, Any]

    @property
    def active(self) -> bool:
        return self.side is not None


class CandidatePolicy(Protocol):
    @property
    def candidate_id(self) -> str: ...

    @property
    def family(self) -> str: ...

    @property
    def stage(self) -> str: ...

    @property
    def evidence(self) -> str: ...

    @property
    def required_bars(self) -> int: ...

    @property
    def requires_funding(self) -> bool: ...

    @property
    def stop_pct(self) -> Decimal: ...

    @property
    def target_r(self) -> Decimal: ...

    def parameters(self) -> dict[str, Any]: ...

    def signals(self, candles: dict[str, list[Candle]],
                economics: dict[str, SymbolEconomics]) -> dict[str, CandidateSignal]: ...

    def exit_reason(self, closes: list[float], held_bars: int) -> str | None: ...


@dataclass(frozen=True)
class ReferencePolicy:
    candidate_id: str = REFERENCE_PARAMS.candidate_id
    family: str = "reference_rsi_regression"
    stage: str = "TEST_FIXTURE"
    evidence: str = "LEGACY_REFERENCE_PARITY_ONLY"
    required_bars: int = 64
    requires_funding: bool = False
    stop_pct: Decimal = Decimal(str(REFERENCE_PARAMS.stop_pct))
    target_r: Decimal = Decimal(str(REFERENCE_PARAMS.target_r))

    def parameters(self) -> dict[str, Any]:
        return asdict(REFERENCE_PARAMS) | {"stage": self.stage, "evidence": self.evidence}

    def signals(self, candles: dict[str, list[Candle]],
                economics: dict[str, SymbolEconomics]) -> dict[str, CandidateSignal]:
        del economics
        result: dict[str, CandidateSignal] = {}
        for symbol, bars in candles.items():
            closes = [float(bar.close) for bar in bars]
            active = reference_entry(closes, bars[-1].start_ms)
            result[symbol] = CandidateSignal(float(active), "Buy" if active else None,
                {"rsi": wilder_rsi(closes, REFERENCE_PARAMS.entry_period)})
        return result

    def exit_reason(self, closes: list[float], held_bars: int) -> str | None:
        return reference_exit(closes, held_bars)


@dataclass(frozen=True)
class FactorPolicy:
    spec: FactorSpec
    stage: str
    evidence: str

    @property
    def candidate_id(self) -> str:
        return self.spec.candidate_id

    @property
    def family(self) -> str:
        return self.spec.family

    @property
    def required_bars(self) -> int:
        return max(250, self.spec.lookback + 3)

    @property
    def requires_funding(self) -> bool:
        return self.spec.family == "funding_crowding"

    @property
    def stop_pct(self) -> Decimal:
        return Decimal(str(self.spec.stop_pct))

    @property
    def target_r(self) -> Decimal:
        return Decimal(str(self.spec.target_r))

    def parameters(self) -> dict[str, Any]:
        return self.spec.payload() | {"stage": self.stage, "evidence": self.evidence}

    def signals(self, candles: dict[str, list[Candle]],
                economics: dict[str, SymbolEconomics]) -> dict[str, CandidateSignal]:
        values = latest_factor_scores(candles, self.spec, economics)
        return {symbol: CandidateSignal(strength=value,
            side="Buy" if value > 0 else "Sell" if value < 0 else None,
            features={"factor_score": value, "family": self.family})
            for symbol, value in values.items()}

    def exit_reason(self, closes: list[float], held_bars: int) -> str | None:
        del closes
        return "TIME_STOP" if held_bars >= self.spec.holding_bars else None


def load_candidate(root: Path, config: RuntimeConfig) -> CandidatePolicy:
    if config.candidate_id == REFERENCE_PARAMS.candidate_id:
        return ReferencePolicy()
    spec = next((item for item in registry() if item.candidate_id == config.candidate_id), None)
    if spec is None:
        raise ValueError("unknown candidate identity")
    if config.fixture_mode:
        if config.mode not in {Mode.PAPER, Mode.SHADOW}:
            raise PermissionError("factor fixture cannot use a privileged mode")
        return FactorPolicy(spec, "TEST_FIXTURE", "EXPLICIT_LOCAL_REGRESSION_FIXTURE")
    approved, stage = approved_factor(root, config.candidate_id, config.mode)
    return FactorPolicy(approved, stage, "FROZEN_RESEARCH_PROMOTION")
