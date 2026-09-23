from tradev2.config.models import Mode

LIVE_DISABLED = True

# A partial order: public-data modes share no authenticated capability. Research
# cannot enable networking by a CLI override; testnet never becomes production.
DOWNGRADES: dict[Mode, frozenset[Mode]] = {
    Mode.RESEARCH: frozenset({Mode.RESEARCH}),
    Mode.PAPER: frozenset({Mode.PAPER, Mode.RESEARCH}),
    Mode.SHADOW: frozenset({Mode.SHADOW, Mode.PAPER, Mode.RESEARCH}),
    Mode.TESTNET: frozenset({Mode.TESTNET, Mode.SHADOW, Mode.PAPER, Mode.RESEARCH}),
    Mode.LIVE: frozenset(Mode),
}


def override_mode(configured: Mode, requested: Mode) -> Mode:
    if requested not in DOWNGRADES[configured]:
        raise PermissionError(f"Mode escalation prohibited: {configured} -> {requested}")
    return requested


def require_runtime_mode(mode: Mode) -> None:
    if mode == Mode.LIVE:
        raise PermissionError("LIVE_DISABLED: live transport is unavailable")
    if mode == Mode.TESTNET:
        raise PermissionError("TESTNET_NOT_ENABLED: preflight only; no authenticated transport")

