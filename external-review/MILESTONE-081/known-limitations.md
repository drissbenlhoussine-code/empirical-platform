# M081 - Known Limitations

1. **It is a ratio of arithmetic over assertions, not a measurement.** No broker,
   no confirmation, no reconciliation, and no evidence that any trade occurred or
   occurred at the stated price.
2. **It is not a return.** Not ROI, not profit percentage, not investment
   performance, not a market return, not a tax result. The unrepresented economic
   components below remain unrepresented in the ratio exactly as in M080.
3. **Economic components are unrepresented, in three groups with different
   epistemic status**, inherited verbatim from frozen M080: unrepresented
   cashflows (commissions, exchange and regulatory fees, financing and borrow
   cost) would normally reduce a raw result; context-dependent components (taxes,
   dividends, corporate actions) move it either way; and **spread and slippage
   are not claimed excluded at all** - the prices are the operator's own, so they
   may already be embedded, and nothing in the ledger can measure that.
4. **Two ratios are arithmetically comparable but not necessarily economically
   comparable.** Denomination cancels; economics does not.
5. **No aggregate of any kind is emitted** - no sum, mean, median, distribution,
   best, worst, or count of positive ratios. Section 17 of the design records why.
6. **No monetary value is emitted anywhere**, so the ratio cannot be audited from
   within M081. That is deliberate: run M080 for the money, where the denomination
   banner travels with it.
7. **A partial-exit ratio covers the exited quantity only.** Its denominator is
   the entry cost of exactly that quantity, and it says nothing about the eventual
   outcome of the quantity still open.
8. **`EXIT_QUANTITY_UNRECONCILED` positions do get a ratio**, computed over the
   visible exited quantity, carrying the unreconciled status and the unaccounted
   quantity on the same line. Withholding it was considered and rejected in design
   section 13; the reasoning is recorded there rather than hidden.
9. **No ratio exists for a position with no asserted exit.** Not zero, not `0%`,
   not break-even, not flat - an explicit absence with a reason.
10. **The exact reduced rational is the authoritative value.** Any decimal shown
    is an approximation to six places, truncated toward zero and prefixed `~` when
    inexact. A ratio need not terminate in decimal form.
11. **No annualization and no time-weighting.** Holding period is not represented
    at all, so two ratios say nothing about which was achieved faster.
12. **No currency and no denomination**, inherited from M080 and re-stated:
    M076 persists no currency, `instrument_symbol` is not a currency authority,
    and no value may be read as USD, EUR or anything else on this milestone's
    authority.
13. **Only positions the operator chose to record are visible at all**, so no
    statement about typical or expected outcomes may be built on this report. M081
    emits no aggregate partly for this reason.
14. **`recorded_at` is operator-supplied, not a system clock** - M079's own frozen
    limitation, inherited unchanged and not re-litigated here.
15. **Quantities are integers**, because frozen M076 types them so; fractional
    share positions are unrepresentable by the ledger, not by M081.
16. **No index on `recorded_at`**; filtering is in memory through the existing
    `list_all()`, exactly as M077 through M080 do. A deliberate deferral.
17. **No cross-position fold**, so M081 detects no incoherence between positions -
    only what M080 already detects within each key.
18. **Pre-existing and untouched:** the M062/M064/M065 CRLF seal debt.
