# Bounded source discovery

Before implementation, local branch, status, HEAD and authoritative GitHub `main` were
compared for both references. The exact revisions and preexisting untracked Aegis
`reports/` are in [SOURCE_MANIFEST.md](SOURCE_MANIFEST.md). Neither reference was cloned,
modified, installed into, tested in, cleaned, stashed, switched or committed.

Discovery followed relevant paths and history rather than copying either tree. For
AegisQuant, the existing Graphify output, paper API/account, dashboard package and
health/shadow commits supplied UI and evidence concepts. For the Bybit prototype,
precision/risk, fee/funding accounting, reconciliation, and late-fill tests supplied
invariants and counterexamples. [AEGIS_DISCOVERY.md](AEGIS_DISCOVERY.md) and
[BYBIT_DISCOVERY.md](BYBIT_DISCOVERY.md) contain path and commit details.

Public historical OHLCV and funding files from the Bybit reference were read as
evidence, never copied into Git. Their provenance and reuse status are explicit in
the preregistration and campaign artifacts. Private account records, credentials,
runtime databases, and any sealed/final holdout were excluded. The six-family campaign
was registered before execution and consumed once. Every family failed acceptance;
negative results remain immutable evidence, not a reason to relabel validation data.

The target is an independent implementation with shared typed boundaries. The map in
[SOURCE_TO_TARGET_MAP.md](SOURCE_TO_TARGET_MAP.md) links reference decisions to concrete
target modules; [REJECTED_LEGACY_PATTERNS.md](REJECTED_LEGACY_PATTERNS.md) lists the
legacy behavior intentionally left behind.
