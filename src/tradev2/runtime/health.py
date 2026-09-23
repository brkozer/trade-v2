from enum import StrEnum

from tradev2.domain.base import FrozenModel


class Freshness(StrEnum):
    FRESH = "SOURCE_FRESH"
    STALE = "SOURCE_STALE"
    UNKNOWN = "SOURCE_UNKNOWN"


def freshness(source_ms: int | None, observed_ms: int, max_age_ms: int) -> Freshness:
    if source_ms is None or source_ms > observed_ms or source_ms < 0:
        return Freshness.UNKNOWN
    return Freshness.FRESH if observed_ms - source_ms <= max_age_ms else Freshness.STALE


class SafetyHealth(FrozenModel):
    engine: str
    source: Freshness
    safety: str
    pending_halt: bool
    reason: str
    observed_ms: int


def evaluate_health(*, now_ms: int, engine_alive: bool | None, heartbeat_ms: int | None,
                    source_ms: int | None, readable: bool, previous_halt: bool,
                    halt_requested: bool = False, heartbeat_max_age_ms: int = 30000,
                    source_max_age_ms: int = 15000) -> SafetyHealth:
    engine = "ENGINE_UNKNOWN" if engine_alive is None else (
        "ENGINE_ALIVE" if engine_alive else "ENGINE_DEAD")
    source = freshness(source_ms, now_ms, source_max_age_ms)
    heartbeat = freshness(heartbeat_ms, now_ms, heartbeat_max_age_ms)
    pending = previous_halt or halt_requested
    current = readable and engine_alive is True and heartbeat == Freshness.FRESH
    safe = current and source == Freshness.FRESH and not pending
    return SafetyHealth(engine=engine, source=source,
                        safety="CURRENT_SAFE" if safe else "ENTRY_BLOCKED",
                        pending_halt=pending,
                        reason="current_evidence" if safe else "halt_or_unproven_current_state",
                        observed_ms=now_ms)

