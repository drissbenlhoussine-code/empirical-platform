# M080 — Focused Re-Review After Corrections

The single correction was re-attacked in its changed area only.

## R01 — the result line's coverage

| Re-attack | Result |
|---|---|
| Do the three statuses now produce three distinct lines? | Yes — asserted by `test_the_three_coverage_phrasings_are_distinct` |
| Does the fully-exited line still read cleanly? | Yes — `on all 10 exited unit(s)` |
| Does the partial line name what it excludes? | Yes — `6 still open and NOT covered` |
| Does the unreconciled line deny being the whole result? | Yes — `NOT the whole position's result` |
| Did the change alter any computed value? | No — rendering only; every arithmetic assertion unchanged |
| Did the change alter the JSON? | No — JSON already carried the structured quantities beside the result |
| Does the renderer still import cleanly under `mypy`? | Yes — one added import of `RoundTripStatus` |
| Do the four regression tests fail against the pre-fix renderer? | Yes — that is what makes them regression tests |
| Did any existing test change meaning to accommodate the fix? | No — the four are additions |

## The test correction

| Re-attack | Result |
|---|---|
| Was the original assertion wrong, or the renderer? | The assertion — it matched the report title line |
| Is the corrected assertion now anchored? | Yes — `line.startswith("      ASSERTED ROUND-TRIP RESULT")` |
| Could it match the title again? | No — the title is not indented |
| Are there other unanchored substring assertions in the suite? | Audited; the remaining `in` assertions target phrases that appear in exactly one place, and the two forbidden-token tests deliberately scan every surface |

## Whole-suite confirmation after the correction

| Suite | Result |
|---|---|
| M080 unit | 58 passed |
| M080 PostgreSQL integration | 12 passed |
| M080 second pass | 4 passed |
| M076–M080 chain | 364 passed |
| Full regression | failing-ID set identical to the `0e73e0b` baseline |

---

# Owner review correction — focused re-review

Both corrections re-attacked in their changed areas only.

## Finding 1 — exact scaled-integer arithmetic

| Re-attack | Result |
|---|---|
| Does any `Decimal` operation remain in the arithmetic path? | No — `_entry_for_key` asserted free of `Decimal(`, `.normalize(`, `.quantize(`, `.scaleb(` |
| Does any remain in rendering? | No — `_money_from_scaled` is `divmod` and string formatting |
| Is global Decimal state mutated, or `prec` raised? | No — the module contains no `getcontext()` call |
| Is `_scaled_price` itself context-free? | Yes — it reads `as_tuple()`, which is pure data, and scales by appending zero digits |
| What if a future M076 widened the price scale past 6? | `_scaled_price` **raises** naming the invariant rather than rounding silently |
| Is the canonical rendering still identical to M076's for values both express? | Yes — trailing zeros stripped, no point when the fraction is empty, no exponent form; every pre-existing rendering assertion still passes unchanged |
| Is negative zero still possible? | No — now impossible by construction, since the sign comes from an integer. The old defensive guard is gone because it cannot be reached |
| Did any previously-passing arithmetic assertion change value? | No — all 58 original unit tests pass unmodified |
| Did the fix alter the firewall, statuses or counts? | No — only monetary computation and rendering |

## Finding 2 — economic-component vocabulary

| Re-attack | Result |
|---|---|
| Does any surface still call the whole list costs? | No — banner, limitations, text, JSON key and field names all checked |
| Does any universally-favourable-bias claim survive? | No — four phrasings checked, including "upper bound" |
| Do the two groups partition the list exactly? | Yes — union equal, intersection empty, asserted |
| Is the friction direction still stated, where it *is* knowable? | Yes — frictions "would normally reduce a raw result" |
| Were the original honesty guards weakened by the rewording? | No — 13 forbidden tokens and six banner disclaimers re-asserted at the boundary case |
| Was the API renamed rather than aliased? | Renamed. An alias would have preserved the misleading name in the frozen contract |

## Whole-suite confirmation after both corrections

| Suite | Result |
|---|---|
| M080 unit | **78 passed** |
| M080 PostgreSQL integration | **15 passed** |
| M080 fresh second pass | **4 passed** |
| M076–M080 chain | **387 passed** |
| Full regression | failing-ID set identical to the `0e73e0b` baseline |
