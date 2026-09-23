# Execution kernel

The kernel performs Decimal arithmetic and has no exchange transport. `assess` returns
ALLOW, RESIZE, REJECT or HALT and includes cost allowance in stop risk. Open and pending
risk consume the same portfolio budget. Directional and correlated exposure passed in
the portfolio snapshot must be measured for the candidate's side and correlation group.
Margin, maximum size and exposure constraints all cap quantity before lot flooring;
exchange minima never increase quantity. Unknown account facts halt new risk.
Optional per-symbol notional caps apply to existing symbol exposure. Rolling correlation
buckets use aligned historical returns available as of the decision, absolute Pearson
correlation, and conservatively include missing/constant/insufficient peer series. Callers
sum exposures from this bucket into the risk snapshot; defaults require 30 observations
and use a 0.7 absolute-correlation threshold.

Client IDs deterministically bind owner, decision, symbol, side and reduce-only intent.
A decision identity must never be reused for a revised order: revisions need new decision
identities. An owned fill requires matching client ID, side and symbol. Repeated execution
IDs are idempotent; contradictory repeats fail. Cancel requests and mismatched cancel
observations retain uncertainty. Late fills are adopted and require protection. Entry
fills must occur strictly after signal availability, never at the revealing close.
The lifecycle explicitly records CREATED, SUBMITTED, ACKNOWLEDGED, RESTING,
PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, REJECTED, EXCHANGE_ENDED,
SIGNAL_INVALIDATED, PRICE_LEFT, UNPLACED and UNRESOLVED. Acknowledgement never fills;
signal invalidation and price departure retain unresolved order responsibility.

Position management continues until flat is proven. Reduce-only exits must match owner,
symbol, opposite side and remaining quantity. Position protection reports unhealthy when
confirmed protected quantity is below exposure. Exit acknowledgement does not imply flat.
Reconciliation is a pure reducer over an immutable original position and its complete exit
execution set. Always replay from that original baseline; duplicate rows are deduplicated,
foreign identities and excess coverage rejected, and a complete fresh position snapshot
must agree exactly before remaining quantity changes. Callers persist the baseline and
events; this package itself is in-memory and makes no durability claim.

`reconciliation/snapshot.py` compares complete dated account, orders, executions,
positions and closed-PnL observations against journal state. Missing coverage,
duplicate IDs, ownership mismatches, unknown money components, unprotected
positions or account disagreement block entry. The generic startup gate separately
requires authority, identity, metadata, fees, recovered journal, freshness and
protection. Neither HTTP acknowledgement nor an empty stale snapshot proves flat.

Ledger amounts retain source and source time. Unknown and estimated fees/funding cannot
produce canonical net PnL. Known zero is explicit. Net PnL is gross minus entry/exit fees
plus signed funding. Duplicate immutable ledger events do nothing; conflicts fail. Later
corrections require a distinct evidence event instead of overwriting historical evidence.
