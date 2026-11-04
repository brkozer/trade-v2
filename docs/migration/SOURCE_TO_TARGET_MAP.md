# Source-to-target decision map

`PORT` means a narrowly retained concept, not copied source code. `ADAPT` changes
semantics to the target's types and safety boundary. `REWRITE` retains only the
requirement. `REJECT` means absent from Trade v2.

| Source evidence | Decision | Target implementation / reason |
| --- | --- | --- |
| Aegis `graphify-out/graph.json`, `app/paper/api.py`, frontend dashboard and health history | ADAPT | `src/tradev2/api/server.py`, `frontend/src/App.tsx`: typed, read-only operator view with explicit freshness and unknowns; no Aegis service dependency |
| Aegis paper/shadow separation and persisted runtime history | ADAPT | `src/tradev2/runtime/coordinator.py`, `src/tradev2/evidence/`: public transport plus local simulation and restartable journal/checkpoints |
| Aegis cash/long-only paper account | REJECT | Bybit Linear quantities, collateral and PnL need a distinct Decimal account model in `src/tradev2/accounting/` and `src/tradev2/paper/` |
| Aegis historical candidate rankings and source runtime data | REJECT | `src/tradev2/research/` stages acceptance explicitly; source runtime state and sealed holdouts are not migrated |
| Bybit `v4bot/precision.py` and `v4bot/risk.py` | ADAPT | `src/tradev2/risk/`, `src/tradev2/domain/`: Decimal grid checks, risk sizing, reservations and typed rejections |
| Bybit `v4bot/accounting.py` fee/funding provenance | ADAPT | `src/tradev2/accounting/`: known/estimated/unknown money, fee and funding evidence; missing is never zero |
| Bybit `v4bot/reconciliation.py` and unresolved-late-fill regression | REWRITE | `src/tradev2/reconciliation/`, `src/tradev2/execution/`: exact owned order/fill identities, uncertainty reduction and fail-closed authority |
| Bybit historical OHLCV/funding and measured fee snapshot | PORT as evidence | `research/manifests/`, `research/results/`: hashed, previously consumed public history; explicit economics and no fresh-OOS claim |
| Bybit live transport and monolithic engine | REJECT | `src/tradev2/venues/` exposes only public GET; `src/tradev2/testnet/` is a dedicated preflight plus host-pinned, separately authorized signed testnet boundary; `LIVE_DISABLED` remains final |

No direct source-history success claim, strategy literal, credential, account record or
runtime database becomes target authority. Research and runtime share explicit signal
availability: a closed candle cannot fill at the close that revealed it.
