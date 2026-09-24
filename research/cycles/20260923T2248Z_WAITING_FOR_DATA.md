# Bounded research cycle — 2026-09-23 22:48 UTC

Status: **WAITING_FOR_DATA**

This cycle consumed no search identity and scored no hypothesis or candidate.
It inspected completed public datasets and terminal supervisor status only; no
open recorder journal was read.

## Closed evidence accepted

Independent read-back accepted three new candle chunks and three new OI chunks
for the fixed 20-symbol Search 004 universe. Across the complete prospective
chains:

- 25 candle chunks contain 960 contiguous symbol-bars from 10:00 through
  21:45 UTC, with exact universe/timestamp coverage, matching payload hashes,
  finite valid OHLCV geometry and declared availability bounds;
- five OI chunks contain 200 contiguous symbol-points from 19:45 through
  22:00 UTC, with exact universe/timestamp coverage, matching payload hashes,
  positive finite Decimal quantities and stable clock probes;
- nine OI timestamps have matching accepted candles; and
- six of those timestamps also have a completed candle at the first bar open
  strictly after both source-availability bounds.

The newly accepted candle payload hashes are:

- `8e91e8a7b4324b8ed91ed63a5429af94151bf9cb56a10e72f0a22a47f40ab2bc`
- `5d044b116d8db18317c012272080ee6f2a9e1ccfbdd8a8d7c109c3b31689eb52`
- `b8a08bd84c5e6f04be627174f9e0c1336cbe7ef535f0852dcdfcd0abb59b800f`

The newly accepted OI payload hashes are:

- `905c77f00dfc6e1520aceeb0eaacb8e3d79e3e3b61189444b8ae0382612e87af`
- `b96f7b6b2a821502cbcbfa0649898908a0c8c7828b51f2268a6901cb9331800f`
- `570e76efc1b4e856c23d09dcf2b26ede1732ea5d2cbc0790a1c6ce77258cac7b`

This remains a few hours on one calendar day, not enough independently dated
post-registration evidence for training, chronological validation and at least
28 forward days. No outcome distribution or net expectancy was estimated.

## Candle continuation defect

The initial bounded candle campaign completed all 24 rounds with zero failures,
then its long continuation failed on the first native collector error. Windows
PowerShell converted native stderr into an error record under the script-wide
`Stop` policy, bypassing the intended nonzero-exit retry accounting. The helper
also lacked an explicit safe resume mode after its wait target had exited.

The repair keeps the strict outer error policy but temporarily uses `Continue`
only around the native collector invocation, captures its exit code, restores
the strict policy, and then applies the existing three-consecutive-failure
bound. `ResumeExistingChain` is an explicit mutually exclusive startup mode;
it does not bypass chain integrity, disk, round, or failure gates.

## Exact wait condition

An alpha experiment remains ineligible until closed, independently accepted,
gap-free OI and candle evidence covers the fixed prerequisite, including at
least 28 forward days, and every scored outcome has a completed execution bar
strictly after the later source-availability bound. Search/trial counts remain
unchanged. LIVE remains disabled.

## Verification

- PowerShell AST parse and native-stderr/nonzero-exit smoke: passed.
- Pytest: 124 passed (two dependency deprecation warnings).
- Ruff: passed.
- Frontend Vitest: 6 passed.
- Frontend TypeScript/Vite production build: passed.
- Mypy retains the pre-existing unrelated missing `numpy.ndarray` type
  arguments at `ops/extend_btc_eth_public.py:100`.

## Autonomous restart

After commit `60c90ad`, the repaired candle helper was started exactly once as
independent PID `37304`. An immediate process-table read confirmed the intended
`ResumeExistingChain` command with 1,344 maximum rounds, 1,800-second intervals
and a 100 GiB disk floor. Launch output is retained under
`runtime/recorder/bars-resume-20260923T225157Z.{stdout,stderr}.log`. No later
process/status check or journal read was performed.
