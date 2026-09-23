# Bounded Bybit execution discovery

Source: `bybit-prototype`, SHA `e136564ed488a63c7f55d800d2a598bfc40ab497`.
Root provenance discovery verified this against authoritative main. All discovery was
read-only; no source imports, installers, tests or runtime data were used.

| Source evidence | Decision | Target adaptation |
| --- | --- | --- |
| `v4bot/risk.py` `_lot_size`, budget metadata | ADAPT | Decimal-only quantity, explicit risk decisions and pending reservations |
| `v4bot/precision.py` `floor_to_step` | ADAPT | Decimal floor sizing; reject off-grid prices rather than silently alter stop risk |
| `v4bot/accounting.py` fee and funding provenance | ADAPT | Typed nullable Amount, explicit zero/estimate/unknown, immutable events |
| `v4bot/reconciliation.py` exact size coverage principle | REWRITE | Exact owned execution identity and fresh snapshot proof, no float tolerance |
| `tests/test_unresolved_late_fill.py` uncertainty regression | ADAPT | Pure reducer cancel/late-fill regression without authenticated REST |
| Source live transport and monolithic engine coupling | REJECT | No authenticated transport or imported engine; bounded kernel interfaces |

Relevant read-only path history included `a5830fc` (paper fee-tier correction),
`9e75e18` (walk-forward negative evidence), `2735b6a` (funding regime), `d86696a`
(exchange stop reconciliation cooldown), and `ab4e1cc` (exit-policy hypothesis).
This history motivates preservation of negative evidence and unknown costs; it supplies
no claim of tradable alpha. No source private account records or sealed data were copied.
