# Trade v2 research ledger

Snapshot: 2026-09-23 20:07 UTC. This ledger tracks search consumption and the next
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
Subsequent collection is constrained to the exact next 15-minute open; the
collector rechecks every prior chunk's universe, interval, range and bars hash
before accepting an extension. Overlapping or skipped intervals are a hard
error, not quietly counted as new independent observations.

A second target-local supervisor began waiting on the same confirmed recorder
PID at 10:22 UTC. After that process exits, it is configured for at most 24
half-hour rounds of 20-symbol public candle collection, deriving the exact next
open from the verified chain each time. It stops after three consecutive fetch
failures or below 100 GiB free disk. Operational status is under ignored
`runtime/recorder/bars-continuation-20260923T102243Z/status.json`. At launch it
was **waiting**, with zero successful rounds; no future candle coverage is
claimed from this plan alone. REST backfills retain actual ingestion times and
must not be treated as contemporaneously observed order-book or shadow fills.

## Closed raw-data integrity audit — 2026-09-23 14:12 UTC

The initial run and seven sequential continuation runs have closed. Independent
read-back of **all eight** target-local journals verified their hash chains,
schema, book sequence and counts, with exactly one `recorder_complete` event and
zero `source_failure` events per run. Together they contain **1,273,740 public
messages**, including **1,057,815 50-level book updates** and **836,807 public
trades**, from 10:02:18 to 14:03:01 UTC. The seven continuation run IDs, in
order, are `100637d3f1d44d2b90d6c1365bbde090`,
`561cee7a845c4429b20b6261c7601efa`, `fa901dbef22d4f7885031a0b838dcea7`,
`6fbd9a08285f4efdbec0709e44ff6a41`, `b2ad13257e764ba2bb98a3ab24c8b738`,
`c025ade2471e4c0e93f305535cbab4e8`, and
`d6bf2ade112e443c9276269c7ca22d02`. The closed-run CLI receipts are under
ignored `runtime/recorder/continuation-20260923T101132Z/session-*.log`.

Per-symbol within-run book ingestion gaps peaked at 1,618 ms; there were only
four book gaps over one second across the eight runs, none over five seconds.
There were no invalid book states, duplicate trade IDs within a run, or messages
over one second future-dated. One run contained **62/151,812 (0.041%)** messages
with exchange-to-ingestion lag over five seconds, all in a roughly 0.8-second
burst (maximum 5,348 ms). The seven **inter-run** message gaps were 4,862–11,487
ms. These exact intervals and the delayed-message burst must be excluded or
explicitly censored in any short-horizon feature/label construction. Hash-chain
acceptance alone does not certify gap-free market observation.

The 20-symbol public candle chain now holds nine immutable chunks: **16
consecutive confirmed 15-minute bars per symbol** (320 symbol-bars), from the
10:00 through 13:45 UTC opens. Rechecking all chunk hashes found no duplicate or
missing symbol/time keys. The per-row timestamp is **Bybit response server time**,
not a local ingestion timestamp: its lag after candle close had median 181,251 ms
and maximum 1,085,875 ms. The manifest's local `collected_at`, plus a conservative
five-second clock/receipt buffer, is the earliest permitted use time for the
whole chunk (median bound 187,682 ms, maximum 1,090,290 ms after close). Future
manifests explicitly record this `safe_available_ms`; the nine existing chunks
remain immutable and use the same rule derived from `collected_at`. The half-hour
loop backfills one interval in each round. These bars are suitable as
later-observed market context, not proof that every close was available to a
live 15-minute decision at that timestamp.
Both public-only supervisors were still collecting at 14:12 UTC (seven completed
L2 continuation sessions; eight successful candle rounds, zero failures), with
414 GiB free. This is about four hours of observations, **not 28 independent
forward days**. There is no new alpha search, candidate or promotion.

