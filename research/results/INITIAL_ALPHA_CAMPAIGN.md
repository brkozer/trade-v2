# Initial Alpha Factory campaign

Search: `TRADEV2_INITIAL_ALPHA_001`.

This is a reproducible historical discovery experiment. All source candles were previously
inspected in legacy research. Chronological validation here is **not untouched final OOS**.

Dataset: `BYBIT_PUBLIC_REUSED_37_OHLCV_210D`, 37 symbols, 20159 15m bars each.
UTC coverage: 2026-02-10T22:15:00+00:00 to 2026-09-08T21:45:00+00:00 (bar opens).

All37 source symbols were retained. Exact consecutive minute bins were aggregated without imputation.
Search budget: {'configurations': 18, 'selection_evaluations': 72, 'validation_evaluations': 24, 'stress_evaluations': 48, 'total_replays': 144}. All failed trials remain in campaign.json.

Four expanding training windows each choose one of three predefined configurations per family.
The following30-day interval measures that frozen choice; no validation outcome tunes the next
grid. Earlier validation naturally enters later expanding training. Fold boundaries close all positions.
Selection penalizes daily PnL volatility and requires50 training trades. Weekly block bootstrap
and Holm adjustment across six family paths supplement, but cannot repair, prior-history contamination.

| Family | Discovery net R | Validation trades | Validation net R | Net USDT | Fees | Funding | Spread + slip | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| rsi_reversion | -0.0598118123886381 | 1516 | -0.019799462069484224 | -796.69 | 2284.12 | 12.46 | 964.32 | REJECTED |
| time_series_momentum | -0.10838723240918569 | 6551 | -0.13419994740269486 | -16948.76 | 9149.10 | 21.65 | 3310.06 | REJECTED |
| compression_breakout | -0.07414535710185782 | 1051 | -0.14411971377150154 | -3643.90 | 1538.52 | 16.70 | 653.94 | REJECTED |
| relative_strength | -0.1080265644403484 | 5952 | -0.12476804662920951 | -14496.69 | 8257.01 | 5.63 | 3085.91 | REJECTED |
| basket_residual_reversion | -0.08161297944239979 | 4483 | -0.06151665936453342 | -6239.53 | 6256.45 | -19.25 | 2649.21 | REJECTED |
| volume_shock | -0.11249047028508735 | 5443 | -0.10426249772666293 | -11921.38 | 7426.36 | 23.48 | 3060.32 | REJECTED |

Each fold starts with10,000 simulated USDT. Total PnL combines four independently reset folds;
it is not a compounded deployable account return. Rejections, regime/symbol concentration, tails,
daily equity changes, stress arms and opportunity-paired deltas are in campaign.json.

## Costs and execution

Primary replay uses taker/taker fees: dated measured5.5bps per side
for34 symbols and11bps for HEMI/USELESS/VVV, plus at least3bps roundtrip spread and1bps slippage
per side. Actual settled funding times apply with entry-notional approximation. Quotes, queue
priority and historical mark prices are unavailable. Current public venue quantity/minimum rules
constrain sizing; a minimum too large for the risk budget rejects the opportunity.

Wide-cost stress increases fees1.5x, spread2x and slippage to3bps per side. Friction stress delays
entries by one15m bar, fills half size and deterministically misses one quarter of eligible IDs.
These are declared sensitivity scenarios, not empirically calibrated fill probabilities.
All variants fully re-simulate portfolio slot contention. Stop wins an ambiguous OHLC bar.
Closed-bar decisions execute at the next available open. Intrabar fill timestamps remain unknown.

## Family decisions

- **rsi_reversion — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: RSI_8, RSI_8, RSI_8, RSI_8. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -3314.401840941418, 'delay_partial_missed': -871.6526141774654}.
- **time_series_momentum — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; drawdown gate failed; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: TSM_48, TSM_48, TSM_48, TSM_48. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -22610.761009982016, 'delay_partial_missed': -8839.346879869463}.
- **compression_breakout — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; drawdown gate failed; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: BREAK_48, BREAK_48, BREAK_48, BREAK_48. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -5178.8825564605195, 'delay_partial_missed': -2054.973953494637}.
- **relative_strength — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; drawdown gate failed; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: REL_16, REL_16, REL_16, REL_16. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -20466.98238153408, 'delay_partial_missed': -9074.394630790639}.
- **basket_residual_reversion — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; drawdown gate failed; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: RESID_2.5, RESID_2.5, RESID_2.5, RESID_2.5. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -11964.292985732247, 'delay_partial_missed': -4696.791248424005}.
- **volume_shock — REJECTED**: negative aggregate validation economics; day-block bootstrap lower bound does not exceed zero; family-level multiplicity gate failed; fewer than3 positive validation folds; drawdown gate failed; execution/cost stress gate failed; reused legacy history and uncalibrated execution cannot supply fresh independent acceptance.
  Selected: VOLUME_3, VOLUME_3, VOLUME_3, VOLUME_3. Positive folds: 0/4; Holm p=1.0; stress net={'wide_costs': -17864.708830589778, 'delay_partial_missed': -7429.5565863158645}.

## Holdouts and next experiments

No final, sealed or prospective legacy payload was opened.
No candidate receives live or scientific acceptance. No candidates were promoted automatically.
Next: predeclare independent historical data and public prospective execution calibration.
BTC/ETH residuals, L2 imbalance, aggressive flow and funding-state features remain separate hypotheses
requiring their own justified data. The implemented residual family uses an equal-weight market basket.
