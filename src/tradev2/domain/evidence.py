from typing import Any

from pydantic import Field

from tradev2.domain.base import FrozenModel


class EvidenceEnvelope(FrozenModel):
    event_id: str
    run_id: str
    kind: str
    recorded_ms: int = Field(ge=0)
    source: str
    source_ms: int | None = None
    payload: dict[str, Any]
    schema_version: int = 1


class RunManifest(FrozenModel):
    run_id: str
    git_sha: str
    dirty: bool
    mode: str
    started_ms: int
    config: dict[str, Any]
    config_hash: str
    candidate_id: str
    candidate_version: str
    parameter_hash: str
    venue: str
    universe: tuple[str, ...]
    universe_hash: str
    fee_provenance: str
    dataset_identity: str | None
    python_version: str
    package_versions: dict[str, str]
    initial_equity_source: str | None

