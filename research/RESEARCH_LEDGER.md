# Trade v2 research ledger

Snapshot: 2026-10-24 UTC (read-only prospective chain audit, below). The newest
research section is 2026-09-24 09:47 UTC. This ledger tracks search consumption and
the next evidence gate; sealed per-search artifacts remain authoritative for exact
results. Bounded research-cycle reports are in [cycles/](cycles/).

| Identity | Mechanisms and search budget | Result | Evidence role |
| --- | --- | --- | --- |
| `TRADEV2_INITIAL_ALPHA_001` | Six families, 18 configurations, 144 replay evaluations | Six rejected, zero promoted | Reused 37-symbol history; [report](results/INITIAL_ALPHA_CAMPAIGN.md) |
| `TRADEV2_FINAL_ALPHA_002` | Interrupted after 24 evaluations in the first trend family | Consumed abort, no promotion | Same reused 39-symbol history; [record](results/FINAL_ALPHA_SEARCH_002_ABORTED.md) |
| `TRADEV2_FINAL_ALPHA_003` | 14 families, 28 configurations, 336 replays | 14 rejected, zero promoted | Reused 39-symbol history; [report](results/FINAL_ALPHA_SEARCH.md) |
| `TRADEV2_ALPHA_SEARCH_004` | Six new tested families, 12 configurations, 108 evaluations; 18 more ideas explicitly unsupported | Six tested rejected, zero promoted | Newly acquired 20-symbol history, mostly predating the 003 completion; [report](results/ALPHA_SEARCH_004.md) |
| `TRADEV2_DISCOVERY_005` | One funding-carry family, two configurations, 18 evaluations | Rejected discovery-only; zero candidates | Reused consumed 004 panel; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_005.md) |
| `TRADEV2_DISCOVERY_006` | One UTC-hour seasonality family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_006.md) |
| `TRADEV2_DISCOVERY_007` | One low-idiosyncratic-volatility family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_007.md) |
| `TRADEV2_DISCOVERY_008` | One low-volume dislocation-reversal family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_008.md) |
| `TRADEV2_DISCOVERY_009` | One idiosyncratic-MAX family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_009.md) |
| `TRADEV2_DISCOVERY_010` | One downside-beta-defensiveness family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_010.md) |
| `TRADEV2_DISCOVERY_011` | One volume-weighted close-pressure family, two configurations, 24 evaluations | Rejected discovery-only; zero candidates | Reused consumed 39-symbol history; `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; [report](results/DISCOVERY_SEARCH_011.md) |

Totals through 011: **72 distinct searched configurations** and **774 recorded
replay evaluations**, including the consumed 002 abort. These are search-footprint
counts, not independent tests. There is **no promoted candidate** and no live,
testnet or authenticated paper authority granted by any search.

Previously rejected mechanisms: RSI mean reversion, time-series momentum,
compression/range breakout, relative strength, basket/BTC/BTC+ETH residual
reversion, volume shock/reversal, trend persistence/pullback, short/medium
reversal, cross-sectional momentum/reversal, volatility expansion, BTC lead-lag,
funding crowding, ridge OHLCV, and 004 breadth transition, dispersion exhaustion,
volatility-term release, funding-price disagreement, volume-breadth confirmation
and low-beta residual trend, plus 005 persistent funding-settlement carry and
006 UTC-hour cross-sectional seasonality and 007 cross-sectional low
idiosyncratic volatility, 008 low-volume range-dislocation reversal and 009
cross-sectional idiosyncratic MAX, plus 010 cross-sectional downside-beta
defensiveness and 011 cross-sectional volume-weighted close pressure. These are
not eligible for minor
parameter, buffer or calendar-bin retuning, nor repetition under a fresh
identity without a materially new causal mechanism and evidence source.

What 004 taught: a positive base-cost dispersion-exhaustion estimate can be an
isolated spike. Its severe-cost arm lost money, adjacent threshold failed in all
three forward folds, and its symbol/day concentration was excessive. It is
**rejected**, not a shadow candidate. The 004 forward set covered only six days.
Formal BTC/ETH/general-market beta attribution and defensible multiple-test
inference were unavailable at that independent-day count. These are unresolved
research-evidence requirements, never assumed to pass.

## Prospective collection log (historical; liveness is observed, never assumed)

The entries below record collection as it was observed at each dated check. Current
chain coverage and collector recency come only from `tradev2.cli inspect-prospective`
or `/api/v1/prospective-evidence`, which re-verify every chunk on each call.

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

### New public OI evidence source — feasibility, not Search 005

The previous searches rejected funding-crowding and funding-price-disagreement
rules; they did **not** test changes in position inventory. A possible new
mechanism is an open-interest unwind or build-up *condition* on subsequent
price behavior, not a retune of the failed OHLCV/funding thresholds. This is
only a hypothesis source, with no fixed search ID, parameters, trial budget or
outcome estimate yet. It cannot be called alpha without new chronological and
prospective evidence.

Bybit's [public open-interest endpoint](https://bybit-exchange.github.io/docs/v5/market/open-interest)
supports 15-minute history; its documented total is the sum of both sides in
the contract base unit, and the endpoint warns of delayed delivery. Read-only
probes found both historical (at the 004 consumed-panel cutoff) and current
15-minute rows for **all 20 fixed 004 symbols**, each with timestamp, total
and single-side quantity. Historical OI fetched now would be discovery-only,
never an untouched validation set. The newly added independent forward OI
collector requires exact symbol/time coverage, positive finite quantities,
a stable public clock probe, an extra full interval plus two-minute safety
lag, and a local/exchange receipt availability bound; it writes hashed,
create-only chunks without changing the candle chain. Its real first-run
behavior and long-horizon continuity still require verification. No OI signal
has been evaluated, so completed-search and trial counts remain unchanged.

The first actual prospective OI chunk is
`BYBIT_PUBLIC_OI_FORWARD_1790192700000_1790193600000`, sampled at 20:19 UTC:
the 19:45 and 20:00 UTC exchange timestamps for all 20 fixed symbols (40
symbol-points). Independent read-back found exact timestamp/symbol coverage,
positive finite total and single-side quantities, source receipt times before
`safe_available_ms=1790194765934`, and matching OI SHA-256
`131d8f4f5ddae6d8422dc10721636ba2dd5ecb012c69cfec19ba7734ecb16b0b`.
The next required timestamp is 20:15 UTC; it was **not** silently backfilled.
The collection-time server-minus-local receipt observation was 996 ms with
281 ms wall request duration. This chunk is raw forward context, not a fold
or a trading result. A finite OI continuation helper, PID 23844, was
confirmed live at 20:21 UTC under
`runtime/recorder/oi-continuation-20260923T202123Z/status.json` with status
`WAITING_FOR_INTERVAL`, zero rounds, a 100 GiB disk floor, 1,344 half-hour
rounds maximum, and a stop after three consecutive failures. Its next chunk
is not yet present. This plan does not establish 28 days of data or alpha.

A read-only one-day public OI profile ending at the first chunk's 20:00 UTC
timestamp returned 100 rows for each of the 20 symbols. The 97 expected
quarter-hour keys per symbol were all present (zero gaps across 1,940 keys),
with no duplicate timestamp or invalid quantity among the 2,000 returned
rows. The stored 19:45/20:00 values matched a later endpoint read for all 20
symbols. This is a short stability check, not proof that older OI never
revises. The collector now re-requests each symbol's last immutable point as
an overlap anchor before writing the next chunk; a revision raises an error
and preserves the previous chunk rather than silently overwriting history.
The first chunk predates this overlap check; its saved collector hash and raw
values remain unchanged. The first supervised extension will be the first
operational test of the new anchor gate.

### Cross-source point-in-time gate (23 September, 20:31 UTC)

The 19:45 UTC OI and candle rows share the same exchange timestamp, fixed
20-symbol universe and source-universe hash, but their receipt bounds differ:
the candle was safe at 20:04:16.225 UTC and OI only at 20:19:25.934 UTC.
The earliest **eligible** 15-minute execution-bar open is therefore 20:30 UTC,
strictly after both source receipts and the candle close. That is not a fill
claim: the future execution bar and realistic spread, fees, slippage and
latency still have to be observed and modeled. The OI row timestamped 20:00
UTC has no matching collected candle yet and is excluded, rather than joined
to an unavailable price bar. A small typed availability rule now rejects
mismatched timestamps and premature source availability, including an exact
bar-boundary case. Six adversarial/unit checks passed. The check was prompted
by underlying data-quality risk (late-arriving OI and a potentially leaking
cross-source join), not evidence of predictive value. Search/trial counts,
candidate status and the need for 28 independent forward days are unchanged.

At 20:34 UTC the next prospective candle chunk arrived for 20:00/20:15 UTC.
Its saved hash, contiguous timestamps and all 20 symbols passed independent
read-back. The 20:00 OI row is now joinable only as of the candle's later
20:34:21.770 UTC safe receipt, making 20:45 UTC its first eligible execution
bar open. Neither eligible bar is a fill or scored outcome.

The 20:05–20:35 UTC BTC/ETH session `c04ad2216b824b27b46fb08095e0d30c`
closed with a clean manifest, verified journal, one reconciled completion,
zero source or clock-probe failures, stable start/end clock probes, 120,246
messages, 108,322 books and 41,750 trades. Its within-symbol book ingestion
had zero gaps over one second. The concurrent eight-symbol breadth session
`51d3051605994cd8916593dec02dbaab` likewise closed with clean provenance,
verified journal, one completion, zero source/clock-probe failures, 394,275
messages, 373,599 books and 91,769 trades. It had 24 within-symbol book
gaps over one second, none over five seconds. All books in both sessions had
exchange timestamps ahead of host ingestion timestamps; public clock probes
put server time about 0.98–1.01 seconds ahead of local receipt. Thus raw
cross-clock negative lag is a clock-quality observation, not negative market
latency. The records remain unscored and do not constitute continuous L2
coverage or an alpha result. The first supervised OI extension is still
pending its next safe interval and requires separate real-world audit.

An additional OI field-grain check on the first 40 symbol-points found
`singleOpenInterest` exactly half the both-sides quantity in 21 rows and within
6.11×10⁻⁷ relative error in the other 19 (consistent with display rounding).
It is not an independent long/short or directional-positioning measurement;
future OI hypotheses must use the total only, without double-counting the
single-side field as another feature. Across the 20 symbols, the one observed
15-minute total-OI change ranged from −0.931% to +0.677%; zero changes reached
1% absolute magnitude. This one interval is a data-shape observation, not an
event-frequency estimate or evidence of an effect on future returns.

For mechanism *feasibility only*, a read-only public OI query covered the
seven historical days 16–22 September (before the 004 completion) for the
fixed 20 symbols. Eighty bounded pages yielded all 13,440 expected 15-minute
symbol/timestamp keys with no duplicate, missing, nonpositive or nonfinite
total-OI value. Across 13,360 **overlapping** trailing-hour changes, median
absolute OI change was 0.449%, the 90th percentile 1.876% and the 99th
percentile 6.409%; 3,114/13,360 (23.3%) exceeded 1% absolute. Day counts
varied from 290 to 617 such overlapping windows (20 symbols). This shows that
an hourly inventory-change condition is not trivially empty in that week, but
overlap, current-universe selection, historical retrieval/revision risk and
the lack of any price-outcome or cost test make these **consumed discovery
statistics**, not an independent event count, alpha estimate or validation.
No search threshold or direction has been frozen from them, and Search 005 has
not begun. The [Bybit OI contract](https://bybit-exchange.github.io/docs/v5/market/open-interest)
allows 200 rows per page, labels total versus single-side units and warns of
delivery delay; collection-time availability must still control every join.

As a *hurdle illustration*, the 004 collection-time symbol economics imply
13.01–17.68 bps (median 13.98) of base taker/taker round-trip fee, observed
spread and 1 bp/side slippage across the fixed 20 symbols. Under the already
declared severe multipliers (2× fee, 3× spread, 5 bp/side slippage), the same
arithmetic is 32.03–46.03 bps (median 34.95), **before** funding, latency,
missed/partial fills or risk limits. These Decimal calculations are not
historical spread paths or a frozen Search 005 cost model; they show why a
delayed OI condition must clear a material net hurdle. No historical OI/price
outcome was queried or optimized in this feasibility check.

### WAITING_FOR_DATA — bounded cycle 2026-09-23 21:00 UTC

No new alpha experiment is eligible. The accepted prospective OI chain has
only four contiguous 15-minute timestamps, 19:45–20:30 UTC on one calendar
day (80 symbol-points for the fixed 20-symbol universe). This is below the
unchanged prerequisite of enough independently dated post-registration data
for training, chronological validation and **at least 28 forward days**.

The exact release condition is: closed, independently accepted, gap-free OI
and candle evidence across the fixed universe must cover that prerequisite,
and every scored outcome must have a completed execution bar strictly after
the later source-availability bound. At this snapshot only the 20:15 UTC row
from the second OI chunk has a completed matching candle; its first eligible
execution-bar open is 21:00 UTC, which is not yet accepted evidence. The
20:30 UTC OI row has no completed matching candle. Therefore no return, fill,
cost, hypothesis, candidate or alpha statistic is scored, and search/trial
counts remain unchanged.

One supervisor/process snapshot found the existing candle-chain, breadth and
OI supervisors alive and responsive as independent PowerShell processes. The
OI supervisor remained `WAITING_FOR_INTERVAL` after one successful extension,
zero failures, a 1,344-round bound and 100 GiB free-disk floor. No collector
was restarted, no open journal was read, and no process was polled or awaited.
Resume only from newly closed and accepted artifacts on a later invocation.

### Closed-chain extension and repaired continuation — 2026-09-23 22:52 UTC

Independent read-back accepted three additional candle chunks and three
additional OI chunks. The candle chain now contains 25 contiguous chunks and
960 fixed-universe symbol-bars from 10:00 through 21:45 UTC. The OI chain has
five contiguous chunks and 200 symbol-points from 19:45 through 22:00 UTC.
All new paths, identities, source-universe hashes, payload hashes, timestamps,
quantities/OHLCV geometry, clock probes and availability bounds passed. Nine
OI timestamps have matching accepted candles; six also have a completed candle
at the first bar open strictly after both source-availability bounds. These are
data-integrity and availability results, not outcome or alpha estimates.

The initial candle campaign completed all 24 rounds with zero failures, but
its preconfigured long continuation then failed on its first ordinary nonzero
collector exit: Windows PowerShell promoted native stderr under the script's
strict error policy before bounded retry accounting ran. The repair confines a
`Continue` policy to the native invocation, captures the exit code, restores
strict handling, and adds an explicit mutually exclusive
`ResumeExistingChain` mode. Chain, disk, round and three-consecutive-failure
gates are unchanged. PowerShell parsing and native-failure behavior passed,
alongside 124 Python tests, Ruff, six frontend tests and the production build.

After commit `60c90ad`, the repaired helper was started exactly once as
independent PID `37304`; an immediate process-table read confirmed the intended
command with 1,344 maximum rounds, 1,800-second intervals and a 100 GiB disk
floor. Launch stdout/stderr are
`runtime/recorder/bars-resume-20260923T225157Z.{stdout,stderr}.log`. No later
process or status check was made. It must stop on three consecutive failures,
disk-floor breach, explicit stop request or completion of the finite rounds.

**WAITING_FOR_DATA remains exact:** all accepted OI evidence is still from one
calendar day. Do not begin a search until closed, independently accepted,
gap-free OI and candle evidence satisfies the registered training and
chronological-validation design plus at least 28 forward days, with every
outcome using a completed execution bar strictly after the later source
availability bound. Search/trial counts remain unchanged; LIVE is disabled.

### First repaired continuation round accepted — 2026-09-23 22:54 UTC

The repaired candle supervisor's first closed round succeeded with zero
failures. Its new chunk extends the immutable chain through 22:30 UTC; the
concurrent closed OI extension reaches the same timestamp. Full-chain read-back
now verifies 26 candle chunks/1,020 symbol-bars and six OI chunks/240
symbol-points, with exact continuity, universe and source identity, matching
hashes, valid Decimal quantities and OHLCV geometry, stable clock probes and
conservative availability bounds. Twelve OI timestamps match accepted candles;
nine also have a completed first-eligible execution bar. This validates the
repair and data path, not any predictive or economic result.

**WAITING_FOR_DATA remains unchanged:** the OI chain still covers only one
calendar day. The latest 22:00, 22:15 and 22:30 UTC feature timestamps require
the unaccepted 23:00 UTC execution bar and remain unscored. Do not start a new
search until the registered training and chronological-validation design plus
at least 28 forward days are present as closed, independently accepted,
gap-free evidence with strictly later completed execution bars. Search/trial
counts remain unchanged; LIVE is disabled.

### Discovery-only Search 005 and next closed chunks — 2026-09-24 09:09 UTC

Per the separate discovery track, Search 005 froze one economically distinct
family before replay: after two consecutive same-sign settled funding rates,
take the receiving side after the settlement-opening bar closes and hold 32
bars. Two absolute-rate thresholds (0.5/1.0 bp) and 18 chronological evaluations
were sealed under `TRADEV2_DISCOVERY_005`; the consumed Search 004 panel was
explicitly labeled `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**: 72 forward trades, mean gross/net R
−0.234/−0.291, zero of three positive folds and zero neighbor-positive folds.
Aggregate net PnL was −520.17/−593.35/−325.66 USDT under base/wide/severe costs.
Base folds received 6.08 USDT funding but lost 418.73 USDT from price movement
before 107.52 USDT of fees, spread and slippage. Maximum symbol/day absolute
shares were 37.4%/84.6%. The smaller severe loss is an exposure/missed-fill
effect, not robustness. No candidate was frozen or promoted.

