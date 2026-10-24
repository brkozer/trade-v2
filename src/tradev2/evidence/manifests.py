import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from tradev2.config.models import RuntimeConfig
from tradev2.domain.evidence import RunManifest


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def software_identity(root: Path) -> dict[str, Any]:
    """The checkout and interpreter that produce subsequent evidence."""
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "--no-optional-locks", "status", "--porcelain"], cwd=root, text=True).strip())
    return {"git_sha": sha, "dirty": dirty, "python_version": platform.python_version()}


def create_manifest(root: Path, config: RuntimeConfig, parameters: dict[str, Any],
                    dataset: str | None = None) -> RunManifest:
    identity = software_identity(root)
    sha, dirty = str(identity["git_sha"]), bool(identity["dirty"])
    normalized = config.model_dump(mode="json")
    return RunManifest(
        run_id=uuid.uuid4().hex, git_sha=sha, dirty=dirty, mode=config.mode.value,
        started_ms=time.time_ns() // 1_000_000, config=normalized,
        config_hash=digest(normalized), candidate_id=config.candidate_id,
        candidate_version="1", parameter_hash=digest(parameters), venue=config.venue,
        universe=config.symbols, universe_hash=digest(config.symbols),
        fee_provenance="explicit simulation assumptions; not authenticated account fees",
        dataset_identity=dataset, python_version=platform.python_version(),
        package_versions={name: importlib.metadata.version(name)
                          for name in ("tradev2", "pydantic", "numpy", "httpx")},
        initial_equity_source="configured_simulated_equity",
    )

