"""Evidence-gated candidate state changes; search rank has no authority here."""

from enum import StrEnum

from pydantic import Field

from tradev2.domain.base import FrozenModel


class Stage(StrEnum):
    IDEA = "IDEA"
    RESEARCHABLE = "RESEARCHABLE"
    DISCOVERY = "DISCOVERY"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    HOLDOUT_VALIDATED = "HOLDOUT_VALIDATED"
    PROSPECTIVE_SHADOW = "PROSPECTIVE_SHADOW"
    PAPER_EXECUTION_VALIDATED = "PAPER_EXECUTION_VALIDATED"
    TESTNET_EXECUTION_VALIDATED = "TESTNET_EXECUTION_VALIDATED"
    LIVE_CANARY_ELIGIBLE = "LIVE_CANARY_ELIGIBLE"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED_WITH_CURRENT_DATA = "UNSUPPORTED_WITH_CURRENT_DATA"


NEXT: dict[Stage, Stage] = {
    Stage.IDEA: Stage.RESEARCHABLE,
    Stage.RESEARCHABLE: Stage.DISCOVERY,
    Stage.DISCOVERY: Stage.WALK_FORWARD_VALIDATED,
    Stage.WALK_FORWARD_VALIDATED: Stage.HOLDOUT_VALIDATED,
    Stage.HOLDOUT_VALIDATED: Stage.PROSPECTIVE_SHADOW,
    Stage.PROSPECTIVE_SHADOW: Stage.PAPER_EXECUTION_VALIDATED,
    Stage.PAPER_EXECUTION_VALIDATED: Stage.TESTNET_EXECUTION_VALIDATED,
    Stage.TESTNET_EXECUTION_VALIDATED: Stage.LIVE_CANARY_ELIGIBLE,
}
TERMINAL = frozenset({Stage.REJECTED, Stage.INSUFFICIENT_EVIDENCE,
                      Stage.UNSUPPORTED_WITH_CURRENT_DATA})


class CandidateState(FrozenModel):
    candidate_id: str = Field(min_length=1)
    stage: Stage = Stage.IDEA
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None

    def transition(self, target: Stage, *, evidence_id: str, reason: str) -> "CandidateState":
        if self.stage in TERMINAL or self.stage == Stage.LIVE_CANARY_ELIGIBLE:
            raise ValueError("terminal candidate cannot transition")
        if not evidence_id.strip() or not reason.strip():
            raise ValueError("transition requires durable evidence and reason")
        if evidence_id in self.evidence_ids:
            raise ValueError("evidence cannot be reused for promotion")
        if target != NEXT[self.stage] and target not in TERMINAL:
            raise ValueError("candidate stage cannot be skipped or reversed")
        return self.model_copy(update={"stage": target,
                                       "evidence_ids": (*self.evidence_ids, evidence_id),
                                       "reason": reason})