Post-completion read-back found three symbols with four-hour funding histories
and one mixed four/eight-hour history, while the preregistered description said
expected eight-hour settlement. A 32-bar hold can cross two settlements there.
This consumed limitation prevents a general claim about an exactly-one-settlement
rule; no symbols, thresholds or horizons were changed after outcomes and the
negative search was not rerun.

The one-time prospective check also found one new closed candle chunk and one
new closed OI chunk. Full-chain integrity accepted 27 candle chunks/1,060
symbol-bars through 23:30 UTC and seven OI chunks/280 symbol-points through the
same timestamp. Their latest payload hashes are respectively
`5e0a99a56e6c104df3eec5ae45852dc9754f092e9142684d1a2eff02cc845493`
and `5df2e4bb83909b20353ff066e276eeb838aaa5219f2c10ea4a406312dcc59eb7`.
This remains one prospective calendar day and cannot satisfy fresh acceptance.

### Discovery-only Search 006 — 2026-09-24 09:19 UTC

Search 006 tested a distinct calendar/liquidity mechanism on the reused 210-day,
39-symbol panel. Training-only mean next-hour return by symbol and UTC entry hour
was cross-sectionally demeaned, then admitted only when its predicted gross edge
cleared each symbol's base taker/spread/slippage hurdle plus a frozen zero or
10 bp buffer. Four nested expanding folds used 30-day inner selections and four
disjoint 30-day forward periods. All 24 planned evaluations were retained and
labeled `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**: 2,726 trades across 21 symbols, mean
gross/net R −0.0015/−0.0753, one of four positive folds, zero neighbor-positive
folds and a 2/2 split in selected buffers. Base/wide/severe aggregate PnL was
−4,482.21/−7,222.81/−4,093.00 USDT. Gross PnL was already −35.52 USDT; fees,
spread and slippage consumed 4,452.96 USDT while funding receipts offset only
6.26 USDT. Maximum fold drawdown was 28.90%. The seven-day block bootstrap
daily-PnL interval was wholly negative [−58.38, −16.62] USDT with p=1.0.

The high-buffer arm's single positive 90-trade fold did not repeat in the next
fold, while every neighboring-buffer fold lost money. This discriminates
against a stable UTC liquidity-handoff premium: neither gross structure,
parameter stability nor net costs passed. No candidate was frozen or promoted;
no calendar-bin or buffer retuning is authorized under this identity.

### Supervisor recovery and Discovery-only Search 007 — 2026-09-24 09:32 UTC

The one-time supervisor audit found the earlier candle PID `37304` and OI PID
`23844` missing while their status files remained nonterminal and unchanged
since 23:22 UTC. Their last recorded rounds had zero failures, and empty launch
logs exposed no collector implementation defect; external termination is the
most defensible classification. The already accepted gate evidence therefore
remained 27 candle chunks/1,060 symbol-bars and seven OI chunks/280 points
through 23:30 UTC, still one calendar day and far below 28 forward days.

An initial relaunch attempt at 09:26:11 UTC exited immediately because the
launcher failed to quote the repository path containing a space; its stderr
records that launch-only error and it collected nothing. The corrected durable
launch at 09:26:32 UTC was verified once from the process table as candle PID
`33456` and OI PID `13340`, each using the target-local public-only script,
1,344 maximum half-hour rounds and a 100 GiB disk floor. Logs are under
`runtime/recorder/{bars,oi}-resume-20260924T092632Z.*.log`. Both supervisors
terminate on their finite round count, disk floor, explicit stop, or bounded
failure policy. They were not polled again during this cycle.

Search 007 then tested a distinct speculative-demand/leverage-constraint
mechanism on the reused 210-day panel. Each Monday it held equal-count long
positions in the two lowest and shorts in the two highest BTC/ETH-residual-
volatility altcoins for seven days. Frozen 14/28-day lookbacks were evaluated in
four disjoint 30-day forward folds under base, wide and severe costs. All 24
evaluations were retained as `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`; there was no
outcome-selected winner.

The result is **REJECTED_DISCOVERY_ONLY**. The 14-day variant lost 103.78 USDT
at base cost with negative gross expectancy. The 28-day variant made only 26.31
USDT base and 4.69 USDT wide across 68 trades, with two of four positive folds;
its higher 80.16 USDT severe result is an exposure/missed-fill artifact, not
monotone robustness. Its seven-day block interval crossed zero [−4.59, 4.62]
USDT/day, Holm p was 0.901, and BTC daily correlation 0.308 exceeded the frozen
0.30 cap. The neighboring 14-day configuration failed.

The fixed weekly four-leg design can produce only 68 trades per configuration
over the 120-day forward span, so the preregistered 200-trade gate was
structurally unreachable. That consumed design limitation does not authorize a
weaker gate, cadence change or rerun. No candidate was frozen or promoted.

### Discovery-only Search 008 — 2026-09-24 09:40 UTC

The one-time prospective chain audit accepted one additional closed candle
chunk. Full read-back verified 28 contiguous chunks/1,860 symbol-bars through
09:00 UTC; the latest dataset is
`BYBIT_PUBLIC_FORWARD_1790205300000_1790240400000` with bars hash
`c7a232310fbcbf6c971ecfc28fd90f69c3fb969669fe72e7596685de6bae8a8c`.
OI remained seven chunks/280 symbol-points through 23:30 UTC with latest hash
`5df2e4bb83909b20353ff066e276eeb838aaa5219f2c10ea4a406312dcc59eb7`.
The synchronized prospective evidence still spans one calendar day and cannot
advance the 28-day acceptance gate. Supervisors were not inspected again.

Search 008 tested whether the earlier failures of high-volume reversal and
generic volatility expansion concealed a distinct thin-liquidity mechanism.
It reversed only wide, extreme-closing candles with unusually low volume and a
body above a symbol-specific 1.5× or 2.5× base-cost hurdle. Both frozen variants
used next-open execution, a four-bar hold, four disjoint 30-day folds and all
three cost schedules. All 24 evaluations were retained and labeled
`DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**. The 1.5×/2.5× variants produced
174/166 trades, negative gross R of −0.0315/−0.0349, zero positive folds and
base PnL of −441.64/−436.74 USDT. Wide losses were −667.27/−652.55 USDT and
severe losses −180.11/−225.24 USDT. Both weekly-block intervals were wholly
negative with Holm p=1.0. Near-zero BTC beta/correlation and acceptable
concentration show this was not a market-exposure or single-contributor failure.
The stricter hurdle barely changed opportunity count and did not improve gross
economics, directly rejecting the proposed liquidity-vacuum reversal. No
candidate was frozen or promoted, and no threshold retuning is authorized.

