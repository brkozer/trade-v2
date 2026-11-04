import json
import sqlite3
import subprocess
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.evidence.journal import latest_activity_ms, open_reader, read_kinds, verify_connection
from tradev2.evidence.sealed_research import SealedSearch, load_sealed_searches
from tradev2.marketdata.recording_audit import (
    RecordingIncompleteError,
    RecordingIntegrityError,
    completion_events,
    inspect_recording,
)
from tradev2.research.prospective_chain import summarize_prospective_evidence


class RuntimeView(BaseModel):
    mode: str | None = None
    run_id: str | None = None
    status: str = "NOT_RUNNING"
    candidate_id: str | None = None
    candidate_stage: str | None = None
    freshness: Literal["FRESH", "STALE", "UNKNOWN"] = "UNKNOWN"
    age_ms: int | None = None
    source_ms: int | None = None
    source_freshness: Literal["FRESH", "STALE", "UNKNOWN"] = "UNKNOWN"
    pending_halt: bool | None = None
    halt_reason: str | None = None
    engine: Literal["ENGINE_UNKNOWN"] = "ENGINE_UNKNOWN"
    safety: Literal["ENTRY_BLOCKED"] = "ENTRY_BLOCKED"
    live: Literal["LIVE_DISABLED"] = "LIVE_DISABLED"


class EvidenceView(BaseModel):
    """Journal integrity and sealed-research integrity are separate observations."""
    integrity: str
    errors: list[str]
    journals: int
    window_limit_per_kind: int = 1000
    research_integrity: Literal["VERIFIED", "FAILED", "UNKNOWN"] = "UNKNOWN"
    research_errors: list[str] = []


class Workstation(BaseModel):
    schema_version: int = 1
    generated_ms: int
    runtime: RuntimeView
    account: dict[str, Any] | None
    events: dict[str, list[EvidenceEnvelope]]
    manifests: list[dict[str, Any]]
    campaign: dict[str, Any] | None
    searches: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    performance: dict[str, Any] = {}
    prospective: dict[str, Any] = {}
    evidence: EvidenceView
    system: dict[str, Any]


KINDS = ("runtime", "account", "opportunity", "decision", "rejection", "order", "position", "fill", "trade", "funding", "market")


def _campaigns(root: Path, errors: list[str],
               selected_search_id: str | None = None) -> tuple[SealedSearch | None, list[dict[str, Any]]]:
    """Verified sealed searches; the latest completed one is active unless one is selected."""
    sealed = load_sealed_searches(root, errors)
    active = (next((item for item in sealed if item.search_id == selected_search_id), None)
              if selected_search_id else sealed[-1] if sealed else None)
    if selected_search_id and active is None:
        errors.append("SEARCH_NOT_FOUND_OR_UNVERIFIED")
    return active, [item.summary() for item in sealed]


def _recording_status(root: Path) -> dict[str, Any]:
    """Latest recorder journal by actual write activity; integrity is not acceptance."""
    paths = sorted((root / "runtime/recorder").glob("*/journal.sqlite"), key=latest_activity_ms)
    unknown: dict[str, Any] = {"messages": None, "books": None, "trades": None}
    if not paths:
        return {"status": "UNKNOWN", "run_id": None, "reason": None, **unknown}
    path = paths[-1]
    run_id = path.parent.name
    try:
        audit = inspect_recording(path, run_id)
        return {"status": "RECORDED_STOPPED", "reason": None, **audit}
    except RecordingIntegrityError as exc:
        return {"status": "INTEGRITY_FAILED", "run_id": run_id, "reason": str(exc), **unknown}
    except RecordingIncompleteError as exc:
        return {"status": "NOT_COMPLETED", "run_id": run_id, "reason": str(exc), **unknown}
    except ValueError as exc:
        # An open run can fail an acceptance check before its completion is written.
        status = "NOT_COMPLETED" if completion_events(path, run_id) == 0 else "UNACCEPTED"
        return {"status": status, "run_id": run_id, "reason": str(exc), **unknown}
    except (OSError, sqlite3.Error) as exc:
        return {"status": "UNAVAILABLE", "run_id": run_id, "reason": type(exc).__name__, **unknown}


def _sum_known(events: list[EvidenceEnvelope], field: str) -> str | None:
    if not events:
        return None
    total = Decimal(0)
    try:
        for event in events:
            value = event.payload.get(field)
            if value is None:
                return None
            amount = Decimal(str(value))
            if not amount.is_finite():
                return None
            total += amount
    except (InvalidOperation, ValueError):
        return None
    return str(total)


