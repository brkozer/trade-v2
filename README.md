# Trade v2

Trade v2 is an independent, private successor to AegisQuant and the Bybit prototype.
It joins cost-aware alpha research, public-data paper/shadow simulation, an append-only
evidence ledger, and a read-only operator workstation. It is **not live-trading software**:
`LIVE_DISABLED` is enforced, and paper/shadow cannot construct an authenticated exchange
transport. Testnet requires separate, explicit authorization.

The initial six-family and final 14-family historical campaigns are complete. All
20 family paths were rejected; none earned prospective promotion. The final search
recorded 28 configurations, 112 inner trials and 336 replays with nested chronological
selection. Both campaigns reuse previously researched history, **not** a fresh final
holdout. See the [final report](research/results/FINAL_ALPHA_SEARCH.md), its
[completion record](research/manifests/final_search_completion_003.json) and the
[initial report](research/results/INITIAL_ALPHA_CAMPAIGN.md). Negative evidence is
a product outcome, not permission to trade a historical winner.

## Local setup

From this directory, use Python 3.11+ and Node 20+:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
cd frontend
npm ci
npm run build
npm test
cd ..
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src/tradev2
```

All virtual environments, npm caches, journals and downloaded public datasets belong
under this target repository and are ignored by Git. Never run installers or tests in
either read-only source repository.

## Operator commands

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli inspect-candidates --search final
.\.venv\Scripts\python.exe -m tradev2.cli replay-parity
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/paper.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/shadow.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli record-public --symbols BTCUSDT ETHUSDT --seconds 30
.\.venv\Scripts\python.exe -m tradev2.cli testnet-preflight
.\.venv\Scripts\python.exe -m tradev2.cli inspect-runtime --mode paper
.\.venv\Scripts\python.exe -m tradev2.cli serve
```

In a second terminal, `cd frontend; npm run dev`, then visit the local Vite URL.
The API is a loopback, read-only service; do not expose it publicly. `paper.json`
selects simulated paper operation. Simulations can be resumed with `--resume <run-id>`.
Stop a running finite simulation with `stop-runtime --mode paper --run-id <id>`.
`record-public` captures prospective public observations without trading authority;
use `analyze-microstructure --run-id <id>` for paired smoke research. The final
historical `research --search final` command is intentionally one-shot and now refuses
a repeat because its preregistered evidence was consumed. A new search needs a new
identity, frozen manifest and explicit accounting for earlier attempts.
The CLI records events and checkpoints in ignored `runtime/`; it does not place orders.

## Evidence and design

Start with [architecture](docs/ARCHITECTURE.md), [safety](docs/SAFETY_MODEL.md),
[execution model](docs/EXECUTION_MODEL.md), [research protocol](docs/RESEARCH_PROTOCOL.md),
and [operations](docs/OPERATIONS.md). [Source manifest](docs/migration/SOURCE_MANIFEST.md)
records the exact read-only revisions; [migration map](docs/migration/SOURCE_TO_TARGET_MAP.md)
states what was adapted or rejected. [Live acceptance](docs/LIVE_ACCEPTANCE.md)
describes unmet gates, not a request to enable live trading. [Completion audit](docs/FINAL_COMPLETION_AUDIT.md)
distinguishes implemented software from scientific and external acceptance.
