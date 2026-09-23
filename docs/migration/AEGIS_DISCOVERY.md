# Bounded Aegis discovery

Reference SHA: `add466d3d56a7dee57174a68655e256ae965bdf5`, local HEAD matching remote main as verified in the source manifest. Source is read-only.

Read README architecture, existing `graphify-out/graph.json` node identities, `app/paper/api.py`, `app/paper/account.py`, frontend package manifest, and narrow paper/frontend history. Existing graph nodes identify paper API/account and execution families; no graph regeneration, HTML generation or source commands were run. The documented workflow is to use the existing graph first and narrow to concrete files, not invent a Graphify CLI.

Relevant history includes `75d7cd2` trader dashboard, `b0d9039` frontend health/refresh hardening, `6c88a28` operator health visibility, `84e2a3e` market-state fail-closed work, `7102026` long-soak synchronization, and `e9446db` shadow campaign preparation. These establish the value of explicit freshness, provenance and simulation scope without importing historical acceptance claims.

Adapted concepts: React/Vite typed read-only console; exact decimal strings at API boundaries; deterministic research/risk/execution separation; immutable journal evidence; paper and public shadow mode isolation; explicit operator health. The independent API exposes target artifacts rather than depending on Aegis services or storage. Aegis cash/long-only account assumptions are not valid Bybit Linear accounting and were not copied. Source control-plane lifecycle mutations, historical run databases, claims of alpha, and runtime state were not carried over.

The target dashboard deliberately preserves missing funding, protection, reconciliation and attribution as unknown. A historical verified journal cannot establish current safety. Detailed campaign evidence is shown without presenting in-sample rankings as accepted alpha.
