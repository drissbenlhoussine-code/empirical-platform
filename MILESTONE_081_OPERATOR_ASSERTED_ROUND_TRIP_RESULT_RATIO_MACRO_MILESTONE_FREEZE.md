# MILESTONE-081 - Operator-Asserted Round-Trip Result Ratio - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M081 baseline
`43eb2c3defdc2964af45be5eaa5c3789743e3475` (the M080 Owner Freeze
hash-recording HEAD; M080 fully `APPROVED_AND_FROZEN`), independently
re-verified from git and from `PROJECT_CHECKPOINT.md` at mission start rather
than taken from the mission text. Delivered through pull request #11,
owner-approved at head `9bea332c2e5cb54ba1e46bb92433cf87447d128d` with the
`foundation` workflow green on that exact SHA, and merged into `master` as
`63456bbc04f7a4c4b2bf9fb3484038fdbfbdc81d`.

The pull request was merged with a true merge commit. **All five commits are
preserved and none was squashed away:**

| Commit | What it is |
|---|---|
| `135622be7aecfe1a69909497a944ce1179b9051d` | the implementation |
| `93d31922019dfd0b15714bb18cfdeae3bf3dd436` | the external review evidence package |
| `99322aa42d26939ad463107cbb546aa39f58322b` | correction: the denomination denial printed twice |
| `9f68635009224a7b090d9ca6f3565e36b66857c4` | owner correction: tiny-ratio sign, and the retracted non-recoverability claim |
| `9bea332c2e5cb54ba1e46bb92433cf87447d128d` | final evidence consistency cleanup |

Scope, the gap, seven ranked candidates, semantics, non-goals and the
pre-implementation adversarial design review are recorded in
`MILESTONE_081_OPERATOR_ASSERTED_ROUND_TRIP_RESULT_RATIO_SCOPE_AND_DESIGN.md`.
The eleven-file external review package is under `external-review/MILESTONE-081/`.

All evidence in this record - including every PostgreSQL result - was executed
in a Linux container holding a fresh clone of this repository, against a real
PostgreSQL 16 server, not simulated.

## Why M081 Exists

M080 closed an arithmetic gap and, in closing it, **opened a comparison hazard
of its own**. It emits a per-position monetary value while forbidding a reader
to combine two of them, because no currency is persisted on an M076 event. A
reader asking "which of these two positions did better" therefore had exactly
one option - divide the money themselves - and that is precisely the
unsupported act M080's own denomination limitation forbids.

M081 supplies the one comparison primitive that is provably safe, and removes
the unsafe one from the artifact.

## The Rejection That Decided The Milestone

The first candidate considered was a **denomination / currency authority**, and
it was **rejected rather than invented**. Searched exhaustively:

| Source | Currency? |
|---|---|
| M076 `operator_position_event` | **none** |
| `InstrumentMaster` - the natural place | **none**: `instrument_id`, `canonical_symbol`, `instrument_type`, `exchange_or_venue`, `external_identifier` |
| M060 `position_plan` | **zero** occurrences of the word |
| M067 `portfolio_capital_policy` | has `currency`, but it denominates **a simulated study's capital policy**, not an operator's asserted execution price, and is not joinable to an M076 event |

**The platform has no instrument-level quote-currency authority.** Building that
candidate would have required inventing the authority or amending frozen M076.
So the milestone that *needs* no currency was built instead.

An R-multiple denominator from M060 sizing was rejected on four independent
grounds, the first being that plan amounts are denominated in the operator's
supplied **account-equity** units, which nothing establishes are the ledger's
units - the division would produce a number that *looks* dimensionless and is
not.

## A. Arithmetic On Assertions, Not Measured Investment Performance

Every figure M081 emits is a ratio of arithmetic over numbers a human typed into
a ledger. There is no broker, no confirmation, no reconciliation, no fill, no
market data, and no evidence that any trade occurred or occurred at the stated
price.

M081 is **NOT** a return, total return, ROI, profit percentage, investment
performance, a market return, a tax result, or a verified outcome.

