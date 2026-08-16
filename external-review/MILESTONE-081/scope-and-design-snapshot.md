# MILESTONE-081 - Operator-Asserted Round-Trip Result Ratio - Scope and Design

## Status: DESIGN CANDIDATE - NOT IMPLEMENTED, NOT OWNER FROZEN

---

## 1. Repository Truth

Verified from git and from `PROJECT_CHECKPOINT.md` at mission start, not taken
from the mission text.

```
branch                    master
HEAD                      43eb2c3defdc2964af45be5eaa5c3789743e3475
origin/master             43eb2c3defdc2964af45be5eaa5c3789743e3475
ahead/behind              0 / 0
working tree              clean
LATEST_FROZEN_MILESTONE   MILESTONE-080
M080_STATUS               APPROVED_AND_FROZEN
M081_STATUS               NOT_STARTED
NEXT_PERMITTED_ACTION     MILESTONE-081 -- recommendation only
```

Repository truth agrees with the expected starting state in every field.

## 2. Frozen M080 Starting Point

Read from code, not from prose.

`M076` (`operator_position_ledger.py`) persists per event:
`governance_id`, `runtime_id`, `position_governance_id`, `instrument_symbol`,
`kind`, `quantity: int`, `asserted_price: Decimal`, `event_timestamp`,
`recorded_at`, `source_position_plan_governance_id: str | None`, `note`.

Two frozen invariants are load-bearing for this milestone, and both were read
out of the validator rather than assumed:

```python
if self.asserted_price <= 0:
    ... "asserted_price must be > 0, got ..."
```

and `quantity` is typed `int` with positive-quantity validation, backed by
PostgreSQL `INTEGER`. `asserted_price` is `NUMERIC(20, 6)`: at most 14 integer
digits and exactly 6 decimal places.

| Term | What it means, from code |
|---|---|
| A. `quantity` | a whole number of units; fractional positions are unrepresentable |
| B. `asserted_price` | a per-unit price the operator typed; **strictly positive**; six decimal places; no currency attached |
| C. `event_timestamp` | when the operator says it happened - **effective time** |
| D. `recorded_at` | when it was written down - **knowledge time**; operator-supplied, not a system clock |

`M079` guarantees (E): exactly one filter, `recorded_at <= K`, applied before
any derivation, enforced **structurally** because the snapshot builder is never
handed the unfiltered events. No assertion recorded after `K` may influence any
value, status, count, ordering or limitation.

`M080` computes (F):

```
asserted_round_trip_result
    = SUM(exit quantity x that exit's asserted price)
    - (exited quantity x the asserted entry price)
```

exposed per position as `asserted_round_trip_result` and
`asserted_entry_cost_for_exited_quantity`, both rendered as exact decimal
strings by integer `divmod` with no `Decimal` operation.

`M080` refuses to compute (G): any aggregate, any percentage, any win rate, any
unrealized figure for still-open quantity.

`M080` says "unspecified asserted price units" (H) because **no currency column
exists on an M076 event**, and it forbids assuming two values share a
denomination (I) because nothing in the platform establishes that they do. It
has no aggregate (J), no percentage (K) and no win rate (L) because each would
be a claim it has no authority to make.

### The exact condition under which a result exists

Read from `_entry_for_key`:

```python
if exited_quantity > 0:
    entry_cost_scaled = exited_quantity * entry_price_scaled
    ...
    result_scaled = consideration_scaled - entry_cost_scaled
else:
    (every monetary field is None)
```

Therefore **`asserted_round_trip_result` is non-null exactly when
`asserted_entry_cost_for_exited_quantity` is non-null**, and in that case
`exited_quantity >= 1` and `entry_price > 0`, so the entry cost is
**strictly positive**. This is a frozen invariant, not a runtime guard.

### M. Does an independent per-position denominator exist?

Yes, and it must be **rejected**. M060 `PositionSizing` persists `entry_price`,
`stop_price`, `risk_per_unit`, `allowed_risk_amount`, `maximum_notional`,
`risk_based_quantity`, `capital_based_quantity`, `quantity`,
`position_notional` and `actual_risk`; `PositionPlan` adds
`supplied_account_equity` and `supplied_risk_percent`. All are persisted in
`position_plan`. Section 6 below explains why none of them may serve as M081's
denominator.

