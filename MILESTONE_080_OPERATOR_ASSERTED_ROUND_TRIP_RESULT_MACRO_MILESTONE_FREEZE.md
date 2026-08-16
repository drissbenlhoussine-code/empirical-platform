# MILESTONE-080 - Operator-Asserted Round-Trip Result - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M080 baseline
`0e73e0bebbd6ecbfc672cbced14010ccf4d5f7b6` (the M079 Owner Freeze
hash-recording HEAD; M079 fully `APPROVED_AND_FROZEN`), independently
re-verified from git and from `PROJECT_CHECKPOINT.md` at mission start rather
than taken from the mission text. Delivered through pull request #10,
owner-approved at head `51d8128909bb1a5f171cb0ae3185e0052b97c3f0` with the
`foundation` workflow green on that exact SHA, and merged into `master` as
`286915dd8b1b016f1292e7218a062d008b1b0dc6`.

The pull request was merged with a true merge commit. **All four commits are
preserved and none was squashed away:** the implementation
`18b8e90e4e3abe9c1041ffdb0ab05714204007bf`, the external review evidence
package `d8c8244915fa04223dee83ba6b8a59ca07913dc6`, owner correction pass 1
`e0510b09449c97100420afc83a2c5ef5f168145c`, and owner correction pass 2
`51d8128909bb1a5f171cb0ae3185e0052b97c3f0`.

Scope, the proved gap, six ranked candidates, semantics, non-goals and the
pre-implementation adversarial design review are recorded in
`MILESTONE_080_OPERATOR_ASSERTED_ROUND_TRIP_RESULT_SCOPE_AND_DESIGN.md`. The
eleven-file external review package is under `external-review/MILESTONE-080/`.

All evidence in this record - including every PostgreSQL result - was executed
in a Linux container holding a fresh clone of this repository, against a real
PostgreSQL 16 server, not simulated.

## Why M080 Exists

M076 validates and persists `asserted_price` on **every** lifecycle event -
`OPENED`, `REDUCED` and `CLOSED` alike. Proved by reading the frozen source
rather than assumed: the only derivation that ever reads a price reads
`opening.asserted_price` alone
(`operator_position_ledger.py:419`). **Every exit price the operator had ever
asserted was write-only data.** Four milestones had been built on that ledger
and none of them read it.

M079 then supplied the missing precondition. Before a knowledge-time firewall
existed, any outcome number computed from the ledger would have been a
backward-looking figure computed from whatever happened to be recorded by the
time somebody asked - which is exactly the shape of an unfalsifiable
performance claim. M079 made "what was knowable at K" a structural property
rather than a discipline. M080 is the first milestone permitted to compute a
monetary-looking value because it is the first one that can say **when** the
evidence for that value became available.

## The Authority Question the Owner Asked Directly

The mission asked whether a monetary asserted outcome is now authorized. The
answer recorded here, and approved by the owner, is **yes, and only this**:

> arithmetic over operator-asserted entry and exit prices and quantities, for
> the exited quantity only, from evidence allowed by the M079 knowledge-time
> firewall.

Formally:

```
asserted_round_trip_result
    = SUM(exit quantity x that exit's asserted price)
    - (exited quantity x the asserted entry price)
```

## A. Arithmetic on Assertions, Not Measured Trading Performance

This is the single load-bearing fact of the milestone. Every figure M080 emits
is arithmetic over numbers a human typed into a ledger. There is no broker, no
confirmation, no reconciliation, no fill, no market data and no evidence that
any trade occurred or occurred at the stated price.

M080 is **NOT**: broker realized P&L; verified profit; an actual execution
result; actual cash proceeds; investment performance; a market return; a tax
result; or evidence that any trade occurred.

The bare token `PNL` and twelve other forbidden names appear in no status, no
field, no enum and no JSON key. Tests walk every surface to assert this, and
re-assert it at the numeric boundary case so that a later correction cannot
weaken the guard without failing.

