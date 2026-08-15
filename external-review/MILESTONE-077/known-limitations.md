# M077 — Known Limitations

1. **Held exposure is operator-asserted, not verified.** Every held figure comes
   from M076, which records what the operator said. There is no broker, no
   confirmation and no reconciliation. The banner says so in both renderings.
2. **The asserted entry price is not a market price.** Held notional is
   quantity × the price the operator asserted at entry, and it is **never
   revalued** — not by a later reduction's cited price, and not by anything
   else. It is not a market valuation, not a cost basis, and not P&L.
3. **Capital is measured as utilisation, not as a cash balance.** Charging held
   notional against the capital base does not claim the operator's cash went
   down; it measures how much of the base is deployed, which is M067's own
   frozen model.
4. **Held and proposed exposure share one capital base whose provenance
   differs.** The base is the equity today's plans were sized against; the held
   positions were asserted at other times against no recorded equity figure.
   The alternative would be inventing a second capital authority that does not
   exist in the repository.
5. **The snapshot is anchored to the session's `as_of`, not to wall-clock now.**
   Any other anchor would make the brief non-reproducible.
6. **A plan cited by a *closed* position is not excluded.** A closed position
   released its exposure, so re-entering is legitimate. Only positions open at
   `as_of` suppress a plan.
7. **A database-level failure reading the ledger propagates** rather than being
   reported as `LEDGER_UNAVAILABLE`. Bad *data* is caught and withheld; a broken
   *database* is not disguised as a soft verdict.
8. **No per-instrument concentration control.** M067's policy has no such cap,
   and M068's dependence evidence is historical — using it operationally is an
   explicit non-goal.
9. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt. M077
   introduces no fixture and no byte seal, so it is unaffected and was not
   repaired.
