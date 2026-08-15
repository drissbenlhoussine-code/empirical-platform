# M079 — Known Limitations

> **Updated after Owner review.** Items 3 and 4 changed substantively: M079 no
> longer classifies an unfoldable sequence as "incomplete" versus "incoherent",
> because that classification read evidence recorded after the cutoff. Item 13
> is new and is a direct cost of the correction.

1. **`KNOWN_OPEN` means known to the ledger, not known to be true.** Every
   figure is an operator assertion. There is no broker, no confirmation and no
   reconciliation.
2. **A snapshot can be superseded.** A position reported open at `K` may later
   prove to have been reduced or closed by an assertion recorded after `K`.
   That is not an error — it is what was known at `K`, and it is the reason the
   milestone exists.
3. **Unfoldable evidence is common and expected, and M079 does not diagnose it.**
   At an early knowledge cutoff a close or reduction may be visible while its
   opening is not. M079 reports `UNRESOLVED_KNOWLEDGE_SEQUENCE` and **infers
   nothing** — no quantity, no state, no "probable" answer, and deliberately **no
   verdict on whether the gap will later close**. Deciding that would require
   reading assertions recorded after the cutoff, which is the leak the milestone
   exists to prevent. A genuinely incoherent ledger and a merely truncated one
   are therefore *indistinguishable in the status*; M076's own rejection reason
   for the visible evidence is still reported and does differ between them.
4. **M079 cannot distinguish a late recording from a late event.** It reports
   both timestamps and the effective-cutoff exclusion count; interpreting *why*
   an assertion was recorded late is outside its authority.
5. **Both cutoffs are required and the answer depends entirely on them.** There
   is deliberately no default on either dimension, because a default would
   silently choose an epistemic stance.
6. **`knowledge_as_of` earlier than `effective_as_of` is permitted** and
   meaningful, but easy to misread; it is named in a limitation whenever used.
7. **The ledger is the only source.** Activity the operator never recorded is
   invisible at every knowledge cutoff, and M079 cannot distinguish "did not
   happen" from "was never written down".
8. **`recorded_at` is itself an operator-supplied value**, not a
   system-assigned immutable receipt time. M079 treats it as authoritative for
   availability because M076 defines it that way, and therefore claims only to
   report **what the ledger records as having been recorded** by the cutoff —
   not what was *actually* available. An operator who back-dates `recorded_at`
   defeats the firewall, and M079 cannot detect that.
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
13. **The snapshot cannot say how much it hid.** There is deliberately no count
    of assertions excluded by the knowledge cutoff and no total-ledger count,
    because both are functions of rows recorded after the cutoff and would leak
    exactly what the firewall exists to withhold. The limitation text says so on
    every snapshot rather than omitting the number silently.
14. **A later query may answer differently, and that is not a contradiction.**
    A sequence unresolved at `K` may fold at `K2`, or may stay unresolved. The
    later answer never reaches back and strengthens the earlier one.
