from tradev2.config.models import Mode, RuntimeConfig
from tradev2.runtime.startup import StartupState, startup_gate


def preflight(config: RuntimeConfig, checks: dict[str, bool | None]) -> StartupState:
    if config.mode != Mode.TESTNET or not config.testnet_authorized:
        raise PermissionError("dedicated testnet configuration and authorization required")
    return startup_gate(checks)