Feed-semantics check for the *unfrozen* microstructure hypotheses: Bybit's
[public-trade specification](https://bybit-exchange.github.io/docs/v5/websocket/public/trade)
defines `S` as the taker side and trade `T` as match time; its
[50-level order-book specification](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook)
defines snapshot/delta handling, `cts` matching-engine time (correlatable with
`T`), and `seq` ordering, while noting that RPI orders are absent. Across the
eight closed runs there were exactly 16 initial book snapshots and 1,057,799
deltas. All observed within-run `u` steps were `+1`, with no regression or skip;
this is a dataset observation, **not** an exchange guarantee or proof that
cross-run gaps contain no missing events. The existing recorder deliberately
does not invent a `u+1` contract. A skipped or reset `u` in future evidence
requires explicit investigation/reseed treatment before book-based research.
The [Cont–Kukanov–Stoikov order-flow study](https://arxiv.org/abs/1011.6402)
motivates testing order-flow versus depth, but its equity-market association
does not establish net-positive Bybit execution after costs. No such outcome
has been inspected in this prospective sample.

At about 14:26 UTC a separate bounded 30-minute public-only feasibility run
began for XRPUSDT, SOLUSDT, DOGEUSDT, BCHUSDT, UNIUSDT, SUIUSDT, ADAUSDT and
NEARUSDT (run ID `b9d0ccea3ad74ef5ad5e5a12425cde18`). All eight were
verified as currently available USDT linear instruments immediately before
subscription. This expands potential symbol coverage; the run is **open and
unaccepted** until its own close/read-back and per-symbol quality audit. It is
not a scored search or an independent 28-day validation set. Broad coverage is
needed before freezing concentration gates for an economically distinct
microstructure search; BTC/ETH-only outcomes cannot answer whether an apparent
edge is one-symbol dependent.

## Immutable provenance correction — 2026-09-23 14:33 UTC

The `record-public` CLI used to construct its `RunManifest` from
`configs/shadow.json`, whose default universe is BTCUSDT/ETHUSDT/SOLUSDT,
regardless of the actual `--symbols` subscription. Thus the eight closed
BTC/ETH journals audited above, the active eighth continuation run, and the
open eight-symbol breadth run have a **manifest universe/config mismatch**.
Their hash chains, raw public events, CLI receipts and timestamps remain useful
for engineering/feasibility diagnostics, but they are **not accepted as clean
prospective alpha/forward evidence**. None was scored for alpha. Their immutable
journals are not edited or relabeled. This caveat supersedes any earlier
"accepted" implication based solely on successful recorder read-back.

Commit `f16d1d5` changes only future recorder creation: the manifest's universe,
config hash/profile and recorder identity now derive from the exact subscribed
symbols, with no account-fee or equity claim. A new continuation supervisor is
waiting for the current breadth run to finish, then is bounded to 24 sequential
30-minute public eight-symbol sessions with a 250 GiB disk floor; ignored status
is `runtime/recorder/continuation-20260923T143237Z/status.json`. Its first new
run must be independently inspected for an exact manifest/event-symbol match
before any data are eligible for a future Search 005 design. The existing
20-symbol candle manifests are unaffected by this recorder defect.

The first fixed-code BTC/ETH run, `c68083a797cf44239795821a08e45f3b`,
records the correct BTCUSDT/ETHUSDT universe and `PUBLIC_RECORDER` identity at
commit `f16d1d5`, but its manifest has `dirty=true` because this ledger change
was uncommitted at launch. It too is engineering-only, not clean forward alpha
evidence. Later runs require both exact universe matching and a clean manifest.
Recorder read-back now rejects inconsistent manifest universe/config hashes,
events outside the declared universe, and missing declared-symbol observations;
it reports the manifest's dirty flag separately. This gate is prospective only:
it does not repair or retroactively validate any earlier immutable journal.
The closed-run gate also requires exactly one `recorder_complete` event,
reconciles its message/book/trade totals against independent read-back, and
reports `source_failure` event count separately. A source failure is a coverage
warning even if the recorder later reconnects and closes successfully.
The microstructure analysis command now refuses dirty-manifest or interrupted
recordings, so diagnostics cannot accidentally score the known provenance-defective
sessions. This does not establish that any later clean session has sufficient
sample size or independent forward-day coverage for alpha acceptance.

Capacity checkpoint at 14:45 UTC: the open eight-symbol journal was 835,358,720
bytes after about 19 minutes, with about 412.7 GiB free on the target drive.
The breadth supervisor's 250 GiB floor leaves only about 163 GiB of usable
headroom. A rough linear extrapolation of this *single volatile interval* is
about 60 GiB/day uncompressed, so the present disk cannot be assumed to retain
28 days of eight-symbol L2. Collection must stop safely at the floor; future
research needs verified compact archival or more capacity, not a shortened
forward gate. The small 20-symbol candle chain has a different storage profile.

## Breadth handoff incident — 2026-09-23 14:52 UTC

The first eight-symbol feasibility process exited nonzero after **594,128**
persisted microstructure messages, with **no `recorder_complete` event**. Its
terminal exception was `websockets.exceptions.ConnectionClosedError` after a
keepalive-ping timeout. The old recorder catch list did not include this
WebSocket exception, so it could not log/reseed and continue. This is an
incomplete, dirty, wrong-universe journal, **not prospective alpha evidence**;
the zero `source_failure` event count is not evidence of a clean feed because
the process crashed before logging one. The supervisor waited for the actual
predecessor PID and then started a new eight-symbol run, ID
`9cb5571d711948a69332b889502120b9`. Its immutable manifest has the exact
eight subscribed symbols, `PUBLIC_RECORDER`, `dirty=false`, and Git SHA
`3a121d5`. It is still open and unaccepted. A targeted recorder fix now catches
the documented `ConnectionClosed` class, logs the source failure and applies
the existing three-retry budget; it cannot retroactively repair either run.

A non-destructive storage probe of that closed engineering-only journal made a
consistent SQLite backup of 1,048,678,400 bytes and 594,128 events. The backup
passed SQLite integrity and event hash-chain checks; zstd-restored bytes had
the same SHA-256 as the backup (`b4f5a4f499902a70c5906e2b371c19e72149a60e4dc74276b1d3e7fc324a4e31`).
Fast level-3 compression produced 156,430,330 bytes (14.92%); level 12 produced
143,466,630 bytes (13.68%). Only generated probe copies were removed afterward;
the original immutable journal was untouched. This single-run ratio does not
solve the 28-day capacity constraint: at the indicative 60 GiB/day raw rate,
even 13.68% is roughly 8 GiB/day before BTC/ETH or other storage. Verified
archival, available space and the 250 GiB stop floor must all be accounted for
before promising a 28-day L2 dataset.

The open clean-manifest successor had a **provisional startup backlog** in a
14:52–14:58 UTC read-only prefix. Across eight symbols, 17,651 book messages
were more than five seconds behind their exchange timestamps (maximum 12,297
ms); all occurred in the first two UTC minute buckets, with zero such messages
in the next five buckets inspected. Every symbol was affected. This interval
cannot be used for short-horizon features or labels; a closed-run audit must
locate and censor its exact boundaries and check for later recurrence. The
prefix is not a score, a completed session or a general latency guarantee.
At a later 21-minute prefix, the clean eight-symbol successor held 411,916
messages. There were still zero books over five seconds late in the 19 minute
buckets after its first two startup buckets, and no within-symbol book
ingestion gap over one second across the inspected prefix. These are open-run
observations only; source failures, completion and later lag remain unverified.

At 15:03:40 UTC the BTC/ETH supervisor closed its ninth continuation session,
`c68083a797cf44239795821a08e45f3b`. Independent read-back under the
current gate verified its hash chain, exactly one completion event, matching
counts (244,231 messages; 168,387 books; 273,237 trades), both symbols, and
zero logged source failures. It remains **engineering-only** because its
immutable manifest says `dirty=true`. The next BTC/ETH run,
`e9eb10f1edce4c00aa1e356c9ac78992`, began with `dirty=false`, the exact
BTCUSDT/ETHUSDT universe, `PUBLIC_RECORDER`, and Git SHA `b066cb5`; it is
open and not yet accepted. A tiny early prefix had both book/trade streams
and no book message over five seconds late, but cannot establish whole-run
quality. The WebSocket-closure fix at `25dd584` is included in that Git SHA.
Per-symbol closed-run read-back now reports book ingestion gaps and source-time
lag without treating an intact journal as gap-free. Applying it to the dirty
`c680` run found six book gaps over one second (none over five), plus 806 books
over five seconds late across BTC/ETH (maximum 7,785 ms). Its engineering-only
classification is unchanged; those intervals would require censorship even
if provenance were clean.

## Candle forward-horizon continuation — 2026-09-23 15:09 UTC

The current 20-symbol candle supervisor was still live at 15:09 UTC, with ten
successful half-hour rounds and zero failures; its verified chain comprised
11 chunks and 20 consecutive bars per symbol from the 10:00 through 14:45 UTC
opens. That is only five hours of bars, not a forward fold. Its 24-round limit
would stop collection well before the fixed independent-day gate.

`ops/continue_public_bars.ps1` now supports a second finite campaign that
waits on the current supervisor PID, requires its terminal `COMPLETE` status,
then extends the same hash-checked contiguous chain. An initial attempted
long-horizon helper at 15:07:52 UTC failed before collecting any rounds:
Windows PowerShell rejected `Wait-Process -Timeout 43200` (maximum 32767).
The failed operational status is preserved under
`runtime/recorder/bars-continuation-20260923T150752Z/`. Commit `2fe4b0d`
uses a tested bounded process-handle wait instead. Its replacement, PID 1660,
is confirmed live and **WAITING**, with zero collected rounds, under
`runtime/recorder/bars-continuation-20260923T150902Z/status.json`. It is
configured for at most 1,344 half-hour public-only rounds (about 28 days)
after the current 24-round supervisor exits, a 100 GiB disk floor, and a stop
after three consecutive collection failures. This is a collection plan and
live waiting process, **not** 28 days of data or proof of unattended success.

## Eight-symbol feed audit and interruption — 2026-09-23 19:30 UTC

The first clean eight-symbol session, `9cb5571d711948a69332b889502120b9`,
closed with a verified journal chain, exact manifest universe, one reconciled
completion, zero source-failure events, 604,069 messages, 548,322 book messages
and 232,576 individual trades. Its 17,651 book messages with exchange lag over
five seconds (maximum 12,297 ms) are confined to the first two one-minute
buckets measured from the first ingestion timestamp. All eight symbols were
affected. No within-symbol book ingestion gap exceeded one second. The opening
two minutes are censored for short-horizon research; the remaining segment is
not thereby a forward fold or a trading result.

The second clean session, `482521f3c323464982de79f2cd80f939`, also passed
full read-back: 590,177 messages, 531,757 books, 273,620 trades, one completion,
zero source failures, and all eight symbols. Every symbol had zero book gaps
over one second, zero books over five seconds behind exchange time, and zero
books more than one second in the future. Maximum book lag was 893 ms; maximum
within-symbol ingestion gap was 891 ms. This is roughly 30 minutes of usable
market observation, not enough independent days to train or validate alpha.

The third session, `09fa8524f410459bb136b0eda250d0e8`, has a valid journal
hash chain and clean manifest but **no completion event**. It persisted 376,576
market messages and three `ConnectionClosedError` source-failure events at
16:06:17, 16:07:38 and 16:09:19 UTC, then exhausted the fixed retry budget.
The eight-symbol supervisor stopped `FAILED` after two completed sessions;
the third is interrupted evidence and cannot be scored as continuous. The
supervisor's PowerShell stderr handling retained only the first traceback
line in its status; a narrow logging correction preserved the full traceback
and nonzero exit in a synthetic native-process failure probe for future runs.
The independent BTC/ETH and 20-symbol candle collectors remained active
at 19:30 UTC (17 completed half-hour BTC/ETH sessions and 18 successful candle
rounds, respectively), with 407 GiB free. No new search ID or alpha candidate
was created from these recorder observations.

At 19:32 UTC, a **single bounded 30-minute diagnostic** eight-symbol public
recording started as PID 12268, run `fa5e1a439e7f49319e344b83f8638dee`,
with clean manifest Git SHA `b84184b` and the exact breadth universe. It was
open at first check (8,786 market messages, no completion yet); output and
stderr are retained under `runtime/recorder/breadth-diagnostic-20260923T193225Z/`.
Its purpose is to distinguish a transient close from a repeatable
eight-symbol collection limitation. It is not a search or an alpha result.
The 20-symbol candle chain independently hash-verified through the 18:45 UTC
bar, with 19:00 UTC the next expected open (19 immutable chunks).

The first eight **clean-manifest** BTC/ETH continuation sessions, 10–17 in
`continuation-20260923T101132Z`, all have one reconciled completion and zero
source failures: 1,475,035 messages, 1,151,625 books and 1,190,003 individual
trades. Sessions 10 and 11 were independently re-audited under the current
per-symbol quality reader; sessions 12–17 have the same closed-run receipts.
Together they report five within-symbol book gaps over one second (four in
session 12, one in session 17), none over five seconds, and no books with more
than five seconds of exchange lag. These intervals require event-time masks,
and the inter-session boundaries also remain gaps. Eight half-hour sessions
are not independent forward days or evidence of net alpha.

### Cross-clock timing limitation — 2026-09-23 19:41 UTC

An event-level recheck of those eight clean BTC/ETH journals found **1,144,866
of 1,151,625 books (99.41%)** with exchange `ts` later than local ingestion
wall-clock time, despite none being more than one second ahead.
Per-run negative shares were 95.72–100%; the most inverted observation was
916 ms. The live eight-symbol diagnostic prefix likewise had 94,164 of 95,735
books (98.36%) with this sign inversion. These are intact, ordered raw events,
but their uncorrected cross-clock differences are **not** valid network latency
measurements or precise availability times. Event sequence and local receipt
order remain evidence; millisecond execution claims are withheld.

Five public `/v5/market/time` calls bracketed the server response timestamp
between local request/response wall-clock reads: round trips were 192–286 ms,
and server timestamp minus local receipt was 948–950 ms. The Windows Time
service reported **not started**; this is consistent with local clock skew but
does not prove which clock is correct or establish historical offsets. Bybit's
[server-time documentation](https://bybit-exchange.github.io/docs/v5/market/time)
defines the response `time` in milliseconds and warns of possible delayed
delivery; its [order-book documentation](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook)
defines `ts` as the system generation time. No host clock setting was changed.
Future read-back now reports every negative cross-clock lag and the minimum
lag, in addition to the prior `below -1s` threshold, so this uncertainty is
visible rather than passing as zero. No past journal was rewritten or scored.
Future 20-symbol candle chunks will also preserve the local-before/server/
local-after bracket and monotonic versus wall elapsed time around their public
server-time call. This is a clock-offset observation, **not** a retroactive
timestamp correction or proof that the host remained synchronized between
half-hour probes. It leaves the fixed bar universe and availability rule intact.

The public recorder now attempts the same **GET-only, two-second-timeout**
server/local clock bracket before and after each *future* bounded session.
Successful observations are hash-chained `clock_probe` events in that run;
public time-request failures are distinct `clock_probe_failure` events and do
not masquerade as WebSocket feed failures or zero offset. Closed-run read-back
reports whether both stable start/end observations exist. This is limited
clock-offset provenance, not measured order latency, not a claim of continuous
clock stability, and not retroactive calibration of sessions 10–18 or the open
diagnostic. The first post-change session and next candle chunk must be checked
for actual persisted probes before using this as operational evidence.

A separate 20-second, BTC-only public integration smoke at 19:51 UTC verified
that recorder path without touching any earlier journal: run
`965a8ff1a0da4835ab3b8306ff68ee49` has a clean manifest at Git commit
`8a2551a`, verified journal chain, 719 messages, one reconciled completion,
zero source or clock-probe failures, and `START_END_OBSERVED` clock coverage.
The start/end public server-minus-local-receipt observations were 963/964 ms
with 287/280 ms wall-clock request durations. All 647 book events had negative
uncorrected cross-clock lag (minimum -967 ms). This confirms the instrumentation
and timing limitation; it is **not** a latency estimate, search, or forward fold.

### Bounded breadth resumption — 2026-09-23 20:07 UTC

The independent 30-minute eight-symbol diagnostic
`fa5e1a439e7f49319e344b83f8638dee` closed successfully. Current-code
read-back independently verified its journal hash chain, exact clean universe,
one reconciled completion, zero source failures, 420,996 messages, 400,006
books and 91,477 trades. Across eight symbols there were eight within-symbol
book ingestion gaps over one second (UNI 1, SUI 3, ADA 4), none over five;
no book had exchange lag over five seconds. However 398,435/400,006 books
(99.61%) had exchange time later than uncorrected local ingestion time,
minimum lag -979 ms. This run predates recorder clock-probe instrumentation,
so its clock coverage is incomplete. It supports feed feasibility only, not
millisecond execution inference, a forward fold, or an alpha result. Unlike
the previous interrupted breadth run, its WebSocket retry count was zero.

A new exact-universe public breadth run started at 20:04:55 UTC as PID 19936,
run `51d3051605994cd8916593dec02dbaab`. Its open manifest is clean at
Git SHA `ec3b13e`, and a stable start clock probe was present at first check;
it is not yet accepted. Supervisor PID 14092 is confirmed live and waiting
for that PID, status under
`runtime/recorder/continuation-20260923T200525Z/status.json`. It is limited
to 24 more 30-minute sessions, stops on a failed recorder, and retains the
250 GiB free-disk floor. This is bounded collection, not a promised 28-day
L2 dataset. At 20:06 UTC, C: had 406.35 GiB free.

The 20-symbol candle chain hash-verified through the 19:45 UTC open (21
chunks). The newest manifest contains an actual stable public clock bracket:
server timestamp minus local receipt 977 ms, request duration 285 ms, with
wall and monotonic elapsed times within 4 ms. The current BTC/ETH session 20,
run `c04ad2216b824b27b46fb08095e0d30c`, also had a clean Git manifest
and a stable start probe at first check. Both open runs require their own
closed-run read-back and end probes before acceptance. The BTC/ETH supervisor
had completed 19 sessions and the candle supervisor 20 successful rounds,
zero failures; the 1,344-round candle extension remained waiting on the first
campaign. No candidate is under evaluation or promoted.

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
