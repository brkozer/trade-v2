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

## Start and stop the workstation

After the README setup, from the Trade v2 directory:

```powershell
.\scripts\start_trade_v2.ps1
.\scripts\status_trade_v2.ps1
.\scripts\stop_trade_v2.ps1
```

`start_trade_v2.ps1 -OpenBrowser` also opens the browser. The UI is at
`http://127.0.0.1:5173/`; API documentation is at `http://127.0.0.1:8000/docs`.
Both services bind to loopback. The launcher stores owned PID/start-time pairs and
logs under ignored `runtime/operator/`. A repeat start or stop is safe. A partial
or unhealthy launch fails clearly rather than killing other Python/Node processes.
The six pages remain useful when no simulation runs: the final campaign is sealed
historical evidence, whereas account and runtime readings are current/last-run
evidence and may correctly be unknown.

## Simulate and observe

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/paper.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/shadow.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/factor_fixture.paper.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/factor_fixture.shadow.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli inspect-runtime --mode paper
.\.venv\Scripts\python.exe -m tradev2.cli record-public --symbols BTCUSDT ETHUSDT --seconds 30
.\.venv\Scripts\python.exe -m tradev2.cli analyze-microstructure --run-id <32-character-run-id>
```

The reference RSI and non-RSI factor are both `TEST_FIXTURE` paths, not promoted
alpha. The factor config requires explicit `fixture_mode`; without it the loader
demands a sealed research promotion and the requested stage. `PROSPECTIVE_SHADOW`
does not authorize paper, and `PAPER_EXECUTION_VALIDATED` additionally needs a
sealed paper acceptance record. Unknown/rejected candidates fail closed. Shadow
consumes public Bybit data and simulates execution without an
authenticated transport. `run --cycles` is finite. Request a clean stop with
`stop-runtime --mode paper --run-id <id>`; the loop checks the sentinel after a
poll and checkpoints before closing. The venue/profile authority lock is local,
not distributed cross-host locking.

The public recorder preserves raw and normalized L2/trade events in the journal.
The read-back audit checks sequence and timing after reopening. A short acceptance
session proves the pipeline, not stable economics or queue fills. Long-horizon
microstructure evidence is `PROSPECTIVE_DATA_COLLECTION_ACTIVE`.

## Historical and new research

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli inspect-candidates --search initial
.\.venv\Scripts\python.exe -m tradev2.cli inspect-candidates --search final
.\.venv\Scripts\python.exe -m tradev2.cli inspect-candidates --search 004
.\.venv\Scripts\python.exe -m tradev2.cli replay-parity
```

`research --search final` and `research --search 004` are one-shot commands, but
both identities and completion records are consumed in this checkout. Search 004
was prepared with `collect-search004`, `preregister-search004`, then
`research --search 004` on its dedicated research branch; those create-only
commands now refuse overwrites. A genuinely new search requires a
new preregistered search ID and manifest, fresh independently dated holdout,
explicit search-count accounting and a separate runner/result identity. Do not
rename, delete or overwrite consumed artifacts. Until those inputs
exist, inspection is the valid reproducible operation; no new campaign is
implicitly authorized by a UI click.

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
