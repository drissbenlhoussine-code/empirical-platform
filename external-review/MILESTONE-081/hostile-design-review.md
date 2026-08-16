# M081 - Hostile Design Review

**156 attacks executed against the design before a single line of M081 was
written.** Many were run against frozen M076/M080 code rather than reasoned
about, because a design attack that is only argued is worth less than one that
is executed. **9 findings changed the design.** They are listed first.

---

## Findings that changed the design

### D-F01 (HIGH) - a float rendering would assert an unreachable total loss

Executed at the `NUMERIC(20,6)` extreme:

```
OPENED  q=2147483647 @ 99999999999999.999999
CLOSED  q=2147483647 @ 0.000001

exact ratio = -99999999999999999998 / 99999999999999999999
float(ratio) = -1.0
```

The exact value is **strictly greater than -1**; the float is **exactly -1.0**.
A float rendering would therefore print a total loss that section 11 proves is
unreachable, at the very input most likely to be quoted.

**Correction:** the ratio is an exact reduced rational internally and is never a
float. The decimal rendering is an explicitly-labelled approximation produced by
integer division, and carries a flag saying whether it is exact for that entry.

### D-F02 (HIGH) - the string inversion is not `replace(".", "")`

I wrote exactly that shortcut in my own first probe and it silently gave the
right answer for `"100"` by luck. M080 renders `100` (no point), `0.5` (one
place) and `1.000001` (six places) - stripping the point conflates all three
scales.

**Correction:** the inversion splits on the point, right-pads the fraction to
exactly six digits, then combines, and is asserted against M080's own boundary
renderings by a round-trip test. Recorded because a shortcut that works on the
first example is the most dangerous kind.

### D-F03 (HIGH) - money and ratio can rank two positions oppositely

Executed:

| position | M080 money result | M081 ratio |
|---|---|---|
| `7203.T` | **1000** | **1/10** |
| `AAPL` | 500 | 1/2 |

The monetary numbers say the first position did twice as well; the ratios say
the second did five times as well. Since the two symbols have **unknown and
possibly different denominations**, the monetary comparison is not merely
different - it is unsupported.

**Correction:** entries are ordered by `(instrument_symbol,
position_governance_id)` and **never** by value, and see D-F05.

### D-F04 (HIGH) - M081 must not emit any monetary value at all

Original design said "no monetary field at report level". That is too weak. If
M081 emits M080's money per entry, a reader can sum it; if it emits the
*unreduced* scaled integers as numerator and denominator, those **are** the
money, and summing numerators is summing money.

**Correction, and it is a genuinely structural one:** M081 emits the ratio only
as a **gcd-reduced** rational. Reduction actively destroys the monetary
magnitude - a result of `500` over a cost of `1000` becomes `1/2`, from which
`500` is unrecoverable. M081 emits **no** monetary value anywhere, at any level.
A reader who wants the money runs M080, which carries its own full denomination
banner. Asserted by a test that walks every M081 surface for M080's monetary
field names.

### D-F05 (MEDIUM) - a six-place approximation of `1/3` reads as exact

`0.333333` looks like a value, not a truncation.

**Correction:** `ratio_approximation_is_exact` is emitted per entry, and the
text renderer marks approximate values distinctly from exact ones.

### D-F06 (MEDIUM) - "unreconciled" ratios must not sit silently beside clean ones

**Correction:** section 13's decision - compute over the visible exited quantity,
carry the unreconciled status and the unaccounted quantity on the same line, and
emit no comparison set for it to contaminate.

### D-F07 (MEDIUM) - the plan is not a denominator authority, proved not argued

Executed: two distinct positions `P1` and `P2` both citing `PLAN-A`. A per-plan
denominator would have to be split between them by a rule that does not exist.

**Correction:** section 6's rejection of the R-multiple is recorded as
*proved*, and M081 performs no join to M060 at all.

### D-F08 (MEDIUM) - "comparable" was under-qualified

The first draft said ratios are comparable across positions. They are
*arithmetically* comparable and not necessarily *economically* comparable.

**Correction:** section 16 splits the two, and the banner carries the
distinction.

### D-F09 (LOW) - ordering must be stated as a non-claim

Ordering by outcome would itself rank the operator's decisions.

**Correction:** section 21 states ordering is by persisted identity and that
this is deliberate.

---

## DENOMINATION - 21 attacks