Twenty-four forbidden tokens - `ROI`, `RETURN`, `TOTAL_RETURN`,
`INVESTMENT_RETURN`, `PROFIT_PERCENTAGE`, `PERFORMANCE`,
`PERFORMANCE_PERCENTAGE`, `GAIN_PERCENT`, `WIN_RATE`, `HIT_RATE`, `EXPECTANCY`,
`ACCURACY`, `ALPHA`, `EDGE`, `YIELD`, `R_MULTIPLE`, `PNL`, `PROFIT`, `REALIZED`,
`UNREALIZED`, `BROKER`, `FILL`, `CASH_PROCEEDS`, `MARKET_VALUE` - are asserted
absent from every field name, enum member and JSON key, with **word-boundary**
matching.

## B. The Ratio Authority Is Per Position Only

```
                asserted_round_trip_result
    ratio  =  ----------------------------------------
              asserted_entry_cost_for_exited_quantity
```

for exactly one position. There is no cross-position quantity of any kind.

## C. Numerator And Denominator Both Come From Frozen M080

M081 is a **read-only composition of one frozen public contract**. It calls
`build_asserted_round_trip_report` and reads two fields off each returned entry.

It does **not** re-fold the M076 event stream, does **not** re-derive
open-versus-closed, does **not** re-apply the knowledge filter, and does **not**
reimplement M080's arithmetic. M080's money is rendered as exact decimal strings
by integer `divmod`; that rendering is injective, so M081 **inverts** it rather
than recomputing. The inversion pads the fraction to exactly six digits - a
naive point-strip is wrong and was caught in design review - and is asserted
against M080's own renderer over 500 random scaled integers.

## D. Denomination Cancels Only Within The Same Position

The cancellation is exact rather than approximate. Both quantities are integer
multiples of `10^-6` of the *same* unspecified asserted price unit, for the
*same* position, from the *same* events:

```
ratio = (R x 10^-6) / (C x 10^-6) = R / C      [dimensionless]
```

The scale cancels identically, so the ratio is the exact quotient of two
integers.

## E. No Currency Authority Is Introduced

M081 establishes no currency and invents none. M080's
`ASSERTED_PRICE_DENOMINATION_LIMITATION` is carried verbatim on every report
shape. The cancellation in D does **not** retroactively denominate the
underlying money.

## F. The Exact Reduced Rational Is Authoritative

Stored and compared as a pair of Python integers, gcd-reduced, sign on the
numerator. Never a float, never a `Decimal`: the module body contains no
`float(`, no `Decimal(`, no `quantize`, no `normalize`, no `scaleb` and no
`getcontext`. Verified identical under ambient precisions 1, 2, 5, 9, 28, 60 and
200 and under `ROUND_UP`, `ROUND_FLOOR` and `ROUND_CEILING`.

Examples of the authoritative form: `1/3`, `-3/8`, `2`, `0`.

## G. The Decimal Text Is Secondary And Explicitly Approximate

Six places, computed by **integer division**, **truncated toward zero**, and
prefixed `~` whenever it is not exact. Each entry additionally carries
`ratio_approximation_is_exact`.

Truncation toward zero was chosen deliberately over `ROUND_HALF_EVEN` because it
guarantees `|approximation| <= |exact|`, so the approximation can never show a
magnitude the ledger's arithmetic cannot produce. That was implementation defect
**R01**: half-even rendered `-1` at the `NUMERIC(20,6)` boundary - a value
section I proves unreachable - at the input most likely to be quoted.

## H. Tiny Non-Zero Ratios Preserve Their Sign

Truncation toward zero has one degenerate case, and the first implementation got
it wrong. A **non-zero** ratio whose magnitude is below `10^-6` truncates to a
quotient of zero, and the sign was applied only when the quotient was non-zero.
So `-1/2000000` - reachable from an ordinary ledger of two units opened at `1`
and exited at `1` and `0.999999` - rendered `~0`, **erasing** the sign. Worse,
`+1/10000000` rendered the identical string, so a tiny gain and a tiny loss were
indistinguishable.

Raising the precision was **rejected**: every precision has the same degenerate
case, so it moves the boundary rather than removing it. Instead, when the
magnitude truncates away entirely, the renderer states the **bound it actually
knows**:

| exact value | rendering |
|---|---|
| `< 0`, magnitude `< 10^-6` | `>-0.000001 and <0` |
| `> 0`, magnitude `< 10^-6` | `>0 and <0.000001` |
| exactly `0` | `0`, `is_exact=True` |

