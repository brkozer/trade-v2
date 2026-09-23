# Rejected legacy patterns

These are prohibited design patterns, not claims that every pattern appeared in each source.

| Pattern | Replacement |
| --- | --- |
| Giant engine/execution modules | Typed components and bounded coordinators |
| Duplicated RSI and exit literals | Immutable shared reference parameters |
| Config-path/PID-only account authority | Canonical profile-scoped host lock plus startup checks |
| Shared paper/live DB, logs or state | Per-mode, per-run isolated simulation state |
| Unknown-as-zero | Nullable provenance and completeness states |
| Fee lookup failure means cheap fee | Verified fresh/cache/conservative hierarchy or reject |
| Missing spread means zero | Unknown spread blocks required decisions |
| Stale journal means current safety | Independent liveness/source freshness and latched halt |
| immutable SQLite freshness reads | WAL-aware read-only connection and regression reproduction |
| CLI mode escalation | Explicit downgrade-only capability relation |
| Arbitrary authenticated endpoints | Built-in endpoints; no production transport |
| Silent unknown config keys | Forbid extras |
| HTTP success means fill | Explicit exchange/order states and unique execution fills |
| Cancel-all recovery | Strict owned identity and exact reconciliation |
| Post-outcome hidden rule changes | Immutable preregistration, code/data hashes and successor studies |
| Untracked search budget | Persist every configuration, fold selection and failed trial |
| Optimized/reused history labelled fresh OOS | Explicit reused historical role; untouched/fresh evidence separately required |