### N. Risk / notional / equity / stop authority

Exists (above), plus `supplied_account_equity` on M062/M063 studies. In every
case the amount is denominated in whatever units the operator supplied as
account equity. **`position_plan.py` contains zero occurrences of the word
`currency`.** So this authority is no better denominated than M076 is.

### O. Does any currency authority exist anywhere?

Searched every migration and every non-test source file.

| Source | Currency? | Verdict |
|---|---|---|
| M076 `operator_position_event` | **none** | no column of any kind |
| `InstrumentMaster` (`instrument_master.py`) | **none** - fields are `instrument_id`, `canonical_symbol`, `instrument_type`, `exchange_or_venue`, `external_identifier` | the natural place for a quote currency, and it is not there |
| M060 `position_plan` | **none** | zero mentions |
| M067 `portfolio_capital_policy` | `currency`, 3-letter uppercase, default `"USD"` | **the currency of a simulated study's capital policy**, not an instrument quote currency; never joined to an M076 event |

**Conclusion: the platform has no instrument-level quote-currency authority.**
M067's field is the denomination of a capital policy the operator declared for
a historical simulation. Treating it as the denomination of an operator's
asserted execution price would be exactly the invention M080's freeze forbids.
Symbol and exchange are **not** currency authorities.

## 3. Fresh Post-M080 Gap Analysis

M080 closed the arithmetic gap and, in closing it, **opened a new hazard of its
own**: it emits a per-position monetary value while forbidding the reader to
combine two of them. A reader who wants to know "which of these two positions
did better" has, today, exactly one option - divide the money themselves - and
that is precisely the act M080's denomination limitation says is unsupported.

M081's opportunity is to supply the one comparison primitive that is provably
safe, and to make the unsafe one structurally unavailable.

## 4. Candidate Ranking

Scored 1-5. For the four risk rows, **5 = low risk**.

| Criterion | A denomination authority | **B dimensionless ratio** | C count calibration | D outcome aggregation | E cross-session exposure | F system receipt time | G recording-latency evidence |
|---|---|---|---|---|---|---|---|
| product value | 3 | **5** | 3 | 4 | 3 | 3 | 2 |
| scientific value | 4 | **4** | 3 | 2 | 3 | 5 | 4 |
| honesty risk | 2 | **3** | 2 | 1 | 4 | 5 | 4 |
| denomination risk | 1 | **5** | 5 | 1 | 3 | 5 | 5 |
| temporal leakage risk | 5 | **5** | 4 | 3 | 4 | 5 | 4 |
| architectural fit | 2 | **5** | 4 | 3 | 4 | 2 | 4 |
| downstream unlock | 5 | **4** | 2 | 3 | 2 | 4 | 2 |
| frozen-contract risk | 2 | **5** | 4 | 2 | 4 | 2 | 5 |
| complexity | 2 | **4** | 3 | 2 | 3 | 2 | 4 |
| testability | 3 | **5** | 4 | 3 | 4 | 4 | 4 |
| operator usefulness | 2 | **5** | 3 | 3 | 3 | 2 | 2 |
| dependency readiness | 1 | **5** | 4 | 1 | 4 | 3 | 5 |
| **total** | **32** | **55** | **41** | **28** | **41** | **42** | **45** |

## 5. Selected Capability

**MILESTONE-081 - Operator-Asserted Round-Trip Result Ratio.**

For each position that M080 gives a monetary result, M081 reports the **exact
rational ratio** of that result to the asserted entry cost of the **same exited
quantity**:

```
                asserted_round_trip_result
ratio  =  ----------------------------------------------
          asserted_entry_cost_for_exited_quantity
```

per position, never aggregated, governed entirely by the M079 firewall it
inherits by composition.

## 6. Rejected Alternatives

**A - denomination / currency authority. REJECTED, and the rejection is a
finding.** There is no instrument-level quote-currency authority anywhere in the
repository to join to. `InstrumentMaster` - the one place it would naturally
live - does not have it. M067's capital-policy currency denominates a simulated
study's capital, not an operator's asserted execution price. Building A would
require either inventing the authority or amending frozen M076, both forbidden.
**Do not invent it if absent** - so it is not invented.

