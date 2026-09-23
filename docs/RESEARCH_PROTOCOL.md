# Research protocol

Before examining outcomes, freeze hypothesis mechanisms, exact search budget,
parameters, causal features, candidate selection, execution assumptions and
acceptance gates. Record immutable content hashes and Git revision. Every failed
configuration and interrupted search counts toward research consumption.

The initial dataset is public legacy OHLCV covering 37 selected symbols. It is
explicitly REUSED_HISTORICAL_DISCOVERY, subject to universe survivorship and prior
research selection. No sealed legacy or final holdout is read. A fresh final
holdout is NOT_ACQUIRED_NOT_CONSUMED; chronological partitions do not erase prior
consumption. Use complete UTC days within common settled funding coverage.

Four expanding training windows select one of three configurations per family,
then replay its next 30 days without tuning. Each fold begins flat at 10,000 USDT,
so aggregate PnL is not a compounded account return. Training selection requires
50 trades and penalizes daily volatility. Features use closed bars only; earliest
execution is the next opening boundary. Same-bar stop/target ambiguity resolves
to stop first, with adverse opening gaps. Intrabar fill timestamps are unknown.

Circular seven-day blocks generate 2,000 bootstrap draws over daily portfolio
PnL; Holm adjusts six family path tests. Retain all 18 searched configurations
and the overlapping training-window warning. Gates require positive lower bound,
adjusted p <= .05, at least 200 trades across ten symbols and 90 days, at least
three positive folds, bounded drawdown and concentration, and positive stresses.
The initial experiment cannot satisfy the fresh independent evidence gate.

Reject missing or malformed funding coverage, dataset hash drift, gaps,
duplicates, nonfinite values and unsupported instruments. Never interpret missing
costs as zero. Funding uses actual settlement times with explicitly approximate
entry notional because historical mark prices are unavailable. Current venue lot
minimums and dated fee/spread observations are not historical rule time series.

Reproduction requires the hashed public inputs, frozen code and environment.
Run tests first, commit the preregistration, then execute the one-shot campaign.
Create a new search identity for any successor or correction; preserve the
original result and clearly disclose the relationship between searches.

The final search follows this rule: attempt 002 failed while writing a checkpoint
after 24 negative evaluations and remains consumed. Attempt 003 froze the same
grid, data, costs and gates with a scalar-serialization correction and disclosed
the prior work. Its 14 family paths were rejected. Its forward windows are
chronological but are **not** an untouched final holdout because the source history
was already used for research. The prospective recorder supplies the next source
of fresh evidence, subject to a new preregistration and enough observation time.
