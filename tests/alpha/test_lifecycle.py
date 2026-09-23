import pytest

from tradev2.alpha.lifecycle import CandidateState, Stage


def test_promotions_require_distinct_evidence_and_cannot_skip() -> None:
    state = CandidateState(candidate_id="alpha")
    with pytest.raises(ValueError, match="skipped"):
        state.transition(Stage.PROSPECTIVE_SHADOW, evidence_id="winner", reason="ranked first")
    state = state.transition(Stage.RESEARCHABLE, evidence_id="data-proof", reason="point-in-time data")
    with pytest.raises(ValueError, match="reused"):
        state.transition(Stage.DISCOVERY, evidence_id="data-proof", reason="same proof")
    with pytest.raises(ValueError, match="durable"):
        state.transition(Stage.DISCOVERY, evidence_id="", reason="good")
    state = state.transition(Stage.DISCOVERY, evidence_id="prereg", reason="registered")
    assert state.stage == Stage.DISCOVERY


def test_rejection_is_terminal() -> None:
    state = CandidateState(candidate_id="alpha").transition(
        Stage.REJECTED, evidence_id="search-result", reason="negative forward net R")
    with pytest.raises(ValueError, match="terminal"):
        state.transition(Stage.RESEARCHABLE, evidence_id="another", reason="retry")
