"""Explicit finite public-data simulation and read-only operator API commands."""

import argparse
import json
import time
import uuid
from pathlib import Path

import httpx
import uvicorn

from tradev2.config.loader import load_config
from tradev2.config.models import Mode
from tradev2.config.privilege import require_runtime_mode
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import create_manifest
from tradev2.marketdata.clock import observe_public_clock
from tradev2.marketdata.recorder import record_public
from tradev2.marketdata.recording_audit import inspect_recording
from tradev2.runtime.coordinator import SimulationRuntime
from tradev2.venues.bybit_linear.public import PublicBybit


def _public_recorder_manifest(root: Path, symbols: tuple[str, ...]) -> RunManifest:
    base = load_config(root / "configs/shadow.json")
    config = base.model_copy(update={"symbols": symbols, "profile": "public-recorder",
                                     "candidate_id": "PUBLIC_RECORDER"})
    manifest = create_manifest(root, config, {"recorder": "public_orderbook_trade_v1",
                                              "symbols": symbols})
    return manifest.model_copy(update={
        "fee_provenance": "public market data only; no authenticated fee schedule",
        "initial_equity_source": None,
    })


def _record_public_clock_probe(journal: Journal, run_id: str, phase: str) -> None:
    if phase not in {"start", "end"}:
        raise ValueError("clock probe phase must be start or end")
    try:
        client = PublicBybit(timeout=2)
        try:
            probe = observe_public_clock(client)
        finally:
            client.close()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex, run_id=run_id,
            kind="clock_probe_failure", recorded_ms=time.time_ns() // 1_000_000,
            source="bybit_public_rest", payload={"phase": phase, "reason": type(exc).__name__}))
        return
    journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex, run_id=run_id,
        kind="clock_probe", recorded_ms=int(probe["local_after_ms"]),
        source_ms=int(probe["server_ms"]), source="bybit_public_rest",
        payload={"phase": phase, **probe}))


