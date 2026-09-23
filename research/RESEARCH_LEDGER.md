# Trade v2 research ledger

Snapshot: 2026-09-23 10:07 UTC. This ledger tracks search consumption and the next
evidence gate; sealed per-search artifacts remain authoritative for exact results.

| Identity | Mechanisms and search budget | Result | Evidence role |
| --- | --- | --- | --- |
| `TRADEV2_INITIAL_ALPHA_001` | Six families, 18 configurations, 144 replay evaluations | Six rejected, zero promoted | Reused 37-symbol history; [report](results/INITIAL_ALPHA_CAMPAIGN.md) |
| `TRADEV2_FINAL_ALPHA_002` | Interrupted after 24 evaluations in the first trend family | Consumed abort, no promotion | Same reused 39-symbol history; [record](results/FINAL_ALPHA_SEARCH_002_ABORTED.md) |
| `TRADEV2_FINAL_ALPHA_003` | 14 families, 28 configurations, 336 replays | 14 rejected, zero promoted | Reused 39-symbol history; [report](results/FINAL_ALPHA_SEARCH.md) |
| `TRADEV2_ALPHA_SEARCH_004` | Six new tested families, 12 configurations, 108 evaluations; 18 more ideas explicitly unsupported | Six tested rejected, zero promoted | Newly acquired 20-symbol history, mostly predating the 003 completion; [report](results/ALPHA_SEARCH_004.md) |

Totals through 004: **58 distinct searched configurations** and **612 recorded
replay evaluations**, including the consumed 002 abort. These are search-footprint
counts, not independent tests. There is **no promoted candidate** and no live,
testnet or authenticated paper authority granted by any search.

Previously rejected mechanisms: RSI mean reversion, time-series momentum,
compression/range breakout, relative strength, basket/BTC/BTC+ETH residual
reversion, volume shock/reversal, trend persistence/pullback, short/medium
reversal, cross-sectional momentum/reversal, volatility expansion, BTC lead-lag,
funding crowding, ridge OHLCV, and 004 breadth transition, dispersion exhaustion,
volatility-term release, funding-price disagreement, volume-breadth confirmation
and low-beta residual trend. These are not eligible for repeated tuning under a
fresh identity without a materially new causal mechanism and evidence source.

What 004 taught: a positive base-cost dispersion-exhaustion estimate can be an
isolated spike. Its severe-cost arm lost money, adjacent threshold failed in all
three forward folds, and its symbol/day concentration was excessive. It is
**rejected**, not a shadow candidate. The 004 forward set covered only six days.
Formal BTC/ETH/general-market beta attribution and defensible multiple-test
inference were unavailable at that independent-day count. These are unresolved
research-evidence requirements, never assumed to pass.

## Prospective collection in progress

The existing public-only WebSocket recorder began a bounded 30-minute BTCUSDT/
ETHUSDT session on 2026-09-23 about 10:02 UTC. Target-local run ID:
`633e65b5c30c46debb309015046138f5`. It records raw and normalized 50-level
book updates and public trades with exchange timestamps and sequences. The
journal is ignored by Git and must be audited after close before use. An early
read-only observation found 5,488 persisted microstructure messages spanning
2026-09-23 10:02:18–10:03:24 UTC; this is **not** a complete accepted dataset.
At 10:07 UTC the recorder process was still active. A read-only audit of a
20,090-message prefix verified SQLite/hash-chain integrity, schema and timestamp
preservation, and strictly increasing per-symbol book sequences. A subsequent
prefix profile (18,608 book messages plus 2,133 public-trade batches) found no
invalid book states, no duplicate trade IDs, and no exchange timestamps more
than five seconds behind ingestion or more than one second ahead. The largest
observed ingestion gaps were 601 ms for BTC books, 498 ms for ETH books, 5,106 ms
for BTC trade batches and 7,157 ms for ETH trade batches; sparse trade batches
do not by themselves prove a feed outage. These are **provisional prefix checks**,
not final closed-run acceptance or a claim of uninterrupted coverage. The exact
live process/session must be checked before treating collection as ongoing. Do
not delete, truncate, backfill or reinterpret this journal. Recorded seconds and
the 004 smokes are insufficient for a multi-day validation fold.

Because the recorder has a 30-minute bound, a target-local continuation supervisor
started at 10:11 UTC and is waiting on that recorder's actual Python PID 2144.
After it exits, the supervisor is configured for at most 24 sequential 30-minute
BTC/ETH **public-only** sessions, stopping on any failed closed-run read-back or
when available disk falls below 100 GiB. Its ignored operational status is under
`runtime/recorder/continuation-20260923T101132Z/status.json`. This is a bounded
12-hour collection plan, not a claim that those sessions have happened or that
their data passed research-quality acceptance. No authenticated transport is
instantiated by this workflow. Other symbols and the 28-day independent-forward
requirement remain uncovered.

The first independently timestamped post-004 market-context snapshot is
`BYBIT_PUBLIC_FORWARD_1790157600000_1790157600000`: one confirmed 10:00–10:15 UTC
15-minute candle for each of the 20 fixed Search 004 symbols, fetched from public
REST at 10:17:22 UTC with a two-minute close safety margin. The collector checked
symbol identity, candle validity, exact per-symbol timestamp coverage and read-back
SHA-256 (`2d8e76db71022aaa8345a7319d9aed76978f6155bc4197d8b95fe0c3950cb1f8`).
Its raw normalized bars and manifest are under ignored target-local
`data/public/prospective_bars_1790157600000_1790157600000/`. This is **one bar per
symbol**, not a validation fold, a sealed holdout, or evidence of net edge.

## New hypothesis queue — not a frozen search

These are mechanisms to preregister **only after** enough independent prospective
observation time and point-in-time data-quality coverage exist. None is being
evaluated or promoted from the current recorder sample.

1. **Liquidity-sweep absorption.** Aggressive sell (buy) trades sweep multiple
   book levels, but bid (ask) depth replenishes within an event-time window.
   Hypothesis: transitory inventory pressure mean-reverts over minutes. Requires
   synchronized public trades, sequenced book deltas, spread/depth, complete
   timestamp alignment, and latency-aware next-event execution. Fails if refill
   is not persistent or taker net expectancy vanishes after wide costs.
2. **Directional flow with failed replenishment.** Persistent aggressor flow and
   thinning opposite-side depth may predict short continuation. This is not an
   OHLCV volume-shock rerun: signed trade flow and actual book resiliency are
   required. Fails if the signal is merely contemporaneous impact or adverse
   selection consumes the edge.
3. **Passive-execution veto.** Condition an already frozen opportunity on spread,
   depth and short-horizon adverse-selection state; compare matched opportunity
   intent-to-treat outcomes against the taker baseline. Maker queue priority and
   fill probability must be bounded conservatively rather than inferred from a
   touched quote. Fails if lower modeled fees are offset by missed fills or
   adverse marks. This is execution-policy research, not a promoted strategy.

Before any new search: capture enough **post-registration, independently dated**
days for training, chronological validation, and at least 28 forward days;
verify continuous sequence/timestamp integrity and symbol coverage; preregister
fixed features, parameter/trial budget, folds, costs, execution assumptions,
neighbor tests, beta regressions, multiplicity accounting and promotion gates.
Do not label overlapping or previously inspected data as untouched. If the
recorder stops or disk/time coverage is inadequate, preserve its partial result
and continue public collection rather than manufacture a search outcome.
