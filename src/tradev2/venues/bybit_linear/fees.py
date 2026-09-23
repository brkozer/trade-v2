from tradev2.domain.market import FeeSchedule


def resolve_fee(symbol: str, now_ms: int, fresh: FeeSchedule | None,
                cached: FeeSchedule | None, conservative: FeeSchedule | None) -> FeeSchedule:
    for schedule in (fresh, cached, conservative):
        if schedule is not None and schedule.symbol in (symbol, "*") and schedule.usable(now_ms):
            return schedule
    raise ValueError("FEE_UNKNOWN: no verified current or conservative schedule")