A signed zero (`~-0`) was considered and rejected: `-0` reads as negative zero,
and the value in that branch is never zero. **The approximation never erases the
sign of a non-zero exact ratio.**

## I. The Ratio Is Strictly Greater Than -1, Always

Proved from frozen M076's `asserted_price > 0` and positive integer quantities,
not guarded:

- the denominator is `exited_quantity x entry_price`, hence **strictly
  positive**, so **division by zero is unreachable**. There is no guard because
  none can be reached.
- exit consideration is a sum of strictly positive terms, so
  `R = consideration - C > -C`, hence **`ratio > -1` always and strictly**.

A ratio of exactly `-1` - a total loss - would require an asserted exit price of
zero, which M076 rejects. Probed over 200000 randomized valid inputs; the
minimum observed was `-0.99999178`.

## J. No Aggregate, Average, Percentage, Win Rate Or Portfolio Result

None is emitted, and none may be added. No sum, mean, median, distribution,
best, worst, count of positive ratios, or portfolio figure. **No percentage
rendering is authorized**: no `%` sign appears in the text or the JSON, because
a percentage reads as a return.

Counts **by status** remain, exactly as M080 already emits them, because
counting how many positions are fully exited is a statement about evidence, not
about outcomes.

The justification for refusing even a dimensionless aggregate: averaging would
weight a one-unit exit equally with a ten-thousand-unit exit; a value-weighted
average would require summing money across unspecified denominations, which the
M080 freeze forbids; and the population is one the operator self-selected by
choosing what to record.

## K. Partial Exits Cover The Exited Quantity Only

The denominator is the asserted entry cost **of the exited quantity**, never of
the whole position. The worked case, verified in unit tests and against
PostgreSQL:

```
OPENED 10 @ 100, REDUCED 1 @ 200      ->  ratio = 1
a whole-position denominator would give 1/10, a DIFFERENT question
```

Every rendered ratio states the exited quantity it covers and the still-open
quantity beside it. A partial-exit ratio is **not** a whole-position result and
says nothing about the eventual outcome of the quantity still open.

## L. An Open Position With No Asserted Exit Gets No Ratio

Not zero. Not `0%`. Not break-even. Not flat. Not omitted from the report. The
position appears with status `NO_EXIT_ASSERTED_YET` and an explicit absence
reason.

## M. The M079 Knowledge-Time Firewall Remains Mandatory

**No event with `recorded_at` greater than the knowledge cutoff may influence any
M081 output** - not a value, not a status, not a count, not an ordering, not a
limitation.

M081 introduces **no** temporal logic and never reads a timestamp. It passes the
same `(effective_as_of, knowledge_as_of)` pair to M080 unchanged, so the firewall
is inherited **structurally**: there is no code path by which post-`K` evidence
could reach a ratio. Proved across **two real databases** carrying identical
rows up to `K` and radically different post-`K` futures: at `K` the report
objects, the rendered text and the JSON are all identical; once `K` advances they
genuinely differ.

Both cutoffs remain required on the CLI with **no default on either dimension**.

Temporal vocabulary, extended by exactly one term:

```
OPERATOR_ASSERTED_ROUND_TRIP_RESULT_AT(E,K)         M080
OPERATOR_ASSERTED_ROUND_TRIP_RESULT_RATIO_AT(E,K)   M081
```

## N. Economic Comparability Is NOT Guaranteed By Dimensionlessness

Two ratios are **arithmetically** comparable - both are unitless. They are **not
necessarily economically** comparable, and the artifact says so on every report.

Denomination cancels; economics does not. Two positions may differ in which
unrepresented components apply, and spread and slippage remain **not claimed
excluded** exactly as M080 froze. A larger ratio means only that the operator's
asserted prices imply a larger arithmetic ratio.

No annualization and no time-weighting: holding period is not represented at all.

## O. gcd Reduction Is Normalization Only, Not Confidentiality

Reduction exists so that `4/8` and `1/2` are one value. It is **not** a secrecy
mechanism, **not** an information-destruction mechanism, and **not** a guarantee
that monetary magnitude cannot be inferred.

This corrects a claim this milestone originally made. Owner review supplied the
counterexample:

