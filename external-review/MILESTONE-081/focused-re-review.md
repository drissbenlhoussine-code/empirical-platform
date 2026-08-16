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


---

# Focused Re-Review After the R02 Correction

## What changed

`_limitations` no longer has `ASSERTED_PRICE_DENOMINATION_LIMITATION` prepended
alongside M080's verbatim limitations, because M080 already carries it. The
now-unused import was removed. Nothing else was touched.

| Re-attack | Result |
|---|---|
| Does the denomination limitation still appear? | **Yes, exactly once**, on both report shapes |
| Is it still verbatim from M080? | Yes - same constant, not a copy |
| Does the withheld `NOT_ASSESSABLE` report still carry it? | Yes - asserted, parametrised |
| Are there any other duplicated limitations? | **No** - the whole tuple is asserted duplicate-free |
| Did any other limitation disappear? | No - M080's are carried verbatim, M081's eight are appended |
| Does the rendered text contain it once? | Yes - asserted on the rendered string, not only the tuple |
| Did the ratio, statuses or firewall change? | No - all 232 attacks re-run, all pass |
| Gates after the change | ruff, format, mypy (306 files), architecture, negative fixture all clean |

## Whole-suite confirmation after both corrections

| Suite | Result |
|---|---|
| M081 unit | **79 passed** |
| M081 PostgreSQL integration | 21 passed |
| M081 fresh second pass | 4 passed |
| M081 suites combined | 104 passed |
| Full regression, both modes | failing-ID sets identical to the `43eb2c3` baseline |
| Executed attacks re-run | 232 / 232 |


---

# Focused Re-Review After the Owner Correction Pass

## Finding 1 - the changed area is `_decimal_approximation` only

| Re-attack | Result |
|---|---|
| Does a tiny negative ratio still render `~0`? | **No** - `>-0.000001 and <0` |
| Are tiny positive and tiny negative distinguishable? | **Yes** - different strings |
| Is either confusable with exact zero? | **No** - exact zero renders `0` with `is_exact=True` |
| Was precision increased to dodge the case? | **No** - deliberately not; it would move the boundary, not remove it |
| Does the R01 truncation property still hold? | Yes - `\|approx\| <= \|exact\|` re-asserted, and a bound is not a magnitude claim |
| Does the boundary case still render `~-0.999999`? | Yes - unaffected |
| Is the exact rational still authoritative and unchanged? | Yes - `-1/2000000` |
| Text / JSON parity | Identical string in all three surfaces |
| Ambient `Decimal` context | Still irrelevant - five precisions |
| Real PostgreSQL rows | Cross-checked against raw SQL to `-1/2000000` |
| Did statuses, counts, ordering or the firewall change? | No |

## Finding 2 - claim only, no capability change

| Re-attack | Result |
|---|---|
| Did any behaviour change? | **No** - the ratio, its reduction and every surface are byte-identical in output apart from the corrected limitation text |
| Does any surface still promise non-recoverability? | **No** - six phrasings swept, asserted by test |
| Is the coprime counterexample asserted, not just described? | Yes - unit **and** PostgreSQL |
| Is D-F04 erased? | **No** - marked **partially retracted** in place, with the original claim struck through and the counterexample beside it |
| Is the semantic guarantee still asserted? | Yes - no field named, typed or labelled as money; no aggregate; no currency |
| Does the limitation now state the boundary honestly? | Yes - "SEMANTIC boundary, NOT a confidentiality one", naming the coprime case |

## Whole-suite confirmation after the correction pass

| Suite | Result |
|---|---|
| M081 unit | **101 passed** |
| M081 PostgreSQL integration | **24 passed** |
| M081 fresh second pass | 4 passed |
| M076-M081 chain | **536 passed** |
| Full regression, both modes | failing-ID sets identical to the `43eb2c3` baseline |
