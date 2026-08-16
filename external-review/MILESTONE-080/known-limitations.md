# M080 — Known Limitations

1. **Every figure is arithmetic over assertions, not a measurement.** There is no
   broker, no confirmation, no reconciliation, and no evidence that any trade
   occurred or occurred at the stated price.
2. **Economic components are not represented**, so a result is **NOT a complete
   economic outcome**. They fall into three groups, which must not be collapsed:
   - *Unrepresented cashflows* — commissions, exchange and regulatory fees,
     financing and borrow cost. The ledger records none of them; including them
     would normally **reduce** a raw result.
   - *Context-dependent components* — taxes, dividends, corporate actions. These
     can move the real outcome in **either** direction.
   - *Not separately attributable execution components* — spread and slippage.
     M080 does **not** claim these are excluded. The arithmetic runs on the
     operator's own asserted execution prices, so any spread or slippage may
     already be embedded in them; M076 stores no benchmark, quoted, intended or
     arrival price, so there is nothing to measure an execution effect against
     and M080 cannot tell whether they are absent, embedded or partly embedded.

   Because the groups differ in direction, **the direction of the total omitted
   effect is not generally knowable** and no universal bound is claimed.

   > ⚠ *Corrected after Owner review (finding 2), then again (finding 4).* This
   > item first said all of these are costs and that every result is
   > "systematically more favourable" than reality — **false**. The first
   > correction then grouped spread and slippage with directional frictions and
   > said their omission "would normally make a raw result look better than
   > reality" — **also too strong, and retracted.** The three-way split above is
   > the current statement.
3. **No unrealized figure is computed** for a still-open quantity, because the
   platform holds no authoritative current market price. A partly-exited
   position's result covers the exited quantity only and is never extrapolated.
4. **No aggregate, percentage or win rate is emitted.** Each is a performance
   claim this milestone has no authority to make. A reader wanting a portfolio
   figure must not construct one from these entries without recognising that
   they leave economic components unrepresented, leave open exposure out, and
   carry no established denomination (see 16).
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
15. **Exactness is guaranteed by integer arithmetic, not by a Decimal context.**
    ⚠ *Added after Owner review.* The original implementation multiplied under
    the ambient `Decimal` context and rendered through `normalize()`, so at the
    maximum persistence-valid quantity (`2147483647`) against the maximum price
    it silently lost six digits and depended on the caller's precision and
    rounding mode. All monetary arithmetic is now carried in Python integers
    scaled to 10⁻⁶ — exact by construction, and context-free. The guarantee
    rests on frozen M076 capping the price scale at six decimal places; if that
    cap ever changed, `_scaled_price` raises rather than rounding silently.
16. **There is no currency or denomination authority.** ⚠ *Added after Owner
    review (finding 3).* M076 persists `instrument_symbol`, `quantity`,
    `asserted_price`, two timestamps, an optional plan citation and a note — and
    **no** currency column of any kind. Every value M080 emits is therefore in
    the same **unspecified asserted price units** the ledger carries.
    `instrument_symbol` is not a currency authority. No value here may be read as
    USD, EUR or any other currency on M080's authority, and two values must not
    be assumed to share a denomination merely because both appear in one report.
    M080 invents no currency value, adds no column and adds no migration.