**B example 2 - result / planned risk amount (an R-multiple). REJECTED as a
denominator**, on four independent grounds, any one of which is sufficient:

1. **Denomination does not cancel.** `actual_risk` is denominated in the
   operator's supplied account-equity units; the M080 numerator is in
   unspecified asserted price units. Nothing establishes they are the same
   units. Dividing them produces a number that *looks* dimensionless and is
   not.
2. **Planned quantity is not asserted quantity.** `PositionSizing.quantity` is
   what the plan sized; the operator may have opened any quantity at all.
3. **Plan-to-position is not one-to-one.** Several M076 positions may cite the
   same `source_position_plan_governance_id`, and the citation is optional.
4. **Stop price is a plan intention**, never a recorded execution.

Calling that an R-multiple would assert a definition the repository does not
support.

**C - count calibration. REJECTED for M081**: proportions of plans followed
through read as success rates while saying nothing about outcome quality, and
they do not need M080 at all - they could have been built at M078.

**D - asserted-outcome calibration / aggregation. REJECTED as premature, and
this is the key sequencing argument.** M080's freeze forbids summing or
averaging monetary results across positions of unspecified denomination. D is
therefore **blocked until a dimensionless per-position quantity exists**. B is
its prerequisite. Choosing D now would mean either violating the M080 freeze or
inventing the missing primitive inside an aggregation milestone, where it would
get less scrutiny.

**E - cross-session exposure evolution. REJECTED**: real, but it neither uses
nor needs M080, and it leaves the hazard M080 created open.

**F - system-assigned knowledge receipt authority. REJECTED for M081, and
recommended for M082 consideration.** Scientifically the strongest of the
rejected set: it would close M079's own admitted weakness that `recorded_at` is
operator-supplied. But it requires either a new column on frozen M076 or a new
side table plus a write path, which is materially more frozen-contract risk
than a read-only composition, and it does not close the hazard M080 just
opened.

**G - recording-latency evidence (discovered during analysis). REJECTED**:
`event_timestamp` and `recorded_at` both exist and have never been compared, so
this is a genuine unexploited gap, but it is a diagnostic about the operator's
habits rather than a capability, and it is strictly weaker than F on the same
axis.

## 7. Authority Model

M081 is a **read-only composition of one frozen public contract**. It calls
`build_asserted_round_trip_report` from
`empirical_platform.decision_candidate.operator_asserted_round_trip` and reads
`asserted_round_trip_result` and `asserted_entry_cost_for_exited_quantity` off
each returned entry.

It does **not** re-fold the M076 event stream, does **not** re-derive
open-versus-closed, does **not** re-apply the knowledge filter itself, and does
**not** reimplement M080's arithmetic. Everything it knows, it knows because
M080 told it.

**Recovering exact integers without recomputing.** M080 exposes its money as
exact decimal strings, produced by `_money_from_scaled` using `divmod` and
string formatting - a sign, a whole part, and at most six fractional digits with
trailing zeros stripped. That rendering is **injective and losslessly
invertible**: splitting on the decimal point, right-padding the fraction to six
digits and recombining recovers the original scaled integer exactly, with no
`Decimal` involved. M081 inverts it rather than recomputing, so M080 remains the
single source of the arithmetic. The inversion is asserted against M080's own
boundary values by test.

## 8. Denomination Model

The ratio is **dimensionless**, and the cancellation is exact rather than
approximate. Both quantities are integer multiples of `10^-6` of the *same*
unspecified asserted price unit, for the *same* position, derived from the
*same* events:

```
result_scaled      = R x 10^-6   [asserted price units]
entry_cost_scaled  = C x 10^-6   [asserted price units]

ratio = (R x 10^-6) / (C x 10^-6) = R / C      [dimensionless]
```

The `10^-6` scale cancels identically, so the ratio is the exact quotient of two
Python integers and needs no scale reasoning at all.

**What this does and does not authorize.** It authorizes reporting a unitless
number per position. It does **not** retroactively authorize any statement about
the underlying money, and it does not establish a currency for anything.

## 9. Temporal / Knowledge Model

