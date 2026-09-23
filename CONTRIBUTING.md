# Contributing

Develop on a branch and open a pull request into `main`. Keep commits cohesive and
include actual validation results. Never commit runtime databases, raw market data,
credentials, or machine-local outputs. Scientific results must state dataset provenance,
search budget, chronological boundaries, costs and limitations. Preserve failed trials.

For a new search, freeze and commit its manifest before results are observed. A
crashed attempt remains consumed; a corrected attempt needs a new identity and
must disclose prior evaluations. A family with the best rank but failed net-cost
gates is rejected, not promoted. Keep legacy sources read-only and all generated
state inside Trade v2. Run backend tests, Ruff, mypy, artifact scan, frontend tests
and build before requesting review. Never weaken `LIVE_DISABLED` in routine work.
