"""Run one bounded public-only collection round for the prospective chains.

Built for cron or any scheduler: each call verifies the candle and OI chains through
their collectors, writes at most one new chunk per chain, and records the outcome
under `<root>/runtime/collector/`. It never starts a new OI chain (a deliberate
operator command), never backfills OI, and never runs two rounds at once.
"No newly closed interval yet" is recorded as NOT_DUE, not as a failure.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_forward_bars as bars  # noqa: E402
import collect_forward_oi as oi  # noqa: E402

from tradev2.venues.bybit_linear.public import PublicBybit  # noqa: E402

STATE_DIR = Path("runtime/collector")
OI_SUCCESSOR_HINT = ("OI chain cannot recover its gap; start its successor deliberately with "
                     "ops/collect_forward_oi.py --new-chain-reason \"<reason>\"")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def code_commit(code_root: Path) -> str | None:
    marker = code_root / "COLLECTOR_COMMIT"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip() or None
    try:
        return subprocess.check_output(["git", "-C", str(code_root), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _collect_sources(root: Path, client: PublicBybit) -> dict[str, dict[str, Any]]:
    calls: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
        ("candles", lambda: bars.collect(root, client, first_open_ms=bars.next_open(root))),
        ("open_interest", lambda: oi.collect(root, client)),
    )
    results: dict[str, dict[str, Any]] = {}
    for name, call in calls:
        try:
            manifest = call()
            results[name] = {"result": "COLLECTED", "dataset_id": manifest["dataset_id"],
                             "safe_available_ms": manifest["safe_available_ms"]}
        except (bars.NotDueError, oi.NotDueError) as exc:
            results[name] = {"result": "NOT_DUE", "detail": str(exc)}
        except Exception as exc:  # recorded as evidence of the failed round, never swallowed
            detail = f"{type(exc).__name__}: {exc}"[:500]
            results[name] = {"result": "FAILED", "error": detail}
            if name == "open_interest" and "exceeds bounded" in detail:
                results[name]["action_required"] = OI_SUCCESSOR_HINT
    return results


def run_round(root: Path, *, client_factory: Callable[[], PublicBybit] = PublicBybit,
              min_free_gb: float = 100, commit: str | None = None) -> dict[str, Any]:
    state = root / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    lock = portalocker.Lock(str(state / "round.lock"), mode="a", timeout=0,
                            fail_when_locked=True)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        return {"outcome": "SKIPPED_ROUND_IN_PROGRESS", "started_utc": _now()}
    try:
        status_path = state / "status.json"
        status: dict[str, Any] = (json.loads(status_path.read_text(encoding="utf-8"))
                                  if status_path.is_file() else
                                  {"rounds": 0, "rounds_failed": 0, "consecutive_failures": 0})
        record: dict[str, Any] = {"started_utc": _now(), "code_commit": commit,
                                  "data_root": str(root)}
        if (state / "stop.request").exists():
            record["outcome"] = "STOPPED_BY_REQUEST"
        elif shutil.disk_usage(root).free < min_free_gb * 1024 ** 3:
            record["outcome"] = "FAILED"
            record["error"] = f"free disk below {min_free_gb} GB; nothing collected"
        else:
            client = client_factory()
            try:
                record["sources"] = _collect_sources(root, client)
            finally:
                client.close()
            failed = any(item["result"] == "FAILED" for item in record["sources"].values())
            record["outcome"] = "FAILED" if failed else "OK"
        record["finished_utc"] = _now()
        if record["outcome"] != "STOPPED_BY_REQUEST":
            status["rounds"] = int(status.get("rounds", 0)) + 1
        if record["outcome"] == "FAILED":
            status["rounds_failed"] = int(status.get("rounds_failed", 0)) + 1
            status["consecutive_failures"] = int(status.get("consecutive_failures", 0)) + 1
            status["last_failure_utc"] = record["finished_utc"]
        elif record["outcome"] == "OK":
            status["consecutive_failures"] = 0
            status["last_success_utc"] = record["finished_utc"]
        status.update({"last_round": record, "code_commit": commit, "data_root": str(root),
                       "state": record["outcome"]})
        with (state / "rounds.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        _write_atomic(status_path, status)
        return record
    finally:
        lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True,
                        help="data root holding data/public and research/results")
    parser.add_argument("--min-free-gb", type=float, default=100)
    args = parser.parse_args()
    record = run_round(args.root.resolve(), min_free_gb=args.min_free_gb,
                       commit=code_commit(Path(__file__).resolve().parents[1]))
    print(json.dumps(record, sort_keys=True))
    raise SystemExit(1 if record["outcome"] == "FAILED" else 0)


if __name__ == "__main__":
    main()
