from tradev2.domain.base import FrozenModel

REQUIRED = frozenset({"authority", "venue_identity", "account_identity", "position_mode",
                      "instruments", "fees", "owned_orders", "positions", "journal",
                      "reconciliation", "protection", "market_freshness", "safety"})


class StartupState(FrozenModel):
    status: str
    missing: tuple[str, ...]


def startup_gate(checks: dict[str, bool | None]) -> StartupState:
    unknown = set(checks) - REQUIRED
    if unknown:
        raise ValueError(f"unknown startup checks: {sorted(unknown)}")
    missing = tuple(sorted(name for name in REQUIRED if checks.get(name) is not True))
    return StartupState(status="ENTRY_BLOCKED" if missing else "ENTRY_ENABLED", missing=missing)

