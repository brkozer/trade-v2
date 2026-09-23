import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel

from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.evidence.journal import open_reader, read_events, verify_connection
from tradev2.marketdata.recording_audit import inspect_recording


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
    searches: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    performance: dict[str, Any] = {}
    evidence: EvidenceView
    system: dict[str, Any]


KINDS = ("runtime", "account", "opportunity", "decision", "rejection", "order", "position", "fill", "trade", "funding", "market")


def _campaigns(root: Path, errors: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    campaigns: list[dict[str, Any]] = []
    for name, marker in (("campaign.json", "initial_campaign_completion.json"),
                         ("FINAL_ALPHA_SEARCH_003.json", "final_search_completion_003.json")):
        path = root / "research/results" / name
        completion = root / "research/manifests" / marker
        if not path.exists():
            continue
        try:
            if not path.resolve().is_relative_to(root.resolve()) or not completion.is_file():
                raise ValueError("research artifact outside target or completion missing")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            seal = json.loads(completion.read_text(encoding="utf-8"))
            if (not isinstance(evidence, dict) or evidence.get("complete") is not True
                    or hashlib.sha256(path.read_bytes()).hexdigest() != seal["result_sha256"]):
                raise ValueError("campaign checksum or completeness invalid")
            campaigns.append(evidence)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            errors.append(f"CAMPAIGN_INTEGRITY_FAILED:{name}")
    active = campaigns[-1] if campaigns else None
    summaries = [{"search_id": c.get("search_id"), "generated_at": c.get("generated_at"),
                  "dataset": (c.get("dataset") or {}).get("id"),
                  "configurations": (c.get("search_budget") or {}).get("configurations"),
                  "evaluations": (c.get("search_budget") or {}).get("total_replays"),
                  "promoted": len(c.get("promoted_candidates") or []),
                  "holdout_state": c.get("final_holdout_state"), "complete": True}
                 for c in campaigns]
    return active, summaries


def _experiments(campaign: dict[str, Any] | None) -> list[dict[str, Any]]:
    if campaign is None:
        return []
    rows: list[dict[str, Any]] = []
    for family in campaign.get("families", []):
        for fold in family.get("folds", []):
            for treatment, result in fold.get("stress", {}).items():
                paired = result.get("paired")
                if not isinstance(paired, dict):
                    continue
                rows.append({"hypothesis": family["family"], "baseline": "base_taker",
                             "treatment": treatment, "sample_unit": "common_opportunity_intent",
                             "n": paired.get("common_opportunities"),
                             "paired_net_delta": paired.get("paired_net_delta"),
                             "mean_paired_delta": paired.get("mean_paired_delta"),
                             "ci": None, "multiple_testing_family": campaign.get("search_id"),
                             "checkpoint": fold.get("fold"), "status": "DESCRIPTIVE_ONLY",
                             "unpaired_portfolio_delta": paired.get("unpaired_portfolio_delta")})
    return rows


def _recording_status(root: Path) -> dict[str, Any]:
    paths = sorted((root / "runtime/recorder").glob("*/journal.sqlite"),
                   key=lambda path: path.stat().st_mtime_ns)
    if not paths:
        return {"status": "UNKNOWN", "messages": None, "books": None, "trades": None}
    path = paths[-1]
    try:
        audit = inspect_recording(path, path.parent.name)
        return {"status": "RECORDED_STOPPED", **audit}
    except (ValueError, OSError, sqlite3.Error):
        return {"status": "INTEGRITY_FAILED", "messages": None, "books": None, "trades": None}


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
    campaign, searches = _campaigns(root, errors)
    return Workstation(generated_ms=now, runtime=runtime,
                       account=events["account"][0].payload if events["account"] else None,
                       events=events, manifests=manifests, campaign=campaign,
                       searches=searches, experiments=_experiments(campaign),
                       symbols=_symbol_rows(events, now), performance=_performance(events),
                       evidence=EvidenceView(integrity="FAILED" if errors else "VERIFIED" if paths else "UNKNOWN",
                                             errors=errors, journals=len(paths)),
                       system={"api": "AVAILABLE", "authority": "READ_ONLY", "live": "LIVE_DISABLED",
                               "reconciliation": None, "protection": None,
                               "testnet": "DEDICATED_AUTHORIZATION_REQUIRED",
                               "public_recorder": _recording_status(root)})


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
        aliases = {"positions": "position", "orders": "order", "fills": "fill", "trades": "trade",
                   "opportunities": "opportunity", "decisions": "decision",
                   "rejections": "rejection"}
        result: Any
        if resource in aliases:
            result = [event.model_dump(mode="json") for event in view.events[aliases[resource]]]
        elif resource == "symbols":
            result = view.symbols
        elif resource in {"runtime", "account", "system-health", "evidence-health", "run-manifests"}:
            key = {"system-health": "system", "evidence-health": "evidence", "run-manifests": "manifests"}.get(resource, resource)
            result = view.model_dump(mode="json")[key]
        elif resource in {"candidates", "searches", "experiments"}:
            result = (view.campaign or {}).get("families", []) if resource == "candidates" else (
                view.searches if resource == "searches" else view.experiments)
        elif resource == "performance":
            result = {"account": view.account, "curve": [event.model_dump(mode="json") for event in reversed(view.events["account"])], **view.performance}
        else:
            raise HTTPException(404, "Unknown evidence resource")
        return {"schema_version": 1, "generated_ms": view.generated_ms, "data": result}

    return app


app = create_app()