def _symbol_rows(events: dict[str, list[EvidenceEnvelope]], now: int) -> list[dict[str, Any]]:
    names = sorted({str(event.payload["symbol"]) for group in events.values()
                    for event in group if event.payload.get("symbol")})
    rows: list[dict[str, Any]] = []
    for symbol in names:
        matching = {kind: [event for event in group if event.payload.get("symbol") == symbol]
                    for kind, group in events.items()}
        market = matching["market"]
        source_ms = market[0].source_ms if market else None
        rows.append({"symbol": symbol,
                     "opportunities": len(matching["opportunity"]),
                     "signals": sum(bool(e.payload.get("signal")) for e in matching["opportunity"]),
                     "entries": len(matching["fill"]),
                     "closed_trades": len(matching["trade"]),
                     "net_usdt": _sum_known(matching["trade"], "net_pnl"),
                     "net_r": _sum_known(matching["trade"], "net_r"),
                     "fees": _sum_known(matching["trade"], "fees"),
                     "funding": _sum_known(matching["trade"], "funding"),
                     "fee_tier": None, "spread_bps": market[0].payload.get("spread_bps") if market else None,
                     "source_age_ms": now - source_ms if source_ms is not None else None,
                     "rejections": len(matching["rejection"]),
                     "scope": "LATEST_1000_EVENTS_PER_KIND"})
    return rows


def _performance(events: dict[str, list[EvidenceEnvelope]]) -> dict[str, Any]:
    trades = events["trade"]
    by_symbol: dict[str, list[EvidenceEnvelope]] = defaultdict(list)
    by_day: dict[str, list[EvidenceEnvelope]] = defaultdict(list)
    for event in trades:
        by_symbol[str(event.payload.get("symbol", "UNKNOWN"))].append(event)
        when = event.payload.get("closed_ms")
        day = time.strftime("%Y-%m-%d", time.gmtime(int(when) / 1000)) if when is not None else "UNKNOWN"
        by_day[day].append(event)
    return {"scope": "SIMULATED_LATEST_1000_CLOSED_TRADES",
            "trades": len(trades), "net_usdt": _sum_known(trades, "net_pnl"),
            "fees": _sum_known(trades, "fees"), "funding": _sum_known(trades, "funding"),
            "net_r": _sum_known(trades, "net_r"),
            "daily_net_usdt": {day: _sum_known(group, "net_pnl") for day, group in by_day.items()},
            "symbol_net_usdt": {symbol: _sum_known(group, "net_pnl") for symbol, group in by_symbol.items()},
            "strategy_attribution": None, "regime_attribution": None,
            "execution_cost": None, "drawdown": None}


def snapshot(root: Path, mode: str, run_id: str | None = None,
             search_id: str | None = None) -> Workstation:
    now = time.time_ns() // 1_000_000
    events: dict[str, list[EvidenceEnvelope]] = {kind: [] for kind in KINDS}
    manifests: list[dict[str, Any]] = []
    errors: list[str] = []
    research_errors: list[str] = []
    paths = sorted((root / "runtime" / mode).glob("*/journal.sqlite"))
    if run_id:
        paths = [path for path in paths if path.parent.name == run_id]
    # A workstation observes one run; never sum unrelated accounts across sessions.
    # Recency is the newest journaled event, not a file modification time.
    if paths:
        paths = [max(paths, key=latest_activity_ms)]
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):
            errors.append("JOURNAL_OUTSIDE_ROOT")
            continue
        try:
            connection = open_reader(path)
            try:
                # One read transaction: verification and every kind see the same snapshot.
                connection.execute("BEGIN")
                if not verify_connection(connection):
                    errors.append("JOURNAL_INTEGRITY_FAILED")
                    continue
                loaded_manifests = [json.loads(row[0])
                                    for row in connection.execute("SELECT manifest FROM runs")]
                loaded = {kind: [EvidenceEnvelope.model_validate(row) for row in rows]
                          for kind, rows in read_kinds(connection, KINDS).items()}
            finally:
                connection.close()
            manifests.extend(loaded_manifests)
            events.update(loaded)
        except (sqlite3.Error, ValueError, OSError):
            # Fail closed: never serve a partially read journal as runtime truth.
            events = {kind: [] for kind in KINDS}
            manifests = []
            errors.append("JOURNAL_UNAVAILABLE")
    runtime = RuntimeView(mode=mode, status="UNKNOWN" if errors else "NOT_RUNNING")
    if events["runtime"]:
        latest = events["runtime"][0]
        age = now - latest.recorded_ms
        source_age = now - latest.source_ms if latest.source_ms is not None else None
        reported = str(latest.payload.get("status", "UNKNOWN"))
        runtime = RuntimeView(mode=mode, run_id=latest.run_id,
                              status="RUNNING_UNVERIFIED" if reported == "RUNNING" else reported,
                              candidate_id=latest.payload.get("candidate_id"),
                              candidate_stage=latest.payload.get("candidate_stage"),
                              freshness="FRESH" if 0 <= age <= 30_000 else "STALE",
                              age_ms=age, source_ms=latest.source_ms,
                              pending_halt=(latest.payload["pending_halt"]
                                            if isinstance(latest.payload.get("pending_halt"), bool)
                                            else None),
                              halt_reason=latest.payload.get("halt_reason"),
                              source_freshness="UNKNOWN" if source_age is None else "FRESH"
                              if 0 <= source_age <= 30_000 else "STALE")
    active, searches = _campaigns(root, research_errors, search_id)
    latest_market = events["market"][0] if events["market"] else None
    if latest_market is None or latest_market.source_ms is None:
        public_market = "UNKNOWN"
    elif runtime.status not in {"RUNNING", "RUNNING_UNVERIFIED"}:
        public_market = "RECORDED_NOT_CONNECTED"
    elif 0 <= now - latest_market.source_ms <= 30_000:
        public_market = "PUBLIC_OBSERVED_FRESH"
    else:
        public_market = "PUBLIC_STALE"
    try:
        software_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        software_sha = None
    return Workstation(generated_ms=now, runtime=runtime,
                       account=events["account"][0].payload if events["account"] else None,
                       events=events, manifests=manifests,
                       campaign=active.evidence if active else None,
                       searches=searches,
                       candidates=active.candidate_rows() if active else [],
                       experiments=active.experiment_rows() if active else [],
                       symbols=_symbol_rows(events, now), performance=_performance(events),
                       prospective=summarize_prospective_evidence(root, now_ms=now),
                       evidence=EvidenceView(integrity="FAILED" if errors else "VERIFIED" if paths else "UNKNOWN",
                                             errors=errors, journals=len(paths),
                                             research_integrity="FAILED" if research_errors
                                             else "VERIFIED" if searches else "UNKNOWN",
                                             research_errors=research_errors),
                       system={"api": "AVAILABLE", "authority": "READ_ONLY", "live": "LIVE_DISABLED",
                               "git_sha": software_sha,
                               "public_market": public_market,
                               "reconciliation": None, "protection": None,
                               "testnet": "DEDICATED_AUTHORIZATION_REQUIRED",
                               "public_recorder": _recording_status(root)})