There is a real vocabulary collision worth naming rather than hiding:
`realized_pnl`, `profit_factor` and `maximum_realized_pnl_drawdown` already
exist in this repository, in M062 validation studies, M063 robustness studies
and M067 portfolio studies. Every one of those is **simulated** P&L over
historical bars, and none touches an operator assertion. M080 deliberately
shares none of that vocabulary.

## B. Exact Arithmetic Through Python Integers Scaled to 10^-6

The first candidate claimed exact arithmetic, no rounding and exact
reproducibility. **All three were false**, and the owner found it. Every one of
my own numeric attacks had paired a large price with a *small* quantity.

M076 persists `quantity` as PostgreSQL `INTEGER`, so `2147483647` is a legal
row. At the maximum persistence-valid price:

```
exact:    214748364699999999997852.516353   (30 significant digits)
produced: 214748364699999999997852.5164     (rounded to the ambient 28)
```

Two distinct defects. `Decimal(quantity) * asserted_price` evaluates under the
**ambient** context; and the renderer passed through `Decimal.normalize()`,
which **re-rounds** an exact value on the way out - so even exact arithmetic
could not have been rendered faithfully.

The fix is exact scaled-integer arithmetic, chosen over deriving a local
`Decimal` context precision because it needs **no precision parameter to
justify**: exact by construction rather than exact up to a proven bound. Frozen
M076 caps an asserted price at six decimal places, so every price is an exact
integer multiple of `10^-6`, and quantities are `int`. Every value M080
computes is therefore an integer multiple of `10^-6`, and the whole computation
fits in Python `int`, which is arbitrary-precision.

| Step | How |
|---|---|
| price to scaled int | `_scaled_price()` reads `Decimal.as_tuple()` - pure data, no Decimal operation - and scales by appending zero digits |
| all arithmetic | Python integers |
| rendering | `_money_from_scaled()` - `divmod` and string formatting, **no Decimal at all** |

If a future M076 ever widened the price scale past six, `_scaled_price` raises
naming the invariant rather than rounding silently.

Two properties fall out of the design rather than being guarded: negative zero
is now impossible **by construction**, and the renderer cannot emit exponent
form because it never builds a `Decimal`.

## C. No Ambient Decimal Context May Affect a Result

No global `Decimal` state is mutated, and `getcontext().prec` is **not** raised.
`scaleb`, `quantize` and multiplication by a power are deliberately avoided -
every one of them is context-sensitive.

Proven at the boundary: `2147483647 @ 99999999999999.999999`, exited at
`0.000001`, yields

```
-214748364699999999995705.032706
```

identical under ambient precisions 1, 5, 9, 28 and 60, identical under
`ROUND_UP` and `ROUND_FLOOR`, identical in the object, the rendered text and
the JSON, and matching an independent **pure-integer** recomputation from the
raw PostgreSQL columns.

**Do not restore Decimal arithmetic or context-sensitive rendering.**

## D. M076 Contains No Currency Authority

Verified against the migration `b7e1c4a95d38`, the frozen domain event and the
repository adapter - not assumed. M076 persists exactly `instrument_symbol`,
`quantity`, `asserted_price`, `event_timestamp`, `recorded_at`, an optional
plan citation and a note.

There is **no** `currency`, `quote_currency`, `price_currency` or
`denomination` column of any kind. `instrument_symbol` is **not** a currency
authority.

No currency value is invented anywhere in the code, the evidence or this freeze
record. No schema change and no migration were made for this.

## E. All Values Are Unspecified Asserted Price Units

`ASSERTED_PRICE_DENOMINATION_LIMITATION` is carried on **every** report shape -
closed, open, partial, empty, and the withheld `NOT_ASSESSABLE` one - and the
banner repeats it. Preserved verbatim:

> every monetary-looking value here is arithmetic in the SAME UNSPECIFIED
> ASSERTED PRICE UNITS carried by the operator ledger. M080 does NOT establish a
> currency denomination: no currency is persisted on an operator position event,
> and instrument_symbol is not a currency authority. A value here must NOT be
> read as USD, EUR or any other currency on M080's authority, and two values must
> NOT be assumed to share a denomination merely because both appear in this
> report

The banner line, preserved verbatim:

