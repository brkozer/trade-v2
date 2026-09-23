# Trade v2

Trade v2 is an independent, private successor to AegisQuant and the Bybit prototype.
It joins cost-aware alpha research, public-data paper/shadow simulation, an append-only
evidence ledger, and a read-only operator workstation. It is **not live-trading software**:
`LIVE_DISABLED` is enforced, and paper/shadow cannot construct an authenticated exchange
transport. Testnet requires separate, explicit authorization.

The initial, preregistered historical campaign is complete. All six strategy families
were rejected after chronological validation and cost stress; no candidate was promoted.
Those folds reuse previously researched source history and are not a fresh final holdout.
See [the campaign report](research/results/INITIAL_ALPHA_CAMPAIGN.md) and
[consumption record](research/manifests/initial_campaign_completion.json).

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

## Run a public-data simulation

```powershell
.\.venv\Scripts\python.exe -m tradev2.cli run --config configs/shadow.json --cycles 1
.\.venv\Scripts\python.exe -m tradev2.cli serve
```

In a second terminal, `cd frontend; npm run dev`, then visit the local Vite URL.
The API is a loopback, read-only service; do not expose it publicly. `paper.json`
selects simulated paper operation. Simulations can be resumed with `--resume <run-id>`.
`record-public` captures prospective public observations without trading authority.
The CLI records events and checkpoints in ignored `runtime/`; it does not place orders.

## Evidence and design

Start with [architecture](docs/ARCHITECTURE.md), [safety](docs/SAFETY_MODEL.md),
[execution model](docs/EXECUTION_MODEL.md), [research protocol](docs/RESEARCH_PROTOCOL.md),
and [frontend/API contract](docs/FRONTEND.md). [Source manifest](docs/migration/SOURCE_MANIFEST.md)
records the exact read-only revisions; [migration map](docs/migration/SOURCE_TO_TARGET_MAP.md)
states what was adapted or rejected. [Live acceptance](docs/LIVE_ACCEPTANCE.md)
describes unmet gates, not a request to enable live trading. [Roadmap](docs/ROADMAP.md)
keeps the next milestones distinct from currently verified capability.
