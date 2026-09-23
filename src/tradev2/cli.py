"""Explicit finite public-data simulation and read-only operator API commands."""

import argparse
import json
import time
from pathlib import Path

import uvicorn

from tradev2.config.loader import load_config
from tradev2.config.models import Mode
from tradev2.config.privilege import require_runtime_mode
from tradev2.domain.evidence import EvidenceEnvelope
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import create_manifest
from tradev2.marketdata.recorder import record_public
from tradev2.runtime.coordinator import SimulationRuntime
from tradev2.venues.bybit_linear.public import PublicBybit


def main() -> None:
    parser = argparse.ArgumentParser(prog="tradev2")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="finite paper/shadow public-data simulation")
    run.add_argument("--config", type=Path, default=Path("configs/paper.json"))
    run.add_argument("--mode", choices=["paper", "shadow"])
    run.add_argument("--cycles", type=int, default=3)
    run.add_argument("--interval-seconds", type=float, default=5)
    run.add_argument("--resume", type=str)
    serve = commands.add_parser("serve", help="local read-only workstation API")
    serve.add_argument("--port", type=int, default=8000)
    recorder = commands.add_parser("record-public", help="finite public orderbook/trade recorder")
    recorder.add_argument("--symbols", nargs="+", required=True)
    recorder.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
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
            for index in range(args.cycles):
                runtime.poll(client)
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
                          "cycles": args.cycles, "orders_simulated": len(runtime.broker.orders),
                          "live_requests": 0}, indent=2))
        return
    if args.command == "record-public":
        symbols = tuple(s.upper() for s in args.symbols)
        if any(not s.isalnum() or not s.endswith("USDT") for s in symbols):
            parser.error("only uppercase USDT linear symbols supported")
        config = load_config(root / "configs/shadow.json")
        manifest = create_manifest(root, config, {"recorder": "public_orderbook_trade_v1",
                                                   "symbols": symbols})
        journal = Journal(root / "runtime" / "recorder" / manifest.run_id / "journal.sqlite")
        try:
            journal.register(manifest)
            counts = record_public(journal, manifest.run_id, symbols, args.seconds)
            journal.append(EvidenceEnvelope(event_id=manifest.run_id+"-complete",
                run_id=manifest.run_id, kind="recorder_complete", recorded_ms=time.time_ns()//1_000_000,
                source="recorder", payload=counts))
        finally:
            journal.close()
        print(json.dumps({"run_id": manifest.run_id, **counts}, indent=2))


if __name__ == "__main__":
    main()