> Every value is in the SAME UNSPECIFIED ASSERTED PRICE UNITS the ledger
> carries: NO currency is persisted, so this is NOT USD, NOT EUR and NOT any
> other denomination on M080's authority

A token sweep for `$`, `USD`, `EUR`, `GBP`, `JPY`, `CHF`, `CAD`, `AUD`, the
euro, pound and yen signs across the rendered text and the JSON - with the
banner and limitation sentences stripped out first, because the denial
legitimately names currencies in order to deny them - finds nothing outside
those explicit denials. `AAPL`, `XAU`, `BTC` and `ZZZZ` all render identically
clean.

## F. Two Values Must Not Be Assumed to Share a Denomination

Stated explicitly in the limitation quoted above, and load-bearing for any
future milestone: because M080 establishes no denomination at all, two entries
appearing in one report carry no implication that their units are the same. No
aggregate field exists that would tempt a reader to combine them.

## G. Economic-Component Semantics - the Approved Three-Way Split

The owner rejected two earlier formulations before this one. Both retractions
are preserved in the evidence package rather than erased.

| Group | Members | What may honestly be said |
|---|---|---|
| `UNREPRESENTED_CASHFLOW_COMPONENTS` | commissions, exchange and regulatory fees, financing and borrow cost | cash the ledger never records; including them would normally **reduce** a raw result |
| `CONTEXT_DEPENDENT_COMPONENTS` | taxes, dividends, corporate actions | can move the real outcome in **either** direction |
| `NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS` | spread, slippage | **NOT claimed excluded**; may already be embedded in the asserted prices; not measurable from this data |

The reason spread and slippage cannot be claimed excluded, stated rather than
merely disclaimed: M080's arithmetic uses the operator's **own asserted
execution prices**. If those are what the operator says they actually paid and
received, spread and slippage are **already embedded in them**. M076 stores no
benchmark price, no quoted bid or ask, no intended price and no arrival price,
so there is nothing to measure an execution effect against, and M080 cannot
determine whether they are absent, embedded, partly embedded or independently
attributable.

The umbrella name changed for the same reason. "Excluded" asserts the very
absence that cannot be asserted:

```
EXCLUDED_COST_COMPONENTS      (original, retracted)
EXCLUDED_ECONOMIC_COMPONENTS  (correction pass 1, superseded)
UNREPRESENTED_ECONOMIC_COMPONENTS   (frozen)
```

The dataclass field and the JSON key are `unrepresented_economic_components`.
The API was renamed rather than aliased, deliberately and before freeze: an
alias would have carried a misleading name into the frozen contract
permanently.

The three groups are pairwise disjoint and their union equals
`UNREPRESENTED_ECONOMIC_COMPONENTS`, asserted by test. Spread and slippage are
asserted **absent** from the line that states a direction.

## H. No Universal Favourable-Bias Claim

The original candidate claimed every result is "systematically more favourable
than a real economic outcome". **That is false and is retracted.** A dividend on
a long position **raises** the real outcome, corporate actions move it either
way, and tax effects are jurisdiction-dependent.

The frozen statement is that a result is **NOT a complete economic outcome**
and that the **direction of the total omitted effect is NOT generally
knowable**. No universal bound in either direction is claimed.

## I. No Aggregate, Percentage, Win Rate or Unrealized Result

No aggregate across positions, no return percentage and no win rate is emitted.
Each would be a performance claim this milestone has no authority to make, and
each is asserted absent by test.

No unrealized figure is computed for a still-open quantity, because the
platform holds no authoritative current market price. A partly-exited
position's result covers the **exited quantity only** and is never
extrapolated.

## J. The M079 Firewall Is Mandatory and Frozen Into M080's Meaning

`recorded_at <= K` is M079's `events_known_by`, used unmodified. **No assertion
with `recorded_at` greater than the knowledge cutoff may influence any
historical output** - not a value, not a status, not a count, not an ordering,
not a limitation.

