# M080 — Known Limitations

1. **Every figure is arithmetic over assertions, not a measurement.** There is no
   broker, no confirmation, no reconciliation, and no evidence that any trade
   occurred or occurred at the stated price.
2. **All costs are excluded** — commissions, spread, slippage, exchange and
   regulatory fees, taxes, dividends, corporate actions and financing cost. M076
   stores none of them. Every result is therefore **systematically more
   favourable** than a real economic outcome.
3. **No unrealized figure is computed** for a still-open quantity, because the
   platform holds no authoritative current market price. A partly-exited
   position's result covers the exited quantity only and is never extrapolated.
4. **No aggregate, percentage or win rate is emitted.** Each is a performance
   claim this milestone has no authority to make. A reader wanting a portfolio
   figure must not construct one from these entries without recognising that
   they omit costs and open exposure.
5. **`EXIT_QUANTITY_UNRECONCILED` is common at early cutoffs and is not
   corruption.** M076 derives a `CLOSED` event's quantity at append time from the
   full history, so a knowledge-filtered prefix can fold coherently while its
   visible exits do not account for the opened quantity.
6. **M080 does not diagnose an unresolved sequence.** As in M079, it cannot know
   from a single cutoff's evidence whether a non-folding prefix is temporary
   incompleteness or ledger incoherence, and it declines to guess.
7. **`recorded_at` is not enforced as a system clock.** The shipped CLI stamps it
   with `datetime.now(UTC)` and offers no override, but the usecase and domain
   accept any timezone-aware value, so nothing *guarantees* it. An operator
   writing through a programmatic path can back-date it and defeat the firewall
   undetectably. This corrects M079's frozen limitation 8, which stated the
   weaker claim flatly; M079's document is not edited.
8. **Lineage is reported, never validated.** A cited plan id is what the operator
   recorded. M080 makes no claim that the position belongs to any research
   session — that is M078's authority — and does not check that the plan exists.
9. **Both cutoffs are required and the answer depends entirely on them.** There
   is deliberately no default on either dimension.
10. **The ledger is the only source.** Activity never recorded is invisible at
    every cutoff, and M080 cannot distinguish "did not happen" from "was never
    written down".
11. **No index on `recorded_at`.** Filtering is in memory through the existing
    `list_all()`, exactly as M077, M078 and M079 do. A deliberate deferral,
    inherited from M079.
12. **A whole-ledger fold is not used**, so M080 does not detect incoherence
    *between* positions — only within each key. This is the per-key resilience
    M079 established, and its cost is stated rather than hidden.
13. **Quantities are integers.** M076 types `quantity` as `int`, so fractional
    share positions cannot be represented at all — by the frozen ledger, not by
    M080.
14. **Pre-existing and untouched:** the M062/M064/M065 CRLF seal debt.
