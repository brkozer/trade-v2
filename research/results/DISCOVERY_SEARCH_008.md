# Discovery Search 008 — low-volume range-dislocation reversal

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_008`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

This experiment discriminated low-participation mechanical impact from the
previously rejected high-volume shocks and generic volatility expansion. It
reversed a candle only when its range was at least 2× its lagged 96-bar mean,
volume was no more than 0.75× its lagged mean, the close was in the outer 10% of
the range, and the body cleared 1.5× or 2.5× symbol-specific base round-trip
cost. Entries occurred at the next open and held four bars. Both variants ran
through four disjoint 30-day forward folds under base, wide and severe costs;
all 24 evaluations were retained with no outcome-based winner selection.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

| Cost hurdle | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | BTC beta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.5× | 174 | -0.0315 | -0.1019 | 0/4 | -441.64 | -667.27 | -180.11 | 1.0 | -0.0036 | FAIL |
| 2.5× | 166 | -0.0349 | -0.1056 | 0/4 | -436.74 | -652.55 | -225.24 | 1.0 | -0.0030 | FAIL |

Both variants had negative gross expectancy before costs and lost in all four
forward folds. At 1.5×, gross PnL was −137.37 USDT; fees, spread and slippage
removed another 305.18 USDT while funding receipts offset only 0.91 USDT. The
2.5× hurdle removed just eight trades and made gross expectancy slightly worse,
so larger apparent dislocations did not rescue the mechanism. Seven-day block
intervals were wholly negative (respectively [−5.51, −1.65] and
[−5.53, −1.66] USDT/day) with Holm-adjusted p=1.0.

BTC daily betas and correlations were near zero, and symbol/day concentration
stayed below the frozen limits. The failure is therefore not explained by broad
market exposure or a single contributor: low-participation extreme candles did
not mean-revert as hypothesized. Smaller severe losses reflect half-size and
missed-fill assumptions, not robustness. Neither variant reached the 200-trade
gate, but the negative gross result and zero positive folds already reject it.

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.

## Verification

- Completion seal: 24/24 evaluations; result SHA-256
  `9bc58a29f6011b975faf98108ab7598885bd65c7de712a71f3bd54e50ae2df54`.
- Full Python suite: 143 passed.
- Ruff: passed.
- Search 008 module mypy: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Frontend: 6 tests passed and the production build passed.