### Discovery-only Search 009 — 2026-09-24 09:47 UTC

The one-time prospective chain read-back was unchanged and integrity-valid: 28
candle chunks/1,860 symbol-bars through 09:00 UTC and seven OI chunks/280
symbol-points through 23:30 UTC. Their latest hashes remained respectively
`c7a232310fbcbf6c971ecfc28fd90f69c3fb969669fe72e7596685de6bae8a8c` and
`5df2e4bb83909b20353ff066e276eeb838aaa5219f2c10ea4a406312dcc59eb7`.
The synchronized OI/candle chain still spans one prospective calendar day, so
the 28-day acceptance gate remains `WAITING_FOR_DATA`. No supervisor or open
journal was inspected.

Search 009 separated a positive-tail lottery-demand hypothesis from Search
007's generic residual-volatility hypothesis. Each UTC day it ranked a causal
BTC/ETH-residual maximum 15-minute return, bought the two lowest-MAX and sold
the two highest-MAX non-factor symbols, then held one day. Frozen 14/28-day
lookbacks ran in four disjoint 30-day folds under all three cost schedules. All
24 evaluations were retained as `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**. Both variants made 464 trades and
only one of four folds was positive. The 14-day arm was almost gross-flat at
+7.25 USDT but lost −225.12/−381.58/−120.50 USDT under base/wide/severe costs.
The 28-day arm was gross-negative and lost −281.38/−437.61/−136.49 USDT. Both
weekly-block intervals crossed zero with Holm p=1.0. Low BTC attribution and
acceptable aggregate concentration rule out market beta or one contributor as
the primary explanation. The positive-tail feature did not supply enough gross
edge to fund daily turnover, and the longer lookback reversed sign. No candidate
was frozen or promoted; lookback, cadence and holding-period retuning are not
authorized under this identity.

### Discovery-only Search 010 — 2026-09-24 10:37 UTC

The invocation's single prospective read-back found the same closed,
integrity-valid evidence: 28 candle chunks/1,860 symbol-bars through 09:00 UTC
and seven OI chunks/280 symbol-points through 23:30 UTC, with latest hashes
`c7a232310fbcbf6c971ecfc28fd90f69c3fb969669fe72e7596685de6bae8a8c` and
`5df2e4bb83909b20353ff066e276eeb838aaa5219f2c10ea4a406312dcc59eb7`.
The synchronized chain still spans one calendar day. The exact prospective
condition therefore remains **WAITING_FOR_DATA** until 28 forward calendar days
of registered, closed, contiguous and integrity-accepted candle/OI evidence are
available. No open journal was scored and no supervisor was polled afterward.

Search 010 tested a forced-deleveraging explanation distinct from residual
trend, total residual variance and positive-tail MAX. Each UTC day it ranked
non-BTC/ETH symbols by rolling beta estimated only during negative BTC
15-minute returns, bought the two lowest-beta and sold the two highest-beta
symbols, then held one day. Frozen 14/28-day lookbacks ran in four disjoint
30-day folds under base, wide and severe costs. All 24 evaluations were retained
as `DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**. Both variants made 464 trades and
were gross-negative before costs: -187.69/-184.63 USDT. Base losses were
-404.56/-400.10 USDT, each with only two of four positive folds; wide losses
were -561.93/-557.13 USDT. Both seven-day block intervals crossed zero and
Holm-adjusted p-values were 1.0. Absolute BTC daily correlations of 0.385/0.360
failed the frozen 0.30 limit, while symbol concentration of 0.372/0.479 failed
the 0.35 limit. The longer variant's loss was especially concentrated in one
symbol. Lower severe losses reflect reduced size and missed fills rather than
robustness. No parameter retuning, candidate freeze or promotion is authorized.