| # | Attack | Result |
|---|---|---|
| D-D01 | Two symbols with different hypothetical currencies | executed; ratios well-defined per position, monetary comparison unsupported - see D-F03 |
| D-D02 | Does `InstrumentMaster` carry a currency? | **no** - fields are `instrument_id`, `canonical_symbol`, `instrument_type`, `exchange_or_venue`, `external_identifier` |
| D-D03 | Does any migration create a currency column joinable to M076? | only `a3f7c81e4b96` (M067 capital policy); not joinable to an operator position event |
| D-D04 | Is M067's `currency` an instrument quote currency? | **no** - it denominates a simulated study's capital policy |
| D-D05 | Symbol heuristic: `AAPL` implies USD | rejected - no authority; asserted by test |
| D-D06 | Exchange heuristic: `7203.T` implies JPY | rejected - `exchange_or_venue` is free text and carries no currency mapping |
| D-D07 | Missing currency filled with a default | forbidden; nothing to default from |
| D-D08 | Mismatched denomination inside one position | impossible - one position's events share one symbol; asserted |
| D-D09 | Does the `10^-6` scale cancel exactly? | yes - identical scale on both sides, integer quotient |
| D-D10 | Could a non-cancelling denominator sneak in? | only by joining M060; M081 performs no such join |
| D-D11 | Does a unitless ratio retroactively denominate the money? | no - stated explicitly in section 8 |
| D-D12 | Could two ratios be summed as if same currency? | there is no aggregate to sum them in |
| D-D13 | Does M081 re-emit M080's money? | **no** - D-F04 |
| D-D14 | Can money be recovered from a reduced rational? | no - `1/2` does not determine `500/1000` |
| D-D15 | Does the banner deny currency? | yes - M080's denomination limitation is carried verbatim |
| D-D16 | `XAU`, `BTC`, `ZZZZ` produce an inferred unit | no - nothing is derived from the symbol |
| D-D17 | Does `note` free text get parsed for a currency? | never read |
| D-D18 | Cross-denomination aggregate reachable by CLI flag | no such flag exists |
| D-D19 | JSON key implies a currency | key names name numerator and denominator only |
| D-D20 | Does M081 modify M076 to add a currency? | no - zero schema change |
| D-D21 | Is candidate A silently half-built? | no - explicitly rejected with the reason recorded |

## MATHEMATICS - 38 attacks

| # | Attack | Result |
|---|---|---|
| D-M01 | Denominator zero | **unreachable** - M076 rejects `asserted_price <= 0`; executed against `0`, `-1`, `-0.000001` |
| D-M02 | Denominator negative | unreachable - same invariant, and quantity is a positive int |
| D-M03 | Numerator exists but denominator does not | impossible - both are `None` or both are set, from the same `if exited_quantity > 0` |
| D-M04 | Tiny denominator (`0.000001` x 1 unit) | exact rational; no precision loss |
| D-M05 | Huge numerator at max INTEGER quantity x max price | exact; 30-significant-digit values handled as integers |
| D-M06 | Exact break-even | executed - result `0`, ratio exactly `0`, not `-0` |
| D-M07 | Negative zero in the ratio | impossible - `Fraction(0, C)` normalizes to `0` |
| D-M08 | Ratio exactly `-1` (total loss) | **provably unreachable** - would need an exit price of `0`, which M076 rejects; executed |
| D-M09 | Ratio below `-1` | impossible - exit consideration is a sum of strictly positive terms |
| D-M10 | Is the `> -1` bound empirically stable? | probed over 200000 randomized valid inputs; minimum `-0.99999178`, never `<= -1` |
| D-M11 | Ratio above `+1` | ordinary and permitted (e.g. exit at 3x entry gives `2`) |
| D-M12 | Ratio unbounded above | yes, and not clamped |
| D-M13 | Partial exit uses whole-position denominator | **prevented** - executed worked example, `1` vs `1/10` |
| D-M14 | Arbitrary ambient `Decimal` context changes the ratio | no `Decimal` operation is performed on it |
| D-M15 | `getcontext().prec = 1` | ratio unaffected - integers only |
| D-M16 | Float appears anywhere in the value path | forbidden; asserted by test |
| D-M17 | `1/3` representation | exact rational `1/3`; approximation labelled |
| D-M18 | `2/3` | exact; approximation `0.666667` marked approximate |
| D-M19 | `1/7` | exact; non-terminating, marked |
| D-M20 | Exact integer ratio (`2/1`) | rendered `2`, marked exact |
| D-M21 | Reduction: `4/8` and `1/2` compare equal | yes - gcd-reduced |
| D-M22 | Sign carried on the denominator | never - denominator is strictly positive, sign lives on the numerator |
| D-M23 | Multiple exits at different prices | each contributes its own price; consideration is their sum |
| D-M24 | Exits summing above and below entry | handled; sign follows the total |
| D-M25 | Rounding introduced anywhere silently | no - the only rounding is the labelled approximation |
| D-M26 | Approximation rounding mode unstated | stated: `ROUND_HALF_EVEN`, 6 places, by integer division |
| D-M27 | Approximation computed with `Decimal`/float division | no - integer division with explicit remainder |
| D-M28 | Is the approximation ever presented as the value? | no - `ratio_exact` is authoritative |
| D-M29 | Very large ratio's approximation overflows | integers do not overflow in Python |
| D-M30 | `gcd` with a zero numerator | `Fraction(0, C)` is `0`; no division by gcd 0 |
| D-M31 | Fractional share quantity | unrepresentable - M076 types quantity `int` |
| D-M32 | Quantity `0` exit | M076 rejects; and `exited_quantity == 0` yields no result |
| D-M33 | Does M081 recompute M080's arithmetic? | **no** - it inverts M080's exact rendering |
| D-M34 | Is that inversion lossless? | yes - `_money_from_scaled` is injective; asserted by round-trip test |
| D-M35 | Inversion by naive point-stripping | **caught as D-F02** |
| D-M36 | Six-decimal-place price boundary | exact - scale cancels |
| D-M37 | Ratio of a one-unit position | exact |
| D-M38 | Comparing two exact rationals for equality | exact - no epsilon needed |

