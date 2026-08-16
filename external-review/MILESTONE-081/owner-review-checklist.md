# M081 - Owner Review Checklist

## The judgment calls, stated so you can overrule them

| # | Call | What I chose, and why |
|---|---|---|
| 1 | **Reject candidate A (denomination authority)** | No instrument-level quote-currency authority exists anywhere. `InstrumentMaster` - the natural place - has none. M067's `currency` denominates a *simulated study's capital policy*, not an operator's asserted execution price, and is not joinable to an M076 event. Building A would mean inventing the authority or amending frozen M076. **If you believe a currency authority should be introduced, this is the decision to overrule.** |
| 2 | **Reject the R-multiple denominator** | M060 sizing amounts are denominated in supplied *account-equity* units; nothing establishes those are the same units as the ledger's asserted prices, so the division would produce a number that *looks* dimensionless and is not. Plus: planned quantity is not asserted quantity, and several positions may cite one plan. |
| 3 | **Emit no aggregate at all** | Even of dimensionless values. Averaging would weight a one-unit exit equally with a ten-thousand-unit exit; value-weighting would require summing money across unspecified denominations. **If you want a calibration statistic, that is M082 and it needs its own population argument.** |
| 4 | **Emit no monetary value at all** | Stronger than "no aggregate": no field is named, typed or labelled as money, so there is nothing monetary to sum. Costs auditability *within* M081 - a reader must run M080 to see the money. ⚠ *Corrected after Owner finding 2:* this row previously justified the call by saying the reduced rational "actively destroys the magnitude" — **retracted**, because coprime scaled operands survive reduction unchanged. The call stands on **semantic** grounds; it was never a confidentiality guarantee. |
| 5 | **Give `EXIT_QUANTITY_UNRECONCILED` a ratio** | Over the visible exited quantity, with the unreconciled status and unaccounted quantity on the same line. Withholding it would make M081 less informative than M080 exactly where a reader most needs the shortfall. Attacked both ways in design section 13. |
| 6 | **Never render a percentage** | A `%` reads as a return. The value is a rational. |
| 7 | **Truncate the approximation toward zero** | Not `ROUND_HALF_EVEN`. Truncation guarantees the approximation never shows a magnitude the exact value cannot reach - which is what defect R01 was. |

## What to check

| # | Check | Where |
|---|---|---|
| 1 | The ratio is dimensionless by *exact* cancellation, not by assertion | design section 8; `test_the_mandated_lifecycle_yields_the_exact_reduced_ratio` |
| 2 | The denominator can never be zero | proved from frozen M076's `asserted_price > 0`; `test_the_denominator_is_always_strictly_positive` and `test_m076_rejects_the_prices_that_would_make_the_bound_reachable` |
| 3 | The ratio is strictly `> -1`, always | `test_the_ratio_is_always_strictly_greater_than_minus_one`, plus 500 randomized cases |
| 4 | The boundary approximation never prints the unreachable `-1` | `test_the_boundary_approximation_never_renders_the_unreachable_minus_one` |
| 5 | No `Decimal` or float touches the ratio | `test_the_module_never_builds_a_float_or_a_decimal_for_the_ratio`; 7 precisions x 3 rounding modes |
| 6 | A partial exit uses the **exited-quantity** denominator | `test_a_partial_exit_uses_the_exited_quantity_denominator_not_the_whole_position`; the mandated `1` vs `1/10` case, also against PostgreSQL |
| 7 | An open position gets no ratio, no zero, no break-even | `test_an_open_position_gets_no_ratio_and_no_zero` |
| 8 | No monetary value anywhere | `test_no_monetary_value_appears_anywhere_in_the_report` |
| 9 | No aggregate of ratio values | `test_the_report_exposes_no_aggregate_of_ratio_values` |
| 10 | Cross-denomination positions are never combined | `test_two_positions_of_unknown_denomination_are_never_summed`, unit **and** PostgreSQL |
| 11 | The M079 firewall is inherited, proved across two databases | `test_two_databases_identical_up_to_k_agree_on_every_m081_output` |
| 12 | 24 forbidden tokens absent from every closed vocabulary | `test_no_forbidden_token_appears_in_any_closed_vocabulary`, word-boundary matched |
| 13 | Ordering is by identity, never by value | `test_entries_are_ordered_by_identity_and_never_by_ratio_value` |
| 14 | Frozen M075-M080 untouched | `git diff --name-only 43eb2c3 HEAD` |
| 15 | R01, R02 and my ten wrong probe assertions are recorded, not hidden | `hostile-implementation-review.md` |
| 16 | A non-zero ratio below `10^-6` never loses its sign | `test_a_negative_ratio_below_the_approximation_scale_keeps_its_sign`; positive and negative tiny ratios render as **distinct** bounds |
| 17 | No claim of monetary non-recoverability survives anywhere | swept branch-wide; the coprime counterexample is asserted by test |

## What I would push back on if you asked for it

- **Adding a currency by inference from symbol or exchange.** There is no
  authority for it, and M080's freeze forbids exactly this.
- **An average ratio.** It would be a performance statistic over a population
  the operator self-selected.
- **Calling this a return in the UI while keeping the honest field name.** The
  field name is the contract; a friendlier label would defeat it.