### Discovery-only Search 011 — 2026-09-24 10:47 UTC

The invocation's single closed-chain read-back accepted two additional candle
chunks and two additional OI chunks. Full content, continuity, schema,
availability and SHA-256 checks verified 30 candle chunks/1,940 symbol-bars and
nine OI chunks/1,160 symbol-points, both through timestamp `1790244000000`.
The latest datasets are `BYBIT_PUBLIC_FORWARD_1790243100000_1790244000000`
with hash `75dcf54c4f256cca97d7a3875dae96f0ae4d81401a7e23ec9016386a1a49074e`
and `BYBIT_PUBLIC_OI_FORWARD_1790243100000_1790244000000` with hash
`069590653acd5c473f91afb8dad424d6369fc63b638f9d089c91b41a5d442762`.
The synchronized chain touches two UTC calendar days, so the exact prospective
condition remains **WAITING_FOR_DATA** until 28 forward calendar days of
registered, closed, contiguous and integrity-accepted candle/OI evidence are
available. No open journal or supervisor was inspected.

Search 011 tested a signed-flow proxy distinct from raw-volume shock/reversal,
low-volume dislocation reversal and price momentum. Each UTC day it ranked
non-BTC/ETH symbols by trailing volume-weighted candle close location, bought
the two highest-pressure and sold the two lowest-pressure symbols, then held
one day. Frozen 7/14-day windows ran in four disjoint 30-day folds under all
three cost schedules. A preregistered rank-overlap gate rejected any substantial
relabeling of trailing price momentum. All 24 evaluations were retained as
`DISCOVERY_ONLY_NOT_FRESH_VALIDATION`.

