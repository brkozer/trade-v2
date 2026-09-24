# Discovery Search 007 — cross-sectional low idiosyncratic volatility

Evidence role: **DISCOVERY_ONLY_NOT_FRESH_VALIDATION**

Search identity: `TRADEV2_DISCOVERY_007`. The reused 210-day dataset is consumed historical
evidence, not fresh validation and not eligible to satisfy the prospective gate.

## Frozen mechanism and design

The experiment tested whether speculative preference and leverage constraints
overprice high-idiosyncratic-volatility altcoins. At each Monday 00:00 UTC entry,
it went long the two lowest- and short the two highest-residual-volatility
non-BTC/ETH symbols for seven days. Residual volatility used only closed returns
and a rolling BTC/ETH regression. Frozen 14- and 28-day lookbacks were both run
through four disjoint 30-day forward folds under base, wide and severe costs.
There was no outcome-based winner selection. All 24 evaluations were retained.

## Result

Status: **REJECTED_DISCOVERY_ONLY**

| Lookback | Trades | Gross R | Net R | Positive folds | Base PnL | Wide PnL | Severe PnL | Holm p | BTC beta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 14d | 68 | -0.0439 | -0.0629 | 2/4 | -103.78 | -125.49 | 21.41 | 0.9005497251374313 | 0.0327 | FAIL |
| 28d | 68 | 0.0336 | 0.0150 | 2/4 | 26.31 | 4.69 | 80.16 | 0.9005497251374313 | 0.0314 | FAIL |

The 14-day variant had negative gross and net economics. The 28-day variant
retained only 26.31 USDT after base costs and 4.69 USDT after wide costs; its
higher severe result reflects half-size exposure and deterministic missed fills,
not monotone cost robustness. Its gains occurred only in folds three and four,
while folds one and two lost 195.99 and 47.46 USDT. The weekly-block interval
[-4.59, 4.62] USDT/day spans zero, Holm-adjusted p is 0.901, and daily BTC
correlation of 0.308 narrowly exceeds the frozen 0.30 cap. The positive result
is therefore unstable and statistically weak despite low estimated BTC beta.

Only 68 trades are mechanically possible per configuration with four legs at a
weekly rebalance over the frozen 120-day forward period. The preregistered
200-trade gate was therefore structurally unreachable. This consumed design
limitation is recorded without weakening the gate, changing cadence or rerunning
the identity. Together with two of four positive folds and the losing 14-day
neighbor, it prevents candidate status.

No live, testnet or paper authority is granted. A passing discovery result, if
any, is only a frozen candidate awaiting genuinely fresh validation.

## Verification

- Completion seal: 24/24 evaluations; result SHA-256
  `90ad6ea6d1facb560e1568e90c53aa17f2f652cf0a033e7d8f899c5d28aa8bbe`.
- Full Python suite: 138 passed.
- Ruff: passed.
- Search 007 module mypy: passed before the frozen run.
- Repository-wide mypy: the sole failure remains the pre-existing missing
  `ndarray` type arguments at `ops/extend_btc_eth_public.py:100`.
- Frontend: 6 tests passed and the production build passed.