## TEMPORAL - 20 attacks

| # | Attack | Result |
|---|---|---|
| D-T01 | Post-`K` exit reaches a ratio | executed - at `K` before the exit's `recorded_at`, status is `NO_EXIT_ASSERTED_YET` and no result exists, so no ratio |
| D-T02 | `K` boundary inclusivity | executed at day 299/300/301 - inclusive at 300, matching M079 |
| D-T03 | Backfilled event (early effective, late recorded) | executed - invisible before its `recorded_at` |
| D-T04 | `E` boundary | delegated to frozen M076 unchanged |
| D-T05 | `K < E` | M080's existing limitation surfaces unchanged |
| D-T06 | Same-instant events | ordering delegated to M080 |
| D-T07 | Timezone-naive cutoff | rejected upstream by the usecase validator |
| D-T08 | Does M081 add any temporal logic? | **none** - it never reads a timestamp |
| D-T09 | Could a ratio be computed from unfiltered events? | no code path - M081 only ever sees M080's output |
| D-T10 | CLI defaulting a cutoff to "now" | no default on either dimension |
| D-T11 | Two reads at the same `(E,K)` differ | deterministic - pure function of M080's output |
| D-T12 | Post-`K` rows appended between reads | double-database proof deferred to implementation phase |
| D-T13 | `recorded_at` in the future | operator-supplied; M079's frozen limitation repeated, not re-litigated |
| D-T14 | Advancing `K` reveals evidence | expected and correct |
| D-T15 | Advancing `K` changes a previously-emitted ratio | possible and correct - a later exit changes the exited quantity; the report says which `(E,K)` produced it |
| D-T16 | Ratio cached across cutoffs | no caching |
| D-T17 | `E` advanced without `K` | independent dimensions preserved |
| D-T18 | Does M081 weaken M079's structural guarantee? | no - it is strictly downstream of it |
| D-T19 | Annualization implies time | **not emitted** |
| D-T20 | Holding-period weighting | **not emitted** |

## LINEAGE - 15 attacks

| # | Attack | Result |
|---|---|---|
| D-L01 | Multiple positions cite one plan | executed - `P1` and `P2` both cite `PLAN-A`; see D-F07 |
| D-L02 | Missing plan citation | passed through as absent; nothing inferred |
| D-L03 | Plan naming a different instrument | never dereferenced, so never trusted |
| D-L04 | Duplicate plan ids | irrelevant - no join |
| D-L05 | Planned quantity vs asserted quantity | never compared - would be a claim M081 has no authority for |
| D-L06 | `actual_risk` as denominator | rejected - section 6 |
| D-L07 | `position_notional` as denominator | rejected - same denomination problem |
| D-L08 | `supplied_account_equity` as denominator | rejected - operator-supplied, undenominated |
| D-L09 | `stop_price` implies a risk unit | a plan intention, never an execution |
| D-L10 | Does M081 import M060? | no |
| D-L11 | Does M081 import M078? | no |
| D-L12 | Session join | out of scope, stays M078's |
| D-L13 | Plan citation used for ordering | no - ordering is by symbol and position id |
| D-L14 | Plan citation used for grouping | no grouping exists |
| D-L15 | R-multiple vocabulary anywhere | forbidden token, asserted absent |

## POPULATION - 16 attacks