The result is **REJECTED_DISCOVERY_ONLY**. The 7-day window earned 269.69 USDT
gross and 52.28 USDT at base cost but lost -103.86/-123.45 USDT under
wide/severe costs, had only two positive folds and derived 172.71 USDT of its
base result from the final fold. Its seven-day block interval crossed zero and
Holm-adjusted p was 0.820. The 14-day neighbor was gross-negative, lost 305.26
USDT at base cost, had one positive fold and Holm p=0.930. Both windows passed
the momentum-overlap, BTC-attribution and concentration safeguards; the failure
is therefore cost fragility and temporal non-replication rather than a rejected
momentum relabel. No parameter retuning, candidate freeze or promotion is
authorized.

### Read-only prospective chain audit — 2026-10-24 UTC

No search identity was consumed and nothing was scored. The new read-only
`inspect-prospective` summary re-verified the primary checkout's ignored
`data/public/prospective_*` chunks (paths, dataset identities, payload hashes,
per-symbol timestamp coverage, contiguity, `safe_available_ms` rule and the fixed
Search 004 source-universe hash):

| Chain | Chunks | Points per symbol | Coverage | Last collection |
| --- | ---: | ---: | --- | --- |
| 20-symbol 15m candles | 34 | 105 | 2026-09-23 10:00 to 2026-09-24 12:15 UTC (26.25 h) | 2026-09-24 12:27 UTC |
| 20-symbol open interest | 13 | 66 | 2026-09-23 19:45 to 2026-09-24 12:15 UTC (16.5 h) | 2026-09-24 12:27 UTC |

