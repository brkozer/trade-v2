# Safety model

Live is hard disabled. There is no production authenticated transport. Paper/shadow
objects have public market-data capability and simulation capability only; no paper,
shadow, runtime or API module imports the testnet package (regression-tested).

A signed testnet transport (`tradev2.testnet.transport.TestnetLinear`) does exist. It is
pinned to `api-testnet.bybit.com`, allowlists four write and seven read endpoints, and
can be constructed only from a testnet-mode config with `testnet_authorized=true`,
`TRADEV2_TESTNET_ENABLE=1` and testnet-only credential environment variables. Entry
additionally requires every startup proof. No CLI command constructs it: the
`run` command refuses testnet mode, and `testnet-preflight` makes zero network
requests. Testnet operation still needs separate, explicit, dedicated authorization;
nothing in research, paper, shadow or the UI infers it.

- Strict configuration rejects unknown keys, including misspelled risk keys and arbitrary
  authenticated host URLs. CLI overrides can only reduce capabilities.
- The full startup gate requires authority, venue/account identity, position mode,
  instruments, fees, owned orders, positions, journal, reconciliation, protection,
  market freshness and safety. Missing/unknown checks block entry.
- Quantity is floored to exchange step within the risk budget. Exchange minimums cannot
  inflate position size. Leverage is not stop risk.
- Owned client IDs use deterministic namespace semantics. Foreign orders are never
  candidates for automatic cancellation. Acknowledgment is not fill.
- An unresolved/partial exit keeps its residual position managed. Unproven protection
  blocks additional exposure and requires explicit recovery.
- Missing fees, spread and funding remain unknown. Estimates are clearly separated from
  canonical settled amounts. Funding payment times determine attribution.
- Engine liveness, heartbeat freshness and source freshness are separate observations.
  A frozen journal, dead engine or unreadable source cannot establish CURRENT_SAFE.
  A pending halt is latched; failed reads cannot clear it.
- Runtime databases and state are separated by mode and immutable run ID. Account
  authority is shared across configurations for the same resolved profile in this installation.

Freshness, WAL stale-reader behavior, mode escalation, startup requirements, account locks,
minimum sizing and lifecycle invariants are regression-tested. These are engineering
invariants, not proof of alpha or live readiness.
