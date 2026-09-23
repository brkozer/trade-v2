# Security and capital boundary

Live trading is hard disabled. No real order creation, cancellation, position modification,
fund transfers or withdrawals are authorized. Production authenticated hosts must never
be arbitrary user URLs. Research, paper and shadow need no private exchange credentials.

Secrets belong in explicitly referenced environment variables for a future authorized
testnet boundary. Never paste secrets into reports or issues. Report vulnerabilities
privately to the repository owner. Do not include credentials in reproduction evidence.

Dedicated testnet operation additionally requires `TRADEV2_TESTNET_ENABLE=1`,
testnet-only key/secret environment variables, a testnet-mode config with explicit
authorization, account-scoped local authority and all startup proofs. The transport
has a fixed testnet host and allowlisted endpoints. A successful REST response is
only an unresolved acknowledgement; it never establishes a fill or safe flatness.
Do not restore ownership from a prefix alone without independent journal and
exchange reconciliation. The current local lock cannot protect across hosts.

The operator API is local and read-only. It must not expose exchange mutation controls.