Sixty-six feature timestamps have both a candle and an OI point; 64 have a
completed execution bar strictly after both availability bounds. Covered forward
time is **1.09 of the 28 required days**. No collector process was running and the
newest chunk was about 29 days old, so the collector state is `STALE`. The
supervisors that were relaunched on 2026-09-24 09:26 UTC therefore stopped after
their 12:27 UTC rounds; their exit cause was not inspected.

Consequences, stated before any restart: the candle chain can only continue by
REST backfill, and every backfilled bar would carry the backfill time as its
`safe_available_ms`, making it later-observed context rather than contemporaneous
evidence. The OI chain cannot continue under its current collector because the
gap (about 2,880 points per symbol) exceeds its deliberate 200-point single-page
recovery bound. Resuming OI requires either a new, explicitly disclosed chain
identity or a separately reviewed bounded-recovery change. Neither was done here.
The forward-day gate remains `WAITING_FOR_DATA`. LIVE remains disabled.

### Engine corrections and disclosed limitations — 2026-10-24 UTC

A read-only code audit (eleven review dimensions, adversarially verified where the
budget allowed) found no defect that changes any sealed search conclusion: every
consumed search remains rejected, and no result artifact or manifest was edited.
Consumed runners refuse a rerun, and each sealed result records the Git SHA that
reproduces it. The following corrections therefore apply only to future searches:

