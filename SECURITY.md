# Security and capital boundary

Live trading is hard disabled. No real order creation, cancellation, position modification,
fund transfers or withdrawals are authorized. Production authenticated hosts must never
be arbitrary user URLs. Research, paper and shadow need no private exchange credentials.

Secrets belong in explicitly referenced environment variables for a future authorized
testnet boundary. Never paste secrets into reports or issues. Report vulnerabilities
privately to the repository owner. Do not include credentials in reproduction evidence.

The operator API is local and read-only. It must not expose exchange mutation controls.

