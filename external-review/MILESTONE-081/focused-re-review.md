# M081 - Focused Re-Review After the R01 Correction

Only the changed area, re-attacked.

## What changed

`_decimal_approximation` moved from `ROUND_HALF_EVEN` to **truncation toward
zero**, and inexact renderings gained a `~` prefix. Nothing else was touched -
not the exact rational, not the reduction, not the statuses, not the firewall.

| Re-attack | Result |
|---|---|
| Does the boundary still render a bare `-1`? | **No** - `~-0.999999` |
| Is `float()` of that value still exactly `-1.0`? | Yes - which is precisely why the rendering must not follow it |
| Can the approximation ever exceed the exact magnitude? | **No** - truncation toward zero guarantees `\|approx\| <= \|exact\|`; asserted over 200 randomized cases plus the boundary |
| Did the exact value change for any input? | No - the exact rational is computed before any rendering and was untouched |
| Did any previously-passing assertion change value? | No - the full unit suite passes unmodified apart from the new R01 regressions |
| Is the `~` prefix present exactly when inexact? | Yes - asserted both ways |
| Does `~` leak into the exact value? | No - `ratio_exact` never carries it |
| Does the text renderer still mark approximations distinctly? | Yes - `(APPROXIMATE)` |
| Is the rounding policy stated in the artifact? | Yes - the limitation says "truncated toward zero" and why |
| Is the policy stated in the code? | Yes - the docstring records the defect and the reason for choosing truncation over half-even |
| Any `Decimal` or float reintroduced? | No - integer `divmod` only |
| Does the change touch the M079 firewall? | No - re-asserted, 13 temporal attacks pass |
| Does it touch money absence? | No - re-asserted, 12 attacks pass |
| Does it touch aggregation refusal? | No - re-asserted, 15 attacks pass |

## Whole-suite confirmation after the correction

| Suite | Result |
|---|---|
| M081 unit | 77 passed |
| M081 PostgreSQL integration | 21 passed |
| M081 fresh second pass | 4 passed |
| M076-M081 chain | 509 passed |
| Full regression | failing-ID sets identical to the `43eb2c3` baseline in both modes |
