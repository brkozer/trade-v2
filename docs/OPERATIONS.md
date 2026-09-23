# Operations

All commands run from Trade v2 on a development branch. Keep `.venv`, npm state,
public datasets and runtime journals inside this target. Legacy repositories are
read-only.

## Validate and inspect

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src/tradev2
.\.venv\Scripts\python.exe ops/check_artifacts.py
.\.venv\Scripts\python.exe -m tradev2.cli inspect-candidates --search final
.\.venv\Scripts\python.exe -m tradev2.cli replay-parity
```

The final one-shot historical search is consumed. Do not delete its marker or
rerun it under the same identity. New research needs a new frozen preregistration,
explicit prior-search count and independently dated results. No current candidate
is approved for prospective shadow.

## Simulate and observe

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/paper.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/shadow.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli inspect-runtime --mode paper
.\.venv\Scripts\python.exe -m tradev2.cli record-public --symbols BTCUSDT ETHUSDT --seconds 30
.\.venv\Scripts\python.exe -m tradev2.cli analyze-microstructure --run-id <32-character-run-id>
.\.venv\Scripts\python.exe -m tradev2.cli serve
```

Start UI separately with `cd frontend; npm ci; npm run dev`. API is loopback and
read-only. Paper and shadow use the engineering reference strategy, not promoted
alpha. Shadow consumes public Bybit data and simulates execution without an
authenticated transport. `run --cycles` is finite. Request a clean stop with
`stop-runtime --mode paper --run-id <id>`; the loop checks the sentinel after a
poll and checkpoints before closing. The venue/profile authority lock is local,
not distributed cross-host locking.

The public recorder preserves raw and normalized L2/trade events in the journal.
The read-back audit checks sequence and timing after reopening. A short acceptance
session proves the pipeline, not stable economics or queue fills. Long-horizon
microstructure evidence is `PROSPECTIVE_DATA_COLLECTION_ACTIVE`.

## Testnet and incidents

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli testnet-preflight
```

This makes zero network requests and reports `ENTRY_BLOCKED` until startup proofs
are true. Dedicated testnet credentials and authorization are not in this repo.
Never paste them into config or logs. The signed transport is fixed to the Bybit
testnet host and ownership-scoped; authenticated lifecycle acceptance is still
required before operational entry. No testnet or live mutation is routine
validation. `LIVE_DISABLED` remains.

On stale public data, unknown economics, reconciliation disagreement or unhealthy
protection: stop new entry, preserve the journal, record the reason, inspect owned
state only, and resume only after fresh complete proof. Do not issue account-wide
cancel-all. An acknowledgement remains unresolved until independent observation
confirms order and execution state. Preserve failed runs and their hashes.
