# Discovery Search 011 — volume-weighted close-location pressure

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_011`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

This experiment tested whether persistent informed flow repeatedly closes
high-volume bars near their directional extreme and continues into the next
day. At each UTC day boundary it ranked non-BTC/ETH symbols by trailing
volume-weighted close location, went long the two highest and short the two
lowest, then held one day. Frozen 7- and 14-day windows ran through four
disjoint 30-day forward folds under base, wide and severe costs. A frozen
momentum-overlap gate rejects a relabeled trailing-return strategy. There was
no outcome-based winner selection; all 24 evaluations were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

| Window | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | Momentum overlap | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 7d | 464 | 0.0234 | 0.0047 | 2/4 | 52.28 | -103.86 | -123.45 | 0.8195902048975512 | 0.457 | FAIL |
| 14d | 464 | -0.0072 | -0.0263 | 1/4 | -305.26 | -461.59 | -78.93 | 0.9295352323838081 | 0.420 | FAIL |

The 7-day window earned 269.69 USDT gross and retained only 52.28 USDT at base
cost. It lost 103.86 USDT under wide costs and 123.45 USDT under severe costs;
only folds two and four were base-positive, with 172.71 USDT of the aggregate
base result arriving in the last fold. Its seven-day block interval crossed
zero [-3.96, 6.06] USDT/day and the Holm-adjusted p-value was 0.820.

The 14-day neighbor was already gross-negative at -85.26 USDT, lost 305.26
USDT at base cost and had one positive fold. Both windows passed the frozen
momentum-overlap cap (median absolute daily Spearman 0.457/0.420), BTC
attribution limits and concentration limits. The result therefore rejects a
stable, cost-robust continuation premium from this OHLCV flow proxy: its short
window produced a fragile late-period base-only edge, while the neighboring
window reversed sign. No window, holding period or rebalance cadence may be
retuned under this identity.

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.

## Verification

- Completion seal: 24/24 evaluations; result SHA-256
  `79fa60900fd448292f75974bb37eada19ae4884a07edfadef3cb89e86a06d36a`.
- Full Python suite: 159 passed.
- Ruff: passed.
- Search 011 module mypy: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Artifact/secret-pattern gate: passed with zero violations.
- Frontend: 6 tests passed and the production build passed.