def _integrity(view: Workstation) -> dict[str, Any]:
    """Every resource envelope states which evidence it was derived from and its checks."""
    return {"journal": view.evidence.integrity, "journal_errors": view.evidence.errors,
            "research": view.evidence.research_integrity,
            "research_errors": view.evidence.research_errors,
            "search_id": (view.campaign or {}).get("search_id")}


def create_app(root: Path | None = None) -> FastAPI:
    project = root or Path(__file__).resolve().parents[3]
    app = FastAPI(title="Trade v2 read-only evidence API", version="1.0")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "AVAILABLE", "live": "LIVE_DISABLED"}

    def checked(mode: str, run_id: str | None, search_id: str | None) -> Workstation:
        view = snapshot(project, mode, run_id, search_id)
        if search_id and view.campaign is None:
            raise HTTPException(404, "Sealed research search not found")
        if run_id and view.evidence.journals == 0:
            raise HTTPException(404, "Simulation run not found")
        return view

    @app.get("/api/v1/workstation", response_model=Workstation)
    def workstation(mode: Literal["paper", "shadow"] = "paper",
                    run_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$"),
                    search_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_]+$")) -> Workstation:
        return checked(mode, run_id, search_id)

    @app.get("/api/v1/{resource}")
    def resource_view(resource: str, mode: Literal["paper", "shadow"] = "paper",
                      run_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$"),
                      search_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_]+$")) -> dict[str, Any]:
        view = checked(mode, run_id, search_id)
        aliases = {"positions": "position", "orders": "order", "fills": "fill", "trades": "trade",
                   "opportunities": "opportunity", "decisions": "decision",
                   "rejections": "rejection"}
        result: Any
        if resource in aliases:
            result = [event.model_dump(mode="json") for event in view.events[aliases[resource]]]
        elif resource == "symbols":
            result = view.symbols
        elif resource in {"runtime", "account", "system-health", "evidence-health", "run-manifests",
                          "system-info", "reconciliation", "recorder-status", "accounting",
                          "prospective-evidence"}:
            key = {"system-health": "system", "system-info": "system",
                   "evidence-health": "evidence", "run-manifests": "manifests",
                   "accounting": "account", "prospective-evidence": "prospective"}.get(resource, resource)
            if resource == "reconciliation":
                result = view.system["reconciliation"]
            elif resource == "recorder-status":
                result = view.system["public_recorder"]
            else:
                result = view.model_dump(mode="json")[key]
        elif resource in {"candidates", "searches", "search-runs", "experiments", "research-results"}:
            result = view.candidates if resource == "candidates" else (
                view.searches if resource in {"searches", "search-runs"} else
                view.campaign if resource == "research-results" else view.experiments)
        elif resource == "performance":
            result = {"account": view.account, "curve": [event.model_dump(mode="json") for event in reversed(view.events["account"])], **view.performance}
        else:
            raise HTTPException(404, "Unknown evidence resource")
        return {"schema_version": 1, "generated_ms": view.generated_ms,
                "integrity": _integrity(view), "data": result}

    @app.get("/api/v1/candidates/{family}")
    def candidate_detail(family: str, search_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_]+$")) -> dict[str, Any]:
        view = checked("paper", None, search_id)
        rows = [row for row in view.candidates if row.get("family") == family]
        if not rows:
            raise HTTPException(404, "Candidate family not present in sealed research")
        data: dict[str, Any] = rows[0] if len(rows) == 1 else {
            "family": family, "search_id": (view.campaign or {}).get("search_id"),
            "configurations": rows}
        return {"schema_version": 1, "generated_ms": view.generated_ms,
                "integrity": _integrity(view), "data": data}

    return app


app = create_app()