| # | Attack | Result |
|---|---|---|
| D-P01 | Open position given a zero ratio | executed - no result, no ratio, explicit absence |
| D-P02 | Open position given "0%" or "break-even" | forbidden; asserted absent |
| D-P03 | Open position omitted from the report | no - it appears with its status |
| D-P04 | Unresolved sequence normalized | no - M080 emits no result to normalize |
| D-P05 | Unreconciled exit normalized silently | no - D-F06 |
| D-P06 | Plans with no ledger action counted | M081 counts positions, not plans |
| D-P07 | Positions without plan citation excluded | no - included, citation shown as absent |
| D-P08 | Survivorship: only recorded positions are visible | stated as a limitation; no population claim is made |
| D-P09 | Selective operator recording | same - stated, not corrected |
| D-P10 | Completion bias toward closed positions | no aggregate exists, so no biased statistic can be formed |
| D-P11 | Cross-session duplicates | M081 is position-centric; no session concept |
| D-P12 | Repeated evaluation at many `K` | permitted and honest - each report names its `(E,K)` |
| D-P13 | Mixing ratios from different `K` | impossible within one report |
| D-P14 | Counting positive ratios | **not emitted** - it would be a win rate |
| D-P15 | Best / worst position | **not emitted** |
| D-P16 | Distribution or histogram | **not emitted** |

## HONESTY - 26 attacks

| # | Attack | Result |
|---|---|---|
| D-H01 | Ratio called `ROI` | forbidden token |
| D-H02 | Called `return` | forbidden |
| D-H03 | Called `total_return` | forbidden |
| D-H04 | Called `investment_return` | forbidden |
| D-H05 | Called `profit_percentage` | forbidden |
| D-H06 | Called `performance` / `performance_percentage` | forbidden |
| D-H07 | Called `yield` | forbidden |
| D-H08 | Called `gain_percent` | forbidden |
| D-H09 | Called `win_rate` / `hit_rate` | forbidden |
| D-H10 | Called `expectancy` | forbidden |
| D-H11 | Called `accuracy` | forbidden |
| D-H12 | Called `alpha` / `edge` | forbidden |
| D-H13 | M080's thirteen forbidden tokens re-checked | all re-asserted on M081 surfaces |
| D-H14 | Rendered as a percentage with a `%` sign | **avoided** - a percentage reads as a return; the ratio is rendered as a rational |
| D-H15 | Implies verified outcome | banner denies |
| D-H16 | Implies a trade occurred | banner denies |
| D-H17 | Implies complete economics | banner repeats M080's unrepresented-component split verbatim |
| D-H18 | Implies spread/slippage were excluded | banner repeats "NOT claimed to be excluded" |
| D-H19 | Implies dividends/corporate actions are captured | denied |
| D-H20 | Implies tax treatment | denied |
| D-H21 | Implies cross-position economic comparability | **qualified** - D-F08 |
| D-H22 | Implies a currency | denied verbatim from M080 |
| D-H23 | Implies annualized performance | not emitted |
| D-H24 | A larger ratio implies a better decision | denied - the artifact states it means only that the asserted prices imply a larger arithmetic ratio |
| D-H25 | The word "profit" anywhere | forbidden |
| D-H26 | The bare token `PNL` | forbidden |

## ARCHITECTURE - 20 attacks

| # | Attack | Result |
|---|---|---|
| D-A01 | Does M080 expose scaled integers publicly? | executed - **no**; hence the documented inversion |
| D-A02 | Mutate frozen M080 to expose them | **rejected** - M080 is frozen; inverting its own exact rendering costs nothing |
| D-A03 | Duplicate M080's arithmetic | forbidden; M081 never folds events |
| D-A04 | Duplicate M076's fold | forbidden |
| D-A05 | Bypass M079 | no code path |
| D-A06 | New table / column / migration | **none** |
| D-A07 | New repository | none - reuses M080's read path |
| D-A08 | `usecases` imports `shared.persistence` | forbidden by the architecture checker |
| D-A09 | `entrypoints` imports `decision_candidate` | forbidden by the checker |
| D-A10 | Unrelated refactor | none |
| D-A11 | Seal-debt repair | none |
| D-A12 | Touching M075-M080 source | none |
| D-A13 | Changing `PROJECT_CHECKPOINT.md` | none on this branch |
| D-A14 | Adding a dependency | none - `fractions` and `math.gcd` are stdlib |
| D-A15 | Global state | none |
| D-A16 | Randomness | none |
| D-A17 | Wall-clock read in the domain | none |
| D-A18 | Mutable module-level default | tuples only |
| D-A19 | Report-level monetary field | **none** - D-F04 |
| D-A20 | M082 work started | none |

---

**156 attacks. 9 findings, all corrected in the design before implementation.**
No unresolved HIGH or CRITICAL finding remains.