```
OPENED 1 @ 0.000003, CLOSED 1 @ 0.000004
scaled operands 1 and 3, gcd = 1  ->  reduction changes NOTHING
M081 emits 1/3, whose numerator and denominator ARE the scaled operands
```

M080's scale is publicly fixed at `10^-6`, so in the coprime case the money reads
straight off the ratio. The original claim generalised from one convenient
example (`500/1000 -> 1/2`) without ever testing coprime operands.

## P. The Non-Monetary Boundary Is Semantic, Not Information-Theoretic

The frozen wording, approved by the Owner:

> **M081 exposes no field semantically labelled or authoritative as a monetary
> amount and provides no monetary aggregate.**

This is **not** an information-theoretic confidentiality claim. The banner states
so explicitly: it does *not* claim the numeric pair can never reveal anything
about the underlying M080 operands, because when those operands are already
coprime the reduced pair coincides with them.

A reader who wants the money runs M080, which carries its own denomination
banner.

## Q. No Denomination Inference From Symbol Or Exchange

Nothing is derived from `instrument_symbol`, exchange, venue, country or asset
class. `AAPL`, `XAU`, `BTC`, `7203.T`, `ZZZZ`, `EURUSD` and `GBP.L` all render
identically clean - a currency token appears nowhere outside the explicit
denials and the operator's own symbol echoed back.

## R. Owner Corrections And Retractions Remain Visible

Nothing was rewritten out of the evidence package. Preserved in place, each with
the finding that superseded it:

| # | Correction | Where preserved |
|---|---|---|
| 1 | **R01** - the approximation reached `-1` at the boundary | implementation review; the code docstring records the defect and why truncation was chosen |
| 2 | **R02** - the denomination denial printed twice | implementation review; found by running the CLI end-to-end |
| 3 | **Owner finding 1** - tiny negative sign erasure | implementation review, with the eleven attacks and why the R01 tests missed it |
| 4 | **Owner finding 2** - the false monetary non-recoverability claim | **D-F04 marked PARTIALLY RETRACTED in place** in nine locations, struck through with the counterexample beside it |
| 5 | **Owner re-review** - stale test docstring, over-strong test name, and a banner stronger than its own limitation | implementation review, and in the test docstrings themselves |

Also preserved: **ten wrong probe assertions of my own**, including a
forbidden-token search that reported `EDGE` inside `KNOWLEDGE_AS_OF`, a currency
search that flagged the artifact's own denial, and a wrong expected value in my
own attack harness. None was a code defect. An attack that fails for the wrong
reason is as misleading as a test that passes for the wrong one.

## Implementation Lineage - Recorded Honestly

```
initial implementation            135622b
  -> external review              93d3192
  -> owner correction pass        99322aa, 9f68635
  -> final evidence consistency cleanup   9bea332
```

The corrections are not collapsed and not hidden. My own 232 executed attacks
found two defects; **the Owner found two more they were too weak to catch, and a
re-review found a third class - claims living in test names and docstrings that
my sweeps had never searched.**

## Canonical Results

```
OPENED 10 @ 100, REDUCED 4 @ 110, CLOSED 6 @ 90
  -> exact = -1/50   approx = -0.02

OPENED 10 @ 100, REDUCED 1 @ 200            (partial)
  -> exact = 1       on the 1 exited unit ONLY

OPENED 2 @ 1, REDUCED 1 @ 1, CLOSED 1 @ 0.999999   (tiny negative)
  -> exact = -1/2000000   approx = >-0.000001 and <0

max INTEGER quantity at max NUMERIC(20,6) price, exited at 0.000001
  -> exact = -99999999999999999998/99999999999999999999
     approx = ~-0.999999          (never the unreachable -1)
```

## Adversarial Review

| Pass | Attacks | Outcome |
|---|---|---|
| Hostile design review | **156** | 9 findings, all corrected before any code |
| Hostile implementation review | **232 executed** | R01 and R02, plus the Owner's two findings and the re-review cleanup |

## Validation Evidence

| Suite | Result |
|---|---|
| M081 unit | **101 passed** |
| M081 PostgreSQL integration | **24 passed** |
| M081 fresh second pass | **4 passed**, dropped-and-recreated database |
| M076-M081 chain | **536 passed** |

