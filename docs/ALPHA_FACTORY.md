# Alpha Factory

Six distinct mechanisms have three declared configurations each: RSI reversion,
time-series momentum, compression breakout, cross-sectional relative strength,
market-basket residual reversion and directional volume shocks. The basket is an
equal-weight return index of the available universe; it is not a BTC proxy claim.
OHLCV does not supply aggressive order flow or queue position.

`python -m tradev2.alpha.campaign --freeze` writes a one-time preregistration that
binds source code, dataset, economics, budget, selection rule and evidence gates.
Commit it before `python -m tradev2.alpha.campaign`. The latter creates an exclusive
consumption marker before evaluating outcomes. A failed or interrupted search is
consumed and must remain visible; never delete its marker to retune and retry.

The initial campaign uses 18 configurations, 72 expanding-window training
evaluations, 24 selected chronological validations and 48 independent stress
replays. All training trials, negative outcomes and rejection counts remain in
`research/results/campaign.json`. Large opportunity and trade ledgers stay in the
ignored target data directory with hashes in the tracked result.

Money, sizing, fee, funding and cash ledger arithmetic use Decimal; feature arrays
and aggregate statistical presentation use float64. Fees are charged taker on
both sides. Spread, slippage, delay, missed fills and partial size are explicit
sensitivity assumptions, not calibrated claims. Each stress arm fully replays
portfolio competition and pairs the common opportunity identities.

No initial result is automatically scientifically accepted: the legacy data is
already consumed. Positive historical gates would still be INSUFFICIENT until
independent evidence and prospective execution calibration exist. Live remains
disabled. The reference candidate remains an engineering parity fixture.