M081 introduces **no** temporal logic. It takes the same `(effective_as_of,
knowledge_as_of)` pair, passes it to M080 unchanged, and derives its ratios only
from what M080 returned. Because M080's builder is never handed post-`K`
evidence, and M081 is never handed anything but M080's output, the firewall is
inherited **structurally**: there is no code path by which a post-`K` assertion
could reach a ratio.

Both cutoffs remain required on the CLI with no default on either dimension.

Temporal vocabulary, extended by exactly one term:

```
OPERATOR_ASSERTED_ROUND_TRIP_RESULT_AT(E,K)         M080
OPERATOR_ASSERTED_ROUND_TRIP_RESULT_RATIO_AT(E,K)   M081
```

## 10. Lineage Model

M081 passes through M080's `cited_position_plan_governance_id` and adds no
lineage of its own. It performs **no join to M060**, precisely because section 6
rejected the plan as an authority. A plan citation is displayed, never
dereferenced.

## 11. Mathematical Model

```
numerator   = R   (exact integer, may be negative or zero)
denominator = C   (exact integer, strictly positive)
ratio       = R / C   as an exact reduced rational, sign carried by numerator
```

Reduced by `gcd(|R|, C)`, so `4/8` and `1/2` are the same object and compare
equal.

### Provable bounds

Both follow from M076's `asserted_price > 0` and positive integer quantities,
not from defensive coding:

- `C = exited_quantity x entry_price > 0` **strictly**, so **division by zero is
  impossible by construction**. There is no guard because none can be reached.
- exit consideration is a sum of strictly positive terms, hence `> 0`, so
  `R = consideration - C > -C`, hence

```
ratio > -1     ALWAYS, strictly
```

A ratio of exactly `-1` (a total loss) is **unreachable**, because a total loss
would require the operator to assert an exit at price zero, which M076 rejects.
The ratio is unbounded above.

This bound is a claim about the ledger's arithmetic, not about markets. It is
asserted by test and probed over 200000 randomized valid inputs.

## 12. Partial-Exit Semantics

The denominator is the entry cost **of the exited quantity**, never of the whole
position. This is the whole reason the field is named
`asserted_entry_cost_for_exited_quantity`.

The mandatory attack, worked:

```
OPENED  q=10 @ 100     REDUCED q=1 @ 200     9 still open

M080:  exited_quantity = 1
       entry cost for exited quantity = 1 x 100 = 100
       exit consideration            = 1 x 200 = 200
       result                        = 100

M081:  ratio = 100 / 100 = 1        (exactly +1, on the one exited unit)

A whole-position denominator would give 100 / 1000 = 1/10, which answers a
different question: "how much of the whole position's entry cost did the
realized part return", a question M081 does NOT ask.
```

Every rendered ratio therefore states the exited quantity it covers, and the
still-open quantity beside it. A partial-exit ratio is a statement about the
exited part only and says nothing about the position's eventual outcome.

## 13. Unresolved Semantics

| M080 status | M080 result | M081 |
|---|---|---|
| `UNRESOLVED_KNOWLEDGE_SEQUENCE` | none | **no ratio.** M080 emits no monetary value, so there is nothing to normalize |
| `EXIT_QUANTITY_UNRECONCILED` | exists when `exited_quantity > 0` | **ratio computed over the visible exited quantity, under its own distinct status** |

The unreconciled case was attacked both ways. Withholding the ratio entirely
would discard a well-defined arithmetic fact about evidence that genuinely
exists, and would make M081 *less* informative than M080 in exactly the case
where a reader most needs to see the shortfall. Emitting it silently alongside
clean ratios would let an unreconciled figure be read as comparable to a
reconciled one.

**Decision:** compute it, over the visible exited quantity only, and carry the
unreconciled status and the unaccounted quantity on the same line, so the number
can never be read without its caveat. M081 emits no comparison set, so there is
no pool for it to contaminate.

## 14. Open-Position Semantics

If no exit is asserted, M080 emits no result, and M081 emits **no ratio**.

Explicitly **not**: zero, `0%`, `1.0`, break-even, "flat", `null` coerced to a
number, or an entry omitted from the report. The position appears with the
status `NO_EXIT_ASSERTED_YET` and an explicit absence marker.

## 15. Numeric Precision Model