def main() -> None:
    parser = argparse.ArgumentParser(prog="tradev2")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="finite paper/shadow public-data simulation")
    run.add_argument("--config", type=Path, default=Path("configs/paper.json"))
    run.add_argument("--mode", choices=["paper", "shadow"])
    run.add_argument("--cycles", type=int, default=3)
    run.add_argument("--interval-seconds", type=float, default=5)
    run.add_argument("--resume", type=str)
    inspect_runtime = commands.add_parser("inspect-runtime", help="read the latest local simulation evidence")
    inspect_runtime.add_argument("--mode", choices=["paper", "shadow"], default="paper")
    stop_runtime = commands.add_parser("stop-runtime", help="request a finite simulation to stop cleanly")
    stop_runtime.add_argument("--mode", choices=["paper", "shadow"], required=True)
    stop_runtime.add_argument("--run-id", required=True)
    candidates = commands.add_parser("inspect-candidates", help="summarize immutable search results")
    candidates.add_argument("--search", choices=["initial", "final", "004"], default="final")
    research = commands.add_parser("research", help="run a frozen one-shot research identity")
    research.add_argument("--search", choices=["final", "004"], required=True)
    commands.add_parser("collect-search004", help="collect a new target-local public-only 004 dataset once")
    commands.add_parser("preregister-search004", help="freeze 004 design and data hashes once")
    commands.add_parser("replay-parity", help="run deterministic replay/runtime parity tests")
    preflight = commands.add_parser("testnet-preflight", help="local fail-closed testnet readiness report; no connection")
    preflight.add_argument("--config", type=Path, default=Path("configs/testnet.example.json"))
    analyze = commands.add_parser("analyze-microstructure", help="inspect a target-local public recorder run")
    analyze.add_argument("--run-id", required=True)
    analyze.add_argument("--save", action="store_true", help="create immutable smoke result under research/results")
    serve = commands.add_parser("serve", help="local read-only workstation API")
    serve.add_argument("--port", type=int, default=8000)
    recorder = commands.add_parser("record-public", help="finite public orderbook/trade recorder")
    recorder.add_argument("--symbols", nargs="+", required=True)
    recorder.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.command == "inspect-runtime":
        from tradev2.api.server import snapshot
        view = snapshot(root, args.mode)
        print(json.dumps({"runtime": view.runtime.model_dump(mode="json"),
                          "account": view.account, "evidence": view.evidence.model_dump(mode="json")}, indent=2))
        return
    if args.command == "stop-runtime":
        if len(args.run_id) != 32 or any(c not in "0123456789abcdef" for c in args.run_id):
            parser.error("run-id must be a 32-character lowercase hex identity")
        directory = root / "runtime" / args.mode / args.run_id
        if not (directory / "journal.sqlite").is_file():
            parser.error("target-local simulation run not found")
        with (directory / "stop.request").open("x", encoding="utf-8") as handle:
            handle.write("operator requested clean stop\n")
        print(json.dumps({"run_id": args.run_id, "status": "STOP_REQUESTED"}))
        return
    if args.command == "inspect-candidates":
        from tradev2.api.server import _campaigns
        issues: list[str] = []
        active, searches = _campaigns(root, issues)
        name = {"initial": "TRADEV2_INITIAL_ALPHA_001", "final": "TRADEV2_FINAL_ALPHA_003",
                "004": "TRADEV2_ALPHA_SEARCH_004"}[args.search]
        selected = next((s for s in searches if s["search_id"] == name), None)
        if selected is None or issues:
            raise ValueError(f"search unavailable or integrity failed: {name}; {issues}")
        path = root / "research/results" / {"initial": "campaign.json",
            "final": "FINAL_ALPHA_SEARCH_003.json", "004": "ALPHA_SEARCH_004.json"}[args.search]
        campaign = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"search": selected, "families": [
            {"family": row["family"], "status": row["status"],
             "net_r": row.get("forward_mean_net_r", (row.get("forward") or row.get("oos") or {}).get("mean_net_r")),
             "reasons": row.get("reasons") or row.get("reason")} for row in campaign["families"]]}, indent=2))
        return
    if args.command == "collect-search004":
        from tradev2.alpha.search004_data import collect
        print(json.dumps(collect(root), indent=2))
        return
    if args.command == "preregister-search004":
        from tradev2.alpha.search004 import preregister
        print(preregister(root))
        return
    if args.command == "research":
        if args.search == "004":
            from tradev2.alpha.search004 import run as run_004
            result_004 = run_004(root)
            print(json.dumps({"search_id": result_004["search_id"],
                              "promoted": result_004["promoted_candidates"]}, indent=2))
            return
        from tradev2.alpha.completion import run as run_final
        result = run_final(root, root / "data/public/completion_campaign")
        print(json.dumps({"search_id": result["search_id"],
                          "promoted": result["promoted_candidates"]}, indent=2))
        return
    if args.command == "replay-parity":
        import subprocess
        import sys
        raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/parity"], cwd=root))
    if args.command == "testnet-preflight":
        from tradev2.runtime.startup import startup_gate
        config = load_config(args.config)
        if config.mode != Mode.TESTNET:
            parser.error("testnet preflight requires a testnet-mode config")
        state = startup_gate({})
        print(json.dumps({"status": state.status, "missing": state.missing,
                          "dedicated_authorization": config.testnet_authorized,
                          "network_requests": 0, "live": "LIVE_DISABLED"}, indent=2))
        return
    if args.command == "analyze-microstructure":
        from tradev2.research.microstructure import analyze as analyze_recording
        if len(args.run_id) != 32 or any(c not in "0123456789abcdef" for c in args.run_id):
            parser.error("run-id must be a 32-character lowercase hex identity")
        path = root / "runtime/recorder" / args.run_id / "journal.sqlite"
        result = analyze_recording(path, args.run_id)
        if args.save:
            target = root / "research/results" / f"PROSPECTIVE_MICROSTRUCTURE_SMOKE_{args.run_id}.json"
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
        print(json.dumps({"run_id": args.run_id, "symbols": result["symbols"],
                          "experiment_arms": len(result["execution_experiments"]),
                          "status": result["status"]}, indent=2))
        return
    if args.command == "serve":
        if not 1024 <= args.port <= 65535:
            parser.error("port must be 1024..65535")
        uvicorn.run("tradev2.api.server:app", host="127.0.0.1", port=args.port,
                    log_level="info")
        return
    if args.command == "run":
        if not 1 <= args.cycles <= 10000 or not 0 <= args.interval_seconds <= 3600:
            parser.error("cycles must be 1..10000 and interval 0..3600 seconds")
        config = load_config(args.config, Mode(args.mode) if args.mode else None)
        require_runtime_mode(config.mode)
        runtime = SimulationRuntime(root, config, resume=args.resume)
        client = PublicBybit()
        failed = True
        try:
            completed = 0
            for index in range(args.cycles):
                runtime.poll(client)
                completed += 1
                if (root / "runtime" / config.mode / runtime.manifest.run_id / "stop.request").exists():
                    break
                if index < args.cycles - 1:
                    time.sleep(args.interval_seconds)
            failed = False
        except Exception as exc:
            runtime.emit("runtime", {"status": "FAILED", "error": type(exc).__name__,
                                     "detail": str(exc)[:200]})
            raise
        finally:
            client.close()
            runtime.close(failed=failed)
        print(json.dumps({"mode": config.mode.value, "run_id": runtime.manifest.run_id,
                          "cycles": completed, "orders_simulated": len(runtime.broker.orders),
                          "live_requests": 0}, indent=2))
        return
    if args.command == "record-public":
        symbols = tuple(s.upper() for s in args.symbols)
        if any(not s.isalnum() or not s.endswith("USDT") for s in symbols):
            parser.error("only uppercase USDT linear symbols supported")
        manifest = _public_recorder_manifest(root, symbols)
        journal_path = root / "runtime" / "recorder" / manifest.run_id / "journal.sqlite"
        journal = Journal(journal_path)
        try:
            journal.register(manifest)
            _record_public_clock_probe(journal, manifest.run_id, "start")
            counts = record_public(journal, manifest.run_id, symbols, args.seconds)
            _record_public_clock_probe(journal, manifest.run_id, "end")
            journal.append(EvidenceEnvelope(event_id=manifest.run_id+"-complete",
                run_id=manifest.run_id, kind="recorder_complete", recorded_ms=time.time_ns()//1_000_000,
                source="recorder", payload=counts))
        finally:
            journal.close()
        accepted = inspect_recording(journal_path, manifest.run_id)
        if accepted["messages"] != counts["messages"] or accepted["trades"] != counts["trades"]:
            raise RuntimeError("public recorder read-back counts disagree")
        print(json.dumps({"run_id": manifest.run_id, **counts,
                          "readback": accepted}, indent=2))


if __name__ == "__main__":
    main()
