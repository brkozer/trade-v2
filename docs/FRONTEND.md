# Evidence workstation

Run `.venv/Scripts/python -m uvicorn tradev2.api.server:app --host 127.0.0.1 --port 8000` from the project root. In `frontend`, run `npm ci` then `npm run dev`. Vite proxies `/api` to the loopback API. Keep both servers local; the API is an unauthenticated local read service, not a public deployment.

Six navigable pages cover Trader, Alpha Lab, Symbols, Experiments, Performance and System. Manual refresh and 15-second polling load one composite response with cancellation on mode changes. Failed refreshes remove old values. Missing money is amber Unknown, never zero. Exact decimal strings are displayed without numeric conversion; the equity plot alone uses approximate screen coordinates with source values available in its disclosure.

The API reads only fixed target artifacts: `runtime/{paper|shadow}/*/journal.sqlite` and `research/results/campaign.json`. It selects the most recently modified journal for a mode or accepts a validated `run_id`; it never combines accounts across runs. Journal hashes are verified before displaying evidence, readers observe WAL through `mode=ro`, and runtime freshness is recalculated at request time (30 seconds). Integrity is not a current safety claim. Event lists are bounded at 1,000 per kind; displayed counts describe that observation window, not lifetime totals.

`/api/v1/workstation` provides the typed composite contract. Individual resources are runtime, account, positions, orders, trades, symbols, opportunities, decisions, rejections, experiments, searches, candidates, performance, evidence-health, system-health and run-manifests. All are GET-only. There is no live/testnet control, mutation, credentials, or browser SQLite access. OpenAPI is available at `/docs`.

Unknown attribution, fee tiers, protection and reconciliation are explicitly unavailable unless source evidence supplies them. Candidate detail disclosures preserve OOS results, stress tests, costs, reasons and search methodology; rank never implies acceptance. Paired experiments are not inferred from candidate rankings.

Semantic navigation, native buttons/disclosures, captioned tables, visible focus, a skip link, responsive layout, and reduced-motion rules support evergreen browsers. React uses one fetch stream per view and no chart dependency. Validate with `npm run build`, `npm test`, and backend API tests. Browser and screen-reader audit are separate from component tests.
