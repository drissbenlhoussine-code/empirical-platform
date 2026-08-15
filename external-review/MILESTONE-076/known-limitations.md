# M076 — Known Limitations

1. **Operator-asserted, not verified.** Every value is what the human said. There is no
   broker, no confirmation, and no reconciliation. The banner says so in both renderings.
2. ~~**No concurrency lock.**~~ **RESOLVED by the owner correction pass.** Validation and
   insertion are now atomic under a transaction-scoped `pg_advisory_xact_lock` keyed on the
   position id, proven by four real concurrency attacks. Writers to different positions
   still proceed in parallel.
3. **Symbols are not validated against `instrument_master`.** Deliberate: the ledger
   stands alone rather than coupling to M057/M064 data.
4. **Asserted prices are limited to six decimal places**, matching the persisted
   `NUMERIC(20, 6)`. Anything finer is rejected rather than silently rounded, so an
   accepted value always reloads identically.
5. **Timestamps must be timezone-aware.** Naive datetimes are rejected at the domain
   boundary rather than persisted into a `TIMESTAMPTZ` column with an assumed zone.
6. **No P&L, no market valuation.** `asserted_open_notional` is quantity × asserted entry
   price, and nothing revalues it.
7. **Not consumed by M075 yet.** Wiring this into same-day capital feasibility would change
   M075's frozen meaning. That is M077's job — recommendation only, not started.
8. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt. M076 introduces no
   fixture and no byte seal, so it is unaffected and was not repaired.