The guarantee is structural, not disciplinary: the report builder is never
handed the unfiltered event set. Proven by appending post-cutoff rows to a live
PostgreSQL database between two reads and asserting the object, the text and
the JSON are byte-identical, then advancing the cutoff and watching the same
rows become visible.

M080 adds exactly one thing to the chain - the arithmetic. The effective filter
and the fold remain frozen M076's; open-versus-closed is never decided here;
lineage projection remains M078's; the session join remains M078's and is out
of scope.

## K. EXIT_QUANTITY_UNRECONCILED Remains Explicitly Partial

The design review found this pre-implementation, by executing frozen M076
rather than by reading it. M076 **derives** a `CLOSED` event's quantity at
append time from the full history and persists that derived value. A
knowledge-filtered prefix can therefore fold **coherently** - M079 reporting
`KNOWN_CLOSED` - while its visible exits account for only part of the opened
quantity.

M080 reconciles from visible evidence alone:

```
unaccounted = opened_quantity - exited_quantity - still_open
```

and reports `EXIT_QUANTITY_UNRECONCILED` when that is non-zero. The shortfall
was proven never negative across 1521 cutoff pairs.

Showing the arithmetic on the visible exits in this state is authorized,
**provided the result remains explicitly labelled as NOT the whole position**.
It is: every result line names the exact exited quantity it covers, and the
three coverage phrasings are asserted distinct - a defect I found by execution
(R01) was precisely that three result lines had been word-for-word identical
whether a position was fully exited, sixty percent still open, or missing four
of ten units.

`EXIT_QUANTITY_UNRECONCILED` is common at early cutoffs and is **not**
corruption. As in M079, M080 does not diagnose an unresolved sequence: it
cannot know from one cutoff's evidence whether a non-folding prefix is
temporary incompleteness or ledger incoherence, and it declines to guess.

## L. All Owner-Review Retractions Remain Visible

Nothing was deleted and no historical incorrect verdict was silently rewritten.

- Design-review verdicts **E04, E06, E07, E12 and H08** are marked
  `RETRACTED` in place, originals preserved, with the reason their test domain
  was too weak recorded.
- Implementation-review **R-H05** is marked `RETRACTED`; **R-L05** is annotated
  with the rename.
- Correction pass 1's own vocabulary - `EXCLUDED_ECONOMIC_COMPONENTS`,
  `EXCLUDED_FRICTION_COMPONENTS`, `EXCLUDED_NON_DIRECTIONAL_COMPONENTS` - is
  marked **superseded in place** by correction pass 2 rather than rewritten.
- The pre-fix rendered output quoted in R01 is kept verbatim and annotated as
  since corrected.

Where two passes disagree, the later one governs, and the earlier statement
carries the finding that superseded it.

## Implementation Lineage - Recorded Honestly

```
initial implementation      18b8e90
  -> external review        d8c8244
  -> owner correction pass 1  e0510b0   (findings 1 and 2)
  -> owner correction pass 2  51d8128   (findings 3 and 4, plus stale-claim audit)
```

The corrections are not collapsed and not hidden. The owner found **four**
blocking defects across two review passes that my own adversarial reviews were
too weak to catch. That is the honest record of this milestone.

## Errors of My Own, Recorded

An accurate freeze record includes the reviewer's own failures.

- **Six** of my own probe assertions across the three passes were wrong - wrong
  assertions, not wrong code. The most dangerous was my first "independent"
  check of finding 1: it computed the control with a `Decimal` **division**,
  which is equally context-sensitive, so the control rounded exactly like the
  code and printed agreement, **appearing to refute the owner**. Only pure
  integer arithmetic settled it.
- **One reconciliation record in my own evidence was false**: the first
  stale-claim sweep listed the `reality-gate.md` closing paragraph as fixed
  while that paragraph was still live.
- That same first sweep searched only under `external-review/` and therefore
  **missed the frozen-facing root design document**, which still carried the
  retracted claims into the document a freeze would seal.

The corrected branch-wide audit found and reconciled **22** active stale
claims. Both errors above are named in the stale-claims table rather than
quietly replaced.

- An intermittent M077 test failure, observed once after a cold database start
  and never reproduced across five subsequent runs, remains recorded
  **unexplained** rather than buried.

