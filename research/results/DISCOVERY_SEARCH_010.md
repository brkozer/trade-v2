# Discovery Search 010 — cross-sectional downside-beta defensiveness

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_010`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

This experiment tested whether forced deleveraging makes altcoins with high
conditional BTC downside beta underperform defensive peers. At each UTC day
boundary it ranked non-BTC/ETH symbols by beta estimated only during negative
BTC 15-minute returns, went long the two lowest and short the two highest, and
held one day. Frozen 14- and 28-day lookbacks ran through four disjoint 30-day
forward folds under base, wide and severe costs. There was no outcome-based
winner selection; all 24 evaluations were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

| Lookback | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | BTC beta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 14d | 464 | -0.0166 | -0.0354 | 2/4 | -404.56 | -561.93 | -192.41 | 1.0 | -0.0563 | FAIL |
| 28d | 464 | -0.0168 | -0.0355 | 2/4 | -400.10 | -557.13 | -216.99 | 1.0 | -0.0546 | FAIL |

Both configurations were already negative before costs: gross PnL was
-187.69 USDT for 14 days and -184.63 USDT for 28 days. Base net losses were
-404.56 and -400.10 USDT, each with only two positive folds; their seven-day
block intervals crossed zero and Holm-adjusted p-values were 1.0. Higher severe
PnL reflects half-size and missed-fill assumptions, not cost robustness.

The result also failed the intended structural safeguards. Absolute BTC daily
correlation was 0.385/0.360 against the frozen 0.30 cap, and symbol
concentration was 0.372/0.479 against 0.35. The longer lookback reached only
10 symbols and concentrated -352.97 USDT in USELESSUSDT. This rejects a stable,
diversified downside-beta defensiveness premium in this consumed panel; no
lookback, leg count, holding period or rebalance cadence may be retuned under
this identity.

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.

## Verification

- Completion seal: 24/24 evaluations; result SHA-256
  `3ebf0cde56d4b60a5cc49f27a41a9382bdaabb5208ff1bc583f0a84f980ecde0`.
- Full Python suite: 153 passed.
- Ruff: passed.
- Search 010 module mypy: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Artifact/secret-pattern gate: passed with zero violations.
- Frontend: 6 tests passed and the production build passed.
