from pathlib import Path

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.config.privilege import override_mode


def load_config(path: Path, mode: Mode | None = None) -> RuntimeConfig:
    config = RuntimeConfig.model_validate_json(path.read_text(encoding="utf-8"))
    if mode is not None:
        config = config.model_copy(update={"mode": override_mode(config.mode, mode)})
    return config

