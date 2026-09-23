import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel

from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.evidence.journal import open_reader, read_events, verify_connection


class RuntimeView(BaseModel):
    mode: str | None = None
    run_id: str | None = None
    status: str = "UNKNOWN"
    freshness: Literal["FRESH", "STALE", "UNKNOWN"] = "UNKNOWN"
    age_ms: int | None = None
    source_ms: int | None = None
    source_freshness: Literal["FRESH", "STALE", "UNKNOWN"] = "UNKNOWN"
    engine: Literal["ENGINE_UNKNOWN"] = "ENGINE_UNKNOWN"
    safety: Literal["ENTRY_BLOCKED"] = "ENTRY_BLOCKED"
    live: Literal["LIVE_DISABLED"] = "LIVE_DISABLED"


class EvidenceView(BaseModel):
    integrity: str
    errors: list[str]
    journals: int
    window_limit_per_kind: int = 1000


class Workstation(BaseModel):
    schema_version: int = 1
    generated_ms: int
    runtime: RuntimeView
    account: dict[str, Any] | None
    events: dict[str, list[EvidenceEnvelope]]
    manifests: list[dict[str, Any]]
    campaign: dict[str, Any] | None
    evidence: EvidenceView
    system: dict[str, Any]


KINDS = ("runtime", "account", "opportunity", "decision", "rejection", "order", "position", "trade", "market")


def snapshot(root: Path, mode: str, run_id: str | None = None) -> Workstation:
    now = time.time_ns() // 1_000_000
    events: dict[str, list[EvidenceEnvelope]] = {kind: [] for kind in KINDS}
    manifests: list[dict[str, Any]] = []
    errors: list[str] = []
    paths = sorted((root / "runtime" / mode).glob("*/journal.sqlite"))
    if run_id:
        paths = [path for path in paths if path.parent.name == run_id]
    # A workstation observes one run; never sum unrelated accounts across sessions.
    if paths:
        paths = [max(paths, key=lambda path: path.stat().st_mtime_ns)]
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):
            errors.append("JOURNAL_OUTSIDE_ROOT")
            continue
        try:
            connection = open_reader(path)
            try:
                if not verify_connection(connection):
                    errors.append("JOURNAL_INTEGRITY_FAILED")
                    continue
                manifests.extend(json.loads(row[0]) for row in connection.execute("SELECT manifest FROM runs"))
            finally:
                connection.close()
            for kind in KINDS:
                events[kind] = [EvidenceEnvelope.model_validate(row) for row in read_events(path, kind)]
        except (sqlite3.Error, ValueError, OSError):
            errors.append("JOURNAL_UNAVAILABLE")
    runtime = RuntimeView(mode=mode)
    if events["runtime"]:
        latest = events["runtime"][0]
        age = now - latest.recorded_ms
        source_age = now - latest.source_ms if latest.source_ms is not None else None
        reported = str(latest.payload.get("status", "UNKNOWN"))
        runtime = RuntimeView(mode=mode, run_id=latest.run_id,
                              status="RUNNING_UNVERIFIED" if reported == "RUNNING" else reported,
                              freshness="FRESH" if 0 <= age <= 30_000 else "STALE",
                              age_ms=age, source_ms=latest.source_ms,
                              source_freshness="UNKNOWN" if source_age is None else "FRESH"
                              if 0 <= source_age <= 30_000 else "STALE")
    campaign = None
    campaign_path = root / "research" / "results" / "campaign.json"
    if campaign_path.exists() and campaign_path.resolve().is_relative_to(root.resolve()):
        try:
            value = json.loads(campaign_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("campaign must be object")
            campaign = value
        except (OSError, ValueError):
            errors.append("CAMPAIGN_UNAVAILABLE")
    return Workstation(generated_ms=now, runtime=runtime,
                       account=events["account"][0].payload if events["account"] else None,
                       events=events, manifests=manifests, campaign=campaign,
                       evidence=EvidenceView(integrity="FAILED" if errors else "VERIFIED" if paths else "UNKNOWN",
                                             errors=errors, journals=len(paths)),
                       system={"api": "AVAILABLE", "authority": "READ_ONLY", "live": "LIVE_DISABLED",
                               "reconciliation": None, "protection": None})


def create_app(root: Path | None = None) -> FastAPI:
    project = root or Path(__file__).resolve().parents[3]
    app = FastAPI(title="Trade v2 read-only evidence API", version="1.0")

    @app.get("/api/v1/workstation", response_model=Workstation)
    def workstation(mode: Literal["paper", "shadow"] = "paper",
                    run_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$")) -> Workstation:
        return snapshot(project, mode, run_id)

    @app.get("/api/v1/{resource}")
    def resource_view(resource: str, mode: Literal["paper", "shadow"] = "paper",
                      run_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$")) -> dict[str, Any]:
        from fastapi import HTTPException
        view = snapshot(project, mode, run_id)
        aliases = {"positions": "position", "orders": "order", "trades": "trade",
                   "symbols": "market", "opportunities": "opportunity", "decisions": "decision",
                   "rejections": "rejection"}
        result: Any
        if resource in aliases:
            result = [event.model_dump(mode="json") for event in view.events[aliases[resource]]]
        elif resource in {"runtime", "account", "system-health", "evidence-health", "run-manifests"}:
            key = {"system-health": "system", "evidence-health": "evidence", "run-manifests": "manifests"}.get(resource, resource)
            result = view.model_dump(mode="json")[key]
        elif resource in {"candidates", "searches", "experiments"}:
            campaign = view.campaign or {}
            result = campaign.get("families", []) if resource == "candidates" else [campaign] if campaign else []
        elif resource == "performance":
            result = {"account": view.account, "curve": [event.model_dump(mode="json") for event in reversed(view.events["account"])], "scope": "SIMULATED", "attribution": None}
        else:
            raise HTTPException(404, "Unknown evidence resource")
        return {"schema_version": 1, "generated_ms": view.generated_ms, "data": result}

    return app


app = create_app()