- Replay now fails closed on a funding settlement off the 15-minute bar grid. All
  126,298 settlements in the three existing economics files are on the grid, so
  past replays were unaffected.
- A bar that opens beyond the target exits at the target (`TARGET_AT_OPEN`) before
  the stop-first rule applies; a zero-quantity sizing result is rejected.
- The descriptive regime label now uses an equal-weight return index; before, a mean
  of price levels made it effectively BTC's 24-hour return. Sealed `regime_net_pnl`
  values use the old label and are descriptive only.
- Simulation time stops now count from the entry bar like the replay; before they
  fired one bar late. Reference signal strength now matches the research ranking.

Disclosed limitations of consumed searches (not rerun, not relabelled):

- Search 005's frozen 0.30 day-share gate was unsatisfiable: each two-day forward fold
  spans at most three UTC days, so its day share is at least one third. The search was
  rejected on gross economics in every fold, so the gate did not decide the outcome.
- The final 003 descriptive `pnl_slope_per_unit_market_return` mixes a sample
  covariance with a population variance, overstating the slope by n/(n-1), about 0.8%.
  It was never a gate.
- The merged 39-symbol economics file uses the limit-order cap (`maxOrderQty`) for
  BTC/ETH and the market-order cap for the other 37 symbols as `max_qty`.
- The testnet transport's 36-character `tv2_` order-link identity cannot match the
  32-character `tv2-` journal client identity, so journal-based ownership recovery
  cannot succeed yet. This is one more unmet item of authenticated testnet
  acceptance, not a reachable trading path.

### Public-only collection restarted — 2026-10-24 UTC

On operator instruction, public-only collection resumed. Code runs from a detached
collector checkout pinned at `98aa9ca` (ignored `runtime/collector-checkout-98aa9ca`);
evidence, status and logs are written under this checkout. The supervisors were
started as independent processes so they do not end with an interactive session.
They do not survive a reboot. No search identity was consumed and nothing was scored.

