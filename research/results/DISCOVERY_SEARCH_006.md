# Discovery Search 006 — UTC-hour cross-sectional seasonality

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_006`. The 210-day dataset was already consumed by
earlier research. This result is not fresh validation and cannot satisfy the
prospective acceptance gate.

## Frozen mechanism and design

Training-only mean next-hour returns were estimated for every symbol/UTC-hour
cell and demeaned across symbols at that hour. Signals occurred once per hour
and were admitted only when predicted gross excess return cleared the symbol's
base taker/spread/slippage hurdle plus a frozen 0 or 10 bp buffer. Four nested
expanding folds used a 30-day inner selection and the next 30 days as untouched
within-search forward data. All 24 planned evaluations were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

- Forward trades: 2726
- Symbols traded: 21
- Mean gross/net R: -0.0014595633456581836 / -0.07533438929060096
- Positive folds: 1/4
- Base/wide/severe net PnL: -4482.214176 /
  -7222.811199 / -4093.000049 USDT
- Neighbor-positive folds: 0/4
- Symbol/day concentration: 0.2435024231332057 /
  0.03367160134594127
- Weekly-block bootstrap 95% interval and positive p-value:
  [-58.3796381993948, -16.619129296263147],
  p=1.0
- Selected buffer counts: {'0.0': 2, '0.001': 2}

The aggregate gross PnL was already slightly negative at −35.52 USDT. Fees,
spread and slippage then consumed 4,452.96 USDT, while funding receipts offset
only 6.26 USDT. The zero-buffer model generated most trades and large losses;
the 10 bp buffer produced one positive 90-trade fold followed by a negative
90-trade fold. The selected buffer split 2/2 across folds, every neighboring
buffer fold lost money, maximum fold drawdown reached 28.90%, and the weekly
block interval was wholly negative. This is unstable calendar structure with
no gross or net edge, not a cost-sensitive near miss.

No live, testnet, paper or prospective-shadow authority is granted. The machine
result retains every selection, forward-cost and neighboring-buffer evaluation.

## Verification

- Full Python suite: 133 passed.
- Ruff: passed.
- Search 006 module mypy check: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Frontend: 6 tests passed and the production build passed.