The ratio is stored and compared as an **exact reduced rational** - a pair of
Python integers - never as a float and never as a `Decimal`. There is no
ambient-context dependence to inherit, because no `Decimal` operation is
performed on it.

A ratio need not terminate in decimal form (`1/3`), so **two** renderings are
emitted, and their relationship is stated on every report:

| Rendering | What it is |
|---|---|
| `ratio_exact` e.g. `"1/3"`, `"-3/8"`, `"2"` | the **exact** reduced rational; the authoritative value |
| `ratio_decimal_approx` e.g. `"0.333333"` | an **approximation**, 6 decimal places, `ROUND_HALF_EVEN`, explicitly labelled |

The approximation is produced by exact integer division with an explicit
remainder rule, not by float or `Decimal` division, so it is reproducible under
any ambient context. Where the exact value terminates within six places, the two
agree and the report says the approximation is exact for that entry.

Mandatory representation tests: `1/3`, `2/3`, `1/7`, negative ratios, very large
ratios, exact zero, exact integer ratios, and the `NUMERIC(20,6)` boundary.

## 16. Comparability Semantics

Two M081 ratios are **arithmetically** comparable: both are unitless, so nothing
prevents `>` from being evaluated.

They are **not necessarily economically** comparable, and M081 says so on every
report. Denomination cancels; economics does not. Two positions may differ in
which unrepresented components apply - commissions, fees, financing, taxes,
dividends, corporate actions - and spread and slippage remain not separately
attributable, exactly as M080 froze. A larger ratio therefore means the
operator's asserted prices imply a larger arithmetic ratio, and nothing more.

Nor is it comparable across time-in-position: M081 emits **no** annualization,
no holding period and no time-weighting.

## 17. Aggregation Rules

**M081 emits no aggregate of ratio values. None.** No sum, no mean, no median,
no distribution, no best, no worst, no count of positive ratios.

Counts **by status** are emitted, exactly as M080 already does, because counting
how many positions are fully exited is a statement about evidence, not about
outcomes.

The justification for emitting no dimensionless aggregate, per the owner's rule
that any such aggregate must be justified: averaging these ratios would weight a
one-unit exit equally with a ten-thousand-unit exit; a value-weighted average
would require summing money across unspecified denominations, which the M080
freeze forbids; and the population is subject to the selection effects listed in
section 26. None of those is solved by M081, so M081 does not pretend to solve
them.

## 18. Explicit Forbidden Aggregation

M081 must never, and structurally cannot:

- sum M080 monetary results across positions
- average raw monetary results across positions
- compute a total or average profit
- compute a portfolio monetary result
- infer a currency from `instrument_symbol`
- infer a currency from an exchange or venue name
- assume two positions share a denomination

**Structural enforcement, strengthened by design review finding D-F04.** The
first draft said "no monetary field at report level". That was too weak: if the
numerator and denominator were emitted *unreduced* they would **be** the money,
and summing numerators would be summing money.

M081 therefore emits the ratio only as a **gcd-reduced** rational, and emits
**no monetary value anywhere, at any level** - no field is named, typed or
labelled as money, and no monetary total can be formed from what is here.

> ### ⚠ D-F04 PARTIALLY RETRACTED BY OWNER REVIEW FINDING 2
>
> The conclusion **"M081 emits no monetary value anywhere"** stands, and the
> design is unchanged.
>
> The *reasoning* offered for it does **not**. ~~Reduction actively destroys the
> monetary magnitude: `500` over `1000` becomes `1/2`, from which `500` is
> unrecoverable.~~ **RETRACTED.** When the two M080 scaled operands are already
> **coprime**, reduction changes nothing and the emitted pair **is** the original
> scaled pair — a ledger of one unit opened at `0.000003` and closed at
> `0.000004` emits `1/3`, and because M080's scale is publicly fixed at `10^-6`
> a knowledgeable reader reads the money straight back off it.
>
> gcd reduction is a **normalisation**, so that `4/8` and `1/2` are one value.
> It is **not** a confidentiality boundary and was never a sound basis for one.
> The real requirement is **semantic non-aggregation and non-denomination**:
> M081 offers no monetary field to sum and establishes no currency. It makes
> **no promise of monetary non-recoverability.**

