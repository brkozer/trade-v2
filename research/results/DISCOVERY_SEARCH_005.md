# Discovery Search 005 — funding-settlement carry

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_005`. This bounded search reused the consumed Search
004 panel. It is not fresh validation and cannot satisfy prospective acceptance.

## Frozen mechanism and design

Two consecutive same-sign settled funding rates were treated as a persistence
condition. At the close of the settlement-opening bar, the strategy takes the
funding-receiving side at the next bar open and holds for 32 bars, subject to
the standard portfolio, stop, fee, spread, slippage and funding ledger. Two
absolute-rate thresholds (0.5 and 1.0 bp) were frozen. Three one-day selections
were followed by disjoint two-day forward folds. All 18 planned evaluations
were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

- Forward trades: 72
- Mean gross R: -0.2338720319053945
- Mean net R: -0.2905455867190185
- Positive folds: 0/3
- Base net PnL: -520.174237 USDT
- Wide net PnL: -593.352025 USDT
- Severe net PnL: -325.657034 USDT
- Neighbor-positive folds: 0/3
- Maximum symbol/day absolute shares: 0.374 /
  0.846

All three forward folds lost money, as did both neighboring-threshold arms.
Across the base folds, receiving funding contributed 6.075 USDT, while price
movement lost 418.726 USDT before 78.990 USDT fees, 14.171 USDT spread and
14.362 USDT slippage. The mechanism therefore failed on gross directional
economics as well as net costs; the smaller severe-arm loss reflects half-size
and missed fills, not robustness.

The frozen description assumed an expected eight-hour next settlement. Read-back
after completion found MUBARAK, ENA and XAU on four-hour histories and CL on a
mixed four/eight-hour history in the reused dataset. The fixed 32-bar hold can
therefore cross two settlements for those symbols. This consumed design
limitation prevents generalizing the result to an exactly-one-settlement carry
rule; it does not rescue the failed candidate, and no post-outcome rerun or
symbol exclusion was performed.

No live, testnet, paper or prospective-shadow authority is granted. The exact
fold arms and every selection, forward-cost and neighbor trial are retained in
the machine result.

Verification: the completion seal and all 18 trial records reconciled; 128
Python tests, Ruff, six frontend tests and the production build passed. Mypy
retains the pre-existing unrelated missing `numpy.ndarray` type arguments at
`ops/extend_btc_eth_public.py:100`.