## Canonical Result

The mandated lifecycle `OPENED q=10 p=100`, `REDUCED q=4 p=110`,
`CLOSED q=6 p=90` yields:

```
AAPL position=POS-1 FULLY_EXITED_ASSERTED
  opened=10 exited=10 still_open=0 unaccounted=0
  asserted entry price=100 entry cost for exited=1000 exit consideration=980
  ASSERTED ROUND-TRIP RESULT on all 10 exited unit(s), in unspecified asserted
  price units, with the economic components above not separately represented: -20
```

`(4 x 110 + 6 x 90) - (10 x 100) = -20`. The corrections changed the honesty
surface, not the arithmetic.

## Temporal Vocabulary

M080 extends the chain by one term and invents no other:

```
STATE_AT(t)                            M076 and earlier
HISTORICAL_EVIDENCE_AVAILABLE_AT(t)    M074
RECOMMENDATION_SET_FEASIBILITY_AT(t)   M075
OPERATOR_ASSERTED_POSITION_STATE_AT(t) M076
PORTFOLIO_AWARE_FEASIBILITY_AT(t)      M077
FOLLOW_THROUGH_OBSERVED_AT(t)          M078
OPERATOR_EVIDENCE_AVAILABLE_AT(E,K)    M079
OPERATOR_ASSERTED_ROUND_TRIP_RESULT_AT(E,K)   M080
```

Both cutoffs are required on the CLI with **no default on either dimension**, so
a caller cannot silently obtain "now" for a historical question.

## Adversarial Review

| Pass | Attacks | Outcome |
|---|---|---|
| Hostile design review | 137 | 46 corrections before any code; T07 found by executing frozen M076 |
| Hostile implementation review, cumulative across three passes | 188 | 1 defect I found (R01) + the 4 the owner found |

## Validation Evidence

| Suite | Result |
|---|---|
| M080 unit | 98 passed |
| M080 PostgreSQL integration | 15 passed |
| M080 fresh second pass | 4 passed, from a dropped and recreated database |
| M076-M080 chain | 407 passed |
| Full regression, candidate | 24 failed, 2575 passed, 14 skipped, 44 errors |
| Full regression, baseline `0e73e0b`, same working tree, same PostgreSQL | identical |
| Failing-test-id diff | **empty** - 68 ids each side, `diff` clean |

Regression was measured by checking out the baseline SHA in the **same** working
tree and diffing sorted failing-test-id lists, not by comparing counts.

Gates: `ruff check` clean; `ruff format --check` 596 files; `python -m mypy`
clean on 302 source files; `compileall` clean; `tools/check_architecture.py .`
exit 0; the negative architecture fixture still exits non-zero on 32 seeded
violations; `pip-audit` reports no known vulnerabilities; the secret scan
reports 0 findings over 1084 targets; `python -m build` produces an sdist and a
wheel.

**No `# type: ignore`, no concealing `# noqa`, no gate suppression.** One mypy
finding arose during the exactness fix (`int ** int` is typed `Any`) and was
fixed by digit-string padding rather than suppressed.

## The Two-Database Proof

A second PostgreSQL database was created empty and migrated from scratch, then
the same query was run against both. The proof needed one correction of its
own: the probe fixture initially left `EMPIRICAL_PLATFORM_POSTGRES_DATABASE`
set across the yield, so the test compared a database with itself. The override
is now scoped to the alembic call alone.

## Fresh Second Verification Pass

Same agent, so **not** an independent review. A genuinely fresh database
(`m080_second_pass`, dropped and recreated empty for the freeze run),
deliberately different instruments, different governance ids, different
timestamps, three exits on one position rather than two, prices at both ends of
the frozen `NUMERIC(20, 6)` domain within a single position, and **reversed
recording order** so that recording order cannot be what makes the arithmetic
work.

## Frozen Preservation

Verified byte-identical against baseline `0e73e0b` after the merge:

