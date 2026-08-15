# M079 — Known Limitations

1. **`KNOWN_OPEN` means known to the ledger, not known to be true.** Every
   figure is an operator assertion. There is no broker, no confirmation and no
   reconciliation.
2. **A snapshot can be superseded.** A position reported open at `K` may later
   prove to have been reduced or closed by an assertion recorded after `K`.
   That is not an error — it is what was known at `K`, and it is the reason the
   milestone exists.
3. **Incompleteness is common and expected.** At an early knowledge cutoff a
   close or reduction may be visible while its opening is not. M079 reports
   `INCOMPLETE_KNOWLEDGE_SEQUENCE` and **infers nothing** — no quantity, no
   state, no "probable" answer.
4. **M079 cannot distinguish a late recording from a late event.** It reports
   both timestamps and both exclusion counts; interpreting *why* an assertion
   was recorded late is outside its authority.
5. **Both cutoffs are required and the answer depends entirely on them.** There
   is deliberately no default on either dimension, because a default would
   silently choose an epistemic stance.
6. **`knowledge_as_of` earlier than `effective_as_of` is permitted** and
   meaningful, but easy to misread; it is named in a limitation whenever used.
7. **The ledger is the only source.** Activity the operator never recorded is
   invisible at every knowledge cutoff, and M079 cannot distinguish "did not
   happen" from "was never written down".
8. **`recorded_at` is itself an operator-supplied value.** M079 treats it as
   authoritative for availability because M076 defines it that way; it is not
   an independently attested receipt time.
9. **No money is derived.** Asserted prices and notionals are M076's own
   figures carried through unchanged. M079 computes no return, no P&L and no
   valuation, so it cannot tell you whether anything was worthwhile.
10. **A database-level failure propagates** rather than being reported as
    `LEDGER_UNAVAILABLE`. Bad *data* is withheld honestly; a broken *database*
    is not disguised as a soft verdict.
11. **No index on `recorded_at`.** M079 filters in memory through the existing
    `list_all()`, exactly as M077 and M078 do. At a much larger ledger this
    would warrant a query-side filter and an index — a deliberate deferral, not
    an oversight.
12. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt.
