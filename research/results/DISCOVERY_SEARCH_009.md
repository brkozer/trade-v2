# Discovery Search 009 — cross-sectional idiosyncratic MAX effect

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_009`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

This experiment isolated positive-tail lottery demand from Search 007's generic
residual-volatility test. At each UTC day boundary it ranked non-BTC/ETH symbols
by their maximum 15-minute residual return from a causal rolling BTC/ETH
regression, went long the two lowest-MAX and short the two highest-MAX symbols,
and held one day. Frozen 14- and 28-day lookbacks ran through four disjoint
30-day forward folds under base, wide and severe costs. There was no
outcome-based winner selection; all 24 evaluations were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

| Lookback | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | BTC beta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 14d | 464 | 0.0008 | -0.0193 | 1/4 | -225.12 | -381.58 | -120.50 | 1.0 | 0.0128 | FAIL |
| 28d | 464 | -0.0044 | -0.0241 | 1/4 | -281.38 | -437.61 | -136.49 | 1.0 | 0.0183 | FAIL |

The 14-day variant was essentially gross-flat at +7.25 USDT, then paid 156.38
USDT in fees, 36.89 USDT in spread, 23.10 USDT in slippage and 15.99 USDT in
funding for a −225.12 USDT base result. Its only positive fold was followed by
the worst fold. The 28-day variant was already gross-negative at −54.02 USDT
and lost −281.38 USDT net. Both variants had just one of four positive folds;
their seven-day block intervals crossed zero and Holm-adjusted p-values were 1.0.

Both configurations cleared the trade and aggregate concentration gates, while
BTC beta and correlation stayed small. The result therefore discriminates
against a stable positive-tail lottery premium: the shorter feature offered no
material gross edge to fund daily turnover, and the longer feature reversed
sign. Smaller severe losses reflect half-size and missed-fill assumptions, not
robustness. No lookback, holding period or rebalance cadence may be retuned under
this identity.

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.

## Verification

- Completion seal: 24/24 evaluations; result SHA-256
  `17be1171248d49a7aec3f441c04793a73a478b23c0ba948fa42159073d70cea1`.
- Full Python suite: 148 passed.
- Ruff: passed.
- Search 009 module mypy: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Frontend: 6 tests passed and the production build passed.