- **Candles.** One labelled backfill chunk, `BYBIT_PUBLIC_FORWARD_1790252100000_1792842300000`,
  closed the gap: 2,879 bars per symbol, `BACKFILL_LATER_OBSERVED`, schema-2
  availability. These bars are later-observed context and never count toward the gate.
  The chain stays contiguous and continues every 30 minutes.
- **Open interest.** `OI_CHAIN_001` is closed at its 2026-09-24 12:00 UTC point.
  `OI_CHAIN_002` began with `BYBIT_PUBLIC_OI_FORWARD2_1792841400000_1792842300000`. Its
  genesis manifest names the predecessor's last chunk and payload hash and records an
  unobserved gap of 2,877 points per symbol (2026-09-24 12:15 to 2026-10-24 11:15 UTC),
  `backfilled: false`, with the stop reason. A plain continuation of chain 1 was refused
  first, as designed.
- **Supervisors.** Candle `bars-continuation-20261024T120845Z` and OI
  `oi-continuation-20261024T120845Z`: up to 2,880 rounds of 30 minutes, a 100 GiB disk
  floor, and a stop after three consecutive failures. The first candle round after the
  backfill was a benign "no new closed bar yet" refusal. The first steady-state rounds at
  12:38 UTC both succeeded: candle chunk `BYBIT_PUBLIC_FORWARD_1792843200000_1792844100000`
  and OI chunk `BYBIT_PUBLIC_OI_FORWARD2_1792843200000_1792844100000`, after which the
  independent read-back verified both chains and the gate stood at 0.04 days.
- **Superseded launch.** A first launch from `f70d45d` wrote status under the code
  checkout. It was stopped between rounds, with no round interrupted, and its records
  were moved here as `SUPERSEDED_BY_RELAUNCH`.
- **Gate.** Directly after the restart: 0.02 of 28 gap-free contemporaneous joint days
  (newest run 11:30 to 12:00 UTC). Under the same stricter rule the pre-restart chain
  held 0.15 days, because 36 of its bars were themselves backfilled. If every round
  succeeds, the forward-day requirement can first be met around 2026-11-21. Meeting it
  authorizes nothing by itself.
- **Compatibility.** Collectors on `research/prospective-evidence-005` predate chain
  succession and schema-2 candle availability. They cannot extend these chains and fail
  closed if run; do not start them against this data.

### Collection moved to an always-on host — 2026-10-24 UTC

The workstation sleeps and restarts, and every interruption resets the gap-free run,
so collection moved to an always-on Ubuntu 20.04 host on the local network (clock
NTP-synchronized). Nothing needed root access.

- **Local stop.** Both workstation supervisors were stopped between rounds at 12:45 UTC.
  No round was interrupted, and their status records read `STOPPED_FOR_SERVER_MIGRATION`.
- **Host runtime.** User-space CPython 3.12.11 installed with `uv`; a dedicated virtual
  environment holds numpy 2.2.6, pydantic 2.14.1, httpx 0.28.1 and portalocker 3.2.0.
  The code is an archive of commit `d45db6b` with a `COLLECTOR_COMMIT` marker.
- **Chain hand-over.** All 51 chain directories, the Search 004 universe manifest and
  the 004 result were copied unchanged. The host's own read-back reproduced the
  workstation summary before any new round ran.
- **Rounds.** A user crontab runs `ops/collection_round.py` at minutes 7 and 37 of every
  hour; it survives reboots and opens no window. A manual round at 12:50 UTC and the
  first cron round at 13:07 UTC both collected a candle and an `OI_CHAIN_002` chunk
  (`..._1792845000000_...` and `..._1792845900000_...`) with no failure.
- **Source of truth.** The host's data root now holds the authoritative chains. This
  checkout's copy changes only through `ops/pull_prospective.py`, which adds absent
  chunks, refuses divergent ones and re-verifies. A first pull added two chunks, found
  51 identical, and reported 0.05 of 28 gap-free contemporaneous days.

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
4. **OI inventory-state conditioning.** A decline in both-sides OI alongside
   a price shock may distinguish position unwinds from new-risk build-up;
   whether either state predicts continuation or reversal remains unknown.
   This needs synchronized, point-in-time OI and price, contract-unit
   normalization, settled funding and cost-aware next-available execution.
   OI alone cannot identify whether longs or shorts were liquidated. Reject
   the mechanism if it is explained by price beta, sparse events, or fees.

Before any new search: capture enough **post-registration, independently dated**
days for training, chronological validation, and at least 28 forward days;
verify continuous sequence/timestamp integrity and symbol coverage; preregister
fixed features, parameter/trial budget, folds, costs, execution assumptions,
neighbor tests, beta regressions, multiplicity accounting and promotion gates.
Do not label overlapping or previously inspected data as untouched. If the
recorder stops or disk/time coverage is inadequate, preserve its partial result
and continue public collection rather than manufacture a search outcome.
