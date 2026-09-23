# Trade v2 Alpha Search 004 — no prospective-shadow promotion

Search identity: `TRADEV2_ALPHA_SEARCH_004`. The [preregistration](../manifests/alpha_search_preregistration_004.json), [machine result](ALPHA_SEARCH_004.json), and [completion seal](../manifests/alpha_search_completion_004.json) are create-only. The 002 aborted attempt and 003 negative result remain consumed and unchanged. A first 004 invocation stopped **before any evaluation** because JSON changed tuple parameters to lists in the registration comparison; only that serialization comparison was corrected. The fixed grid, data, costs and gates were not changed.

The target baseline was merged `main` `737e7a47e5f8aadaa504ae7f95010258cca72344`. Read-only source heads were AegisQuant `add466d3d56a7dee57174a68655e256ae965bdf5` and the Bybit prototype `e136564ed488a63c7f55d800d2a598bfc40ab497`, each matching its GitHub `main` at inspection. The AegisQuant source had an existing untracked `reports/` directory; it was not touched.

## Dataset classification

| Role | Evidence | Use in 004 |
| --- | --- | --- |
| Consumed historical | 37/39-symbol 210-day panel ending 2026-09-08 21:45 UTC; initial and 003 search results | Not reopened for scoring |
| Newly acquired, previously untested public history | `BYBIT_PUBLIC_POST003_004`, 20 dynamically turnover-ranked USDT linear instruments, 2026-09-08 22:00 to 2026-09-23 07:45 UTC, 1,384 continuous confirmed 15m bars/symbol | Sole OHLCV/funding search panel; consumed by 004 |
| Reserved | Final 232 bars (2.42 days) of that same downloaded panel were not replayed for outcomes | Not called independent final holdout |
| Prospective recorder | Two 6-second 10-symbol public WebSocket journals, run IDs `2a243fe233e749eaad5462bb3a976829` and `2f3708122d6e462e803604e1eea1f726` | Book/trade/sequence integrity smoke only; no alpha training |

The new panel's **market interval mostly predates** the 003 search completion on 2026-09-23 00:41 UTC even though it was downloaded later and begins after the *source cutoff* of the consumed panel. It is new-to-research history, **not** an entirely post-search prospective holdout. There are at most hours of genuinely post-003 market time. The dynamic 24h-turnover universe also has current-selection/survivorship bias. Raw public REST responses, book snapshots, rules, funding and exact file hashes are in target-local ignored `data/public/alpha_search_004/manifest.json`; the preregistration pins its manifest, candle and economics hashes. Raw data is not copied into Git.

Read-back quality: 27,680 symbol-bars, zero timestamp gaps, zero nonfinite OHLCV values, and valid panel high/low geometry. The lowest selected current 24h turnover was 120.3 million USDT; collection-time spreads ranged from 0.012 to 4.675 bps. Every symbol had at least 200 settled funding observations. These are **collection-time** liquidity measurements, not historical spread or depth series.

Public recorder A reopened `VERIFIED`: 1,721 messages, 1,583 books, 490 public trades, zero reconnects/invalid books. Recorder B reopened `VERIFIED`: 1,707 messages, 1,427 books, 1,195 trades, zero reconnects/invalid books. Both retain source timestamps and book sequences. Seconds-long streams cannot establish historical imbalance, adverse selection, or maker fill rates.

## Design and execution assumptions

Six new, economically differentiated OHLCV/funding mechanisms were evaluated (two preregistered thresholds each: **12 configurations**). Three expanding chronological windows used a one-day inner selection interval followed by a frozen two-day forward interval. There were **36 selection, 18 base forward, 18 wide, 18 severe and 18 neighboring-parameter evaluations = 108**. The three forward slices span only six calendar days. No random split, same-close fill, or full-history winner was used. Each fold starts flat, and aggregate PnL is a sum of independent simulated fold outcomes, not an account equity curve. No ML model was trained: the independent days, not nominal 20×1,384 rows, are the binding sample size.

The replay enters at the next bar and uses point-in-time closed OHLCV plus settled funding, 10,000 USDT fold start, 0.25% per-trade risk budget, four positions maximum, 80% gross notional cap, current instrument minimums, and conservative stop-first intrabar ambiguity. Base uses VIP0 taker 0.055% per side, current observed half-spread on each side and 1 bp slippage per side; wide multiplies fees ×1.5/spread ×2 with 3 bp slippage; severe multiplies fees ×2/spread ×3 with 5 bp slippage, one-bar latency, 50% size and deterministic missed fills. Historical queue position, maker fills and spread time series are unknown, so **the primary economic claim is taker/taker**, not a modeled maker alpha. Funding is observed at settlement timestamps with entry-notional approximation. Current venue/fee observations are not historical snapshots.

## Results

Forward `R` is mean **net R per filled trade** across the three base-cost outer folds; USDT columns are the sum of independent fold PnL, not compounded equity. Figures are rounded here; exact values and all 108 attempts are in the machine result.

| Family | Net R | Trades | Positive folds | Base USDT | Wide USDT | Severe USDT | Neighbor positive | Worst fold DD | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Breadth transition | -0.148 | 265 | 0/3 | -968.85 | -1,240.84 | -622.70 | 0/3 | 4.53% | REJECTED |
| Dispersion exhaustion | +0.069 | 112 | 2/3 | +192.89 | +34.41 | -146.08 | 0/3 | 1.62% | REJECTED |
| Volatility term release | -0.219 | 116 | 0/3 | -630.00 | -744.78 | -205.52 | 0/3 | 3.43% | REJECTED |
| Funding-price disagreement | -0.103 | 37 | 1/3 | -95.01 | -134.60 | -117.93 | 1/3 | 1.16% | REJECTED |
| Volume-breadth confirmation | -0.026 | 125 | 1/3 | -84.42 | -208.20 | -62.73 | 2/3 | 2.87% | REJECTED |
| Low-beta residual trend | -0.112 | 180 | 0/3 | -504.34 | -666.43 | -311.73 | 1/3 | 3.19% | REJECTED |

Dispersion exhaustion is the only positive base-cost family, but its severe arm is negative, both neighboring-threshold forward tests fail in all three folds, only two folds are positive, and worst-fold absolute symbol/day shares are **59%/77%**. This is an isolated fragile result, not a candidate to promote. Breadth and volume-breadth are also concentrated. Market-beta attribution remains **unestimated on this short independent sample**; no family receives credit for beta independence by assumption. Day-block confidence intervals and multiple-test-adjusted significance are not reported because six forward days cannot sustain them. All six tested families are rejected; zero are promoted.

The remaining **18 of 24 investigated family ideas** are explicitly `UNSUPPORTED_WITH_CURRENT_DATA` in the machine result. They either repeat already-consumed 003 mechanisms or require a historical, timestamp-matched book/trade/queue/outcome series the two recorder smokes cannot supply. Their zero trial count is not a negative performance estimate. The search did not tune around these unsupported observations or invent microstructure history.

**Decision: NONE worth prospective shadow testing.** The absence of an accepted strategy is a measured outcome, not a software failure. No paper, authenticated testnet or live mutation was authorized or made by this research run.