Asserted by a test that walks every M081 surface - object, text and JSON - for
M080's monetary field names and values, and by a coprime-operand test that
demonstrates the retracted claim's counterexample explicitly.

## 19. Persistence Architecture

**Zero.** No new domain aggregate, no new table, no new column, no new
migration, no new repository. M081 reads through the existing frozen M076
repository path that M080 already uses. `usecases` continues not to import
`shared.persistence`; `entrypoints` continues not to import
`decision_candidate`.

## 20. CLI / Text / JSON

One additive console entry point,
`empirical-platform-asserted-round-trip-ratio`, requiring `--effective-as-of`
and `--knowledge-as-of` with **no default on either**, plus `--json`.

Text and JSON carry the same facts. JSON keys are explicit and
self-describing: `asserted_round_trip_result_to_entry_cost_ratio_exact`,
`..._decimal_approx`, `ratio_numerator`, `ratio_denominator`,
`ratio_approximation_is_exact`. The numerator and denominator are the
**reduced** pair, per D-F04, and no monetary field appears.

The ratio is deliberately **not** rendered as a percentage with a `%` sign
(design review D-H14): a percentage reads as a return, which this is not.

## 21. Deterministic Ordering

Entries are ordered by `(instrument_symbol, position_governance_id)`, both
persisted strings, exactly as M080 orders. **Never** by ratio value - ordering by
outcome would itself be a ranking claim.

## 22. Failure / Absence Semantics

M081 inherits M080's `NOT_ASSESSABLE` outcome and its reasons unchanged, and
adds none. Where M080 withholds a report, M081 withholds a report and repeats
M080's reason. Where M080 gives an entry with no monetary result, M081 gives an
entry with an explicit ratio absence and a reason. Database faults propagate;
they are never disguised as "no data".

## 23. Frozen-Contract Preservation

M070, M075, M076, M077, M078, M079 and M080 are read-only and byte-unmodified.
M080's banner, limitations, statuses, field names and arithmetic are untouched.
The M062/M064/M065 seal debt is untouched. No migration.

## 24. Scientific-Honesty Boundary

M081 emits a unitless number derived from unverified assertions. The banner must
therefore deny, in the artifact itself, every reading it does not support. The
vocabulary decision is deliberately **deferred to after the hostile design
review**; the working name is
`asserted_round_trip_result_to_entry_cost_ratio`, chosen because it names its
own numerator and denominator and claims nothing else.

Forbidden names, to be asserted absent from every status, field, enum and JSON
key: `ROI`, `return`, `total_return`, `investment_return`, `profit_percentage`,
`performance`, `performance_percentage`, `yield`, `gain_percent`, `win_rate`,
`hit_rate`, `expectancy`, `accuracy`, `alpha`, `edge`, plus the thirteen tokens
M080 already forbids.

## 25. What M081 Proves

That, for one position, the operator's own asserted exit prices imply an exact
rational ratio of arithmetic result to asserted entry cost on the quantity they
assert they exited, computed only from evidence the ledger records as having
been recorded by the knowledge cutoff.

## 26. What M081 Does NOT Prove

It is not a return, not ROI, not profit percentage, not investment performance,
not a market return, not a tax result, not verified, and not evidence that any
trade occurred or occurred at the stated price. It is not a complete economic
outcome: the components M080 lists as unrepresented remain unrepresented, and
spread and slippage remain not separately attributable and are **not** claimed
excluded.

It carries no currency and establishes none. It makes no statement about a
still-open quantity. It is not annualized and not time-weighted. It is not
comparable across positions economically, only arithmetically. And it says
nothing about the population: only positions the operator chose to record are
visible at all, so no statement about typical outcomes may be built on it.

## 27. M082 Boundary

Explicitly out of scope and not built: any aggregate of ratios; any calibration,
expectancy or win-rate statistic; any currency or denomination authority; any
join to M060 sizing; any R-multiple; any annualization or time-weighting; any
system-assigned receipt time; any monetary aggregation; any new table, column or
migration.

**Recommended M082 direction, recommendation only:** candidate F, a
system-assigned knowledge receipt authority, which would close M079's own
admitted weakness that `recorded_at` is operator-supplied - the strongest
remaining scientific gap, and a prerequisite before any calibration milestone
should be trusted.