| Milestone | Module | Freeze record |
|---|---|---|
| M075 | `same_day_capital_feasibility.py` | identical |
| M076 | `operator_position_ledger.py` | identical |
| M077 | `portfolio_aware_capital_feasibility.py` | identical |
| M078 | `research_decision_follow_through.py` | identical |
| M079 | `operator_evidence_availability.py` | identical |

Every M075-M079 macro milestone freeze record is byte-identical. Zero new
domain aggregate, zero new PostgreSQL schema, zero new migration, zero new
repository. The only non-M080 file this milestone touches is `pyproject.toml`,
and only to register M080's own console entry point.

## M062 / M064 / M065 Seal Debt - Not Repaired

The pre-existing CRLF byte-seal debt in M062, M064 and M065 is untouched, as is
the M063 exceptional byte-seal reconciliation record. M080 does not repair it
and does not pretend it is absent.

## Known Limitations

Sixteen, recorded in full in `external-review/MILESTONE-080/known-limitations.md`.
The load-bearing ones: every figure is arithmetic over assertions, not a
measurement; economic components are unrepresented in three groups with
different epistemic status; no unrealized figure exists; no aggregate,
percentage or win rate is emitted; `EXIT_QUANTITY_UNRECONCILED` is common at
early cutoffs and is not corruption; `recorded_at` is operator-supplied and not
enforced as a system clock; there is no index on `recorded_at` and filtering is
in memory through the existing `list_all()`, a deliberate deferral inherited
from M079; a whole-ledger fold is not used, so incoherence *between* positions
is not detected; quantities are integers because frozen M076 types them so;
exactness rests on integer arithmetic rather than a Decimal context; and there
is no currency or denomination authority.

## Claim Honesty

M080 makes no claim of profitability, live-trading readiness, broker readiness,
order execution, fills, market valuation, realized or unrealized P&L,
investment performance, or investment advice. It computes arithmetic over what
an operator asserted, for the quantity they assert they exited, from evidence
the ledger records as having been recorded by an explicit knowledge cutoff - a
statement about records, not about markets, money or conduct.

## Owner Approval

All phases of the M080 mission specification are complete: repository truth
independently verified from git and the checkpoint rather than trusted from the
mission text; M075-M079 reconstructed from their frozen records; the gap proved
by reading frozen source and showing every exit price was write-only; six
candidates ranked including the mandatory A-F set, with the authority question
answered directly rather than deferred; a design that survived 137 attacks with
46 pre-implementation corrections, including T07 found by executing frozen M076
rather than reading it; a minimal additive implementation with zero new schema;
real-PostgreSQL evidence over the mandated lifecycle cross-checked against raw
SQL; a double-database leak test; a 188-attack cumulative implementation review;
a fresh second pass on a new database with reversed recording order; a full
regression proving zero new failures by diffing failing-test-id lists against a
measured baseline; **two owner review passes that found four real defects -
inexact context-sensitive arithmetic at the maximum persistence-valid quantity,
a false universal favourable-bias claim, an absent denomination authority, and
an unprovable exclusion claim for spread and slippage - each corrected
structurally rather than textually**; and a branch-wide stale-claim audit that
reconciled 22 active stale claims, including two errors of my own that are named
rather than replaced.

**Freeze declaration:** `M080 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M080 APPROVED_AND_FROZEN`.

## Deferred / M080 Boundary

Explicitly out of scope and not built: any aggregate, percentage, win rate or
portfolio-level figure; any unrealized or mark-to-market value; any currency or
denomination; any cost, fee, commission, tax or dividend model; any benchmark,
quoted, intended or arrival price; any execution-quality measure; profitability;
calibration or decision-effectiveness scoring; broker integration, confirmation
or reconciliation; forward observation primitives; cross-session exposure
evolution; judgement of operator conduct; causal claims; predictive claims; any
system-assigned or independently attested receipt time; an index on
`recorded_at` or a query-side knowledge filter; a whole-ledger cross-position
fold; modification of M070, M075, M076, M077, M078 or M079; any new PostgreSQL
table, column or migration; any repair of the M062/M064/M065 seal debt.
**MILESTONE-081 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-081 -- recommendation only; not started as part of M080.