| Full regression vs baseline `43eb2c3`, same tree, same PostgreSQL | Baseline | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2575 passed, 44 errors | 24 failed, **2704** passed, 44 errors | **empty** - 68 ids each side |
| PostgreSQL **off** | 8 failed, 2184 passed, 12 errors | 8 failed, **2285** passed, 12 errors | **empty** - 20 ids each side |

Regression was measured by checking out the baseline SHA in the **same** working
tree and diffing sorted failing-test-id lists, not by comparing counts.

All seven mandated PostgreSQL scenarios A-G were built against real rows, and
every ratio was cross-checked against a numerator and denominator recomputed
**independently from raw SQL** using pure integer arithmetic, without touching
M080's or M081's helpers.

Gates: `compileall` clean; `ruff check` clean; `ruff format --check` 603 files;
`python -m mypy` clean on 306 source files; architecture exit 0; the negative
fixture still exits non-zero on 32 seeded violations; `pip-audit` reports no
known vulnerabilities; the secret scan reports 0 findings; `python -m build`
produces an sdist and a wheel which imports in a clean Python 3.13 venv with the
console entry point registered.

**No `# type: ignore`, no concealing `# noqa`, no gate suppression** in any M081
module.

## Frozen Preservation

Verified byte-identical against baseline `43eb2c3` after the merge:

| Milestone | Module | Freeze record |
|---|---|---|
| M075 | `same_day_capital_feasibility.py` | identical |
| M076 | `operator_position_ledger.py` | identical |
| M077 | `portfolio_aware_capital_feasibility.py` | identical |
| M078 | `research_decision_follow_through.py` | identical |
| M079 | `operator_evidence_availability.py` | identical |
| M080 | `operator_asserted_round_trip.py` | identical |

Every M075-M080 macro milestone freeze record is byte-identical. Zero new domain
aggregate, zero new PostgreSQL schema, zero new migration, zero new repository.
The only non-M081 file this milestone touches is `pyproject.toml`, and only to
register M081's own console entry point.

## M062 / M064 / M065 Seal Debt - Not Repaired

The pre-existing CRLF byte-seal debt in M062, M064 and M065 is untouched, as is
the M063 exceptional byte-seal reconciliation record, which is byte-identical.

## Known Limitations

Eighteen, recorded in full in `external-review/MILESTONE-081/known-limitations.md`.

## Claim Honesty

M081 makes no claim of profitability, live-trading readiness, broker readiness,
order execution, fills, market valuation, realized or unrealized P&L, investment
performance, or investment advice. It reports a unitless ratio derived from
unverified assertions, for the quantity the operator says they exited, from
evidence recorded by an explicit knowledge cutoff.

## Owner Approval

All phases of the M081 mission specification are complete: repository truth
independently verified; the M076-M080 authority chain reconstructed from code;
seven candidates ranked on twelve criteria with a currency authority **rejected
rather than invented**; a design that survived 137+19 attacks with 9 corrections
before any code; a minimal additive read-only composition with zero new schema;
real-PostgreSQL evidence over all seven mandated scenarios cross-checked against
raw SQL; a cross-denomination attack; a double-database firewall proof; a
232-attack implementation review; a fresh second pass on a new database; a full
regression proving zero new failures by diffing failing-test-id lists in both
PostgreSQL modes; **two owner review passes that found three real defect classes
my attacks were too weak to catch - a sign erased below the approximation scale,
a false claim of monetary non-recoverability, and stale claims living in test
names and docstrings my sweeps had never searched - each corrected structurally
and each preserved visibly.**

**Freeze declaration:** `M081 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M081 APPROVED_AND_FROZEN`.

## Deferred / M081 Boundary

Explicitly out of scope and not built: any aggregate of ratios; any average,
median, distribution, best, worst, win rate or positive-ratio rate; any
percentage rendering; any portfolio result; any monetary aggregation; any
currency or denomination authority; any join to M060 sizing; any R-multiple; any
annualization or time-weighting; any system-assigned receipt time; any new
PostgreSQL table, column or migration; modification of M070 or M075-M080; any
repair of the M062/M064/M065 seal debt. **MILESTONE-082 was explicitly NOT
built.**

## Next Permitted Action

MILESTONE-082 -- recommendation only; not started as part of M081.
