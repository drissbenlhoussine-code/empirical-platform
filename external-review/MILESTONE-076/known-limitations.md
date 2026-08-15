# M076 — Known Limitations

1. **Operator-asserted, not verified.** Every value is what the human said. There is no
   broker, no confirmation, and no reconciliation. The banner says so in both renderings.
2. **No concurrency lock.** The unique constraint prevents duplicate events, but two
   *different* logically-conflicting events submitted simultaneously could interleave.
   This is a single-operator CLI primitive; a lock is not justified at this scope.
3. **Symbols are not validated against `instrument_master`.** Deliberate: the ledger
   stands alone rather than coupling to M057/M064 data.
4. **No P&L, no market valuation.** `asserted_open_notional` is quantity × asserted entry
   price, and nothing revalues it.
5. **Not consumed by M075 yet.** Wiring this into same-day capital feasibility would change
   M075's frozen meaning. That is M077's job — recommendation only, not started.
6. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt. M076 introduces no
   fixture and no byte seal, so it is unaffected and was not repaired.
