# Aborted completion-search attempt 002

`TRADEV2_FINAL_ALPHA_002` was preregistered and consumed on 2026-09-23 UTC.
It used the 39-symbol reused-history panel. The unchanged trend-persistence
factor completed four nested folds, requiring 24 replay evaluations (eight
inner selection, four forward, four neighbor, eight stress). The selected
forward paths had 1,135 / 817 / 736 / 1,583 trades and net USDT
-2,756.63 / -2,732.67 / -2,112.37 / -2,478.79, respectively.

The run then failed before persisting the family checkpoint: a NumPy boolean
in `selection_eligible` was not JSON serializable. The exclusive consumption
marker was already written, so this attempt is **not rerun or relabeled**.
No final result artifact, statistical acceptance, or promotion was produced.

Attempt 003 retains the identical dataset, factor/ML grids, chronological
windows, costs, selection metric, multiplicity rule and promotion gates.
Its only research-engine change converts NumPy scalar values to native JSON
scalars when persisting evidence. The new preregistration discloses this
abort and its 24 evaluations so the total search footprint remains visible.
