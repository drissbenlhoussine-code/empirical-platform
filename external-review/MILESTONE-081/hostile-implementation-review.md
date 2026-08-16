# M081 - Hostile Implementation Review

**232 attacks executed against the running code, the usecase layer, the CLI, the
test suite itself and real PostgreSQL.** Not reasoned about - executed, with
results captured from the interpreter.

**2 defects found by my own execution (R01, R02); the Owner found **two more** that 232 attacks missed (findings 1 and 2).** **Ten of my own probe assertions were
wrong** and are recorded below; none of them was a code defect, and an attack
that fails for the wrong reason is as misleading as a test that passes for the
wrong one.

| Batch | Attacks | Passed |
|---|---|---|
| Ratio mathematics, inversion, money-absence, aggregation, honesty, denomination, temporal, status, ordering, lineage, architecture | 180 | 180 |
| CLI, JSON/text, the tests themselves, packaging and repository state | 52 | 52 |
| **Total** | **232** | **232** |

---

## R01 (HIGH) - the approximation rendered a value the exact ratio cannot take

**Found by executing the persistence boundary, not by reading the code.**

```
OPENED  q=2147483647 @ 99999999999999.999999
CLOSED  q=2147483647 @ 0.000001

exact ratio          -99999999999999999998/99999999999999999999
float(exact)         -1.0
approximation, v1    -1          <-- ROUND_HALF_EVEN rounded it to the bound
```

The design already proved a ratio of exactly `-1` is **unreachable**: a total
loss would require an asserted exit price of zero, which frozen M076 rejects.
The first implementation nonetheless printed `-1` at the input most likely to be
quoted. An `is_exact=False` flag beside it was not enough - the string is what a
reader copies.

**Root cause.** `ROUND_HALF_EVEN` can round a magnitude *up*, across a bound the
exact value never reaches.

**Fix.** Rounding is now **truncation toward zero**, chosen deliberately over
half-even, because truncation guarantees `|approximation| <= |exact|` - so the
approximation can never show a magnitude the ledger's arithmetic cannot produce.
An inexact approximation additionally carries a `~` prefix so the truncation
travels with the value into JSON and into anything that quotes it.

**Regression tests.** `test_the_boundary_approximation_never_renders_the_unreachable_minus_one`
asserts both that `float()` of the value is `-1.0` and that the rendering is
`~-0.999999`; `test_the_approximation_never_exceeds_the_exact_magnitude` asserts
the truncation property over four cases including the boundary. Both also run
against real PostgreSQL rows.

---

## R02 (MEDIUM) - the most important denial was printed twice

**Found by running the CLI end-to-end against real PostgreSQL**, not by any of
the 232 structured attacks - none of which had looked at the *shape* of the
limitations list.

M081 prepended `ASSERTED_PRICE_DENOMINATION_LIMITATION` **and** carried M080's
limitations verbatim. M080 already includes that limitation, on every report
shape including the withheld one. So the denomination denial - the single most
important sentence in the artifact - appeared **twice, consecutively**, in the
text and in the JSON.

**Root cause.** An assumption that M080's limitations did not already carry it.
Never checked, because it seemed obvious that M081 would have to add its own.

**Why it matters beyond cosmetics.** A caveat repeated verbatim reads as a
formatting bug, and a reader who spots one duplicated paragraph starts skimming
the rest of them. The limitations are the part of this artifact that does the
honesty work.

**Fix.** M081 no longer adds it; M080's limitations already carry it. The unused
import was removed rather than left dangling.

**Regression test.** `test_no_limitation_is_emitted_twice`, parametrised over
both report shapes, asserts the limitation appears exactly once, that the whole
limitations tuple has no duplicates at all, and that the rendered text contains
it once.

**Recorded as a lesson about my own method:** 232 attacks all probed *content* -
is this value right, is that token absent. Not one probed *structure* - is
anything said twice. The end-to-end run found in one glance what the harness was
not shaped to see.

---

# Owner review correction pass - two findings, both real

## Owner finding 1 - a non-zero ratio below the approximation scale lost its sign

**Reproduced on a real M076-valid ledger before anything was changed.**

```
OPENED  2 @ 1          entry cost   = 2
REDUCED 1 @ 1          consideration= 1.999999
CLOSED  1 @ 0.999999   result       = -0.000001

exact ratio     -1/2000000          (negative, magnitude below 10^-6)
approximation   ~0                  <-- THE SIGN IS GONE
```

Worse than sign erasure: `+1/10000000` rendered the **identical string**, so a
tiny gain and a tiny loss were indistinguishable from each other, and both looked
like nothing happened.

**Root cause.** Truncation toward zero -- the R01 fix -- is correct, but the sign
was applied only when the truncated quotient was non-zero. For any magnitude
below `10^-RATIO_APPROXIMATION_DECIMAL_PLACES` the quotient is zero, so the sign
was dropped.

**Why the R01 regression tests did not catch it.** They asserted
`|approximation| <= |exact|`, which `~0` satisfies perfectly. The property I
tested was true; it was simply not the whole requirement.

**Fix.** Raising the precision was rejected -- it moves the boundary rather than
removing it, and every precision has this degenerate case. Instead, when the
magnitude truncates away entirely the renderer stops pretending to be a point
value and states the **bound it actually knows**:

| exact value | rendering |
|---|---|
| `< 0`, magnitude `< 10^-6` | `>-0.000001 and <0` |
| `> 0`, magnitude `< 10^-6` | `>0 and <0.000001` |
| exactly `0` | `0`, unchanged, `is_exact=True` |

A signed zero (`~-0`) was considered and rejected: `-0` reads as negative zero,
and the value in this branch is never zero -- it is a small non-zero number,
which is exactly what the bound states. The three cases are mutually distinct
strings in text and JSON alike.

| # | Owner attack | Result |
|---|---|---|
| O1-01 | `-1/10000000` | `>-0.000001 and <0` |
| O1-02 | `-1/1000000000000` | `>-0.000001 and <0` |
| O1-03 | `+1/10000000` | `>0 and <0.000001` - distinct from the negative |
| O1-04 | exact zero | `0`, `is_exact=True`, distinct from both bounds |
| O1-05 | exact `-1/2` | `-0.5`, unaffected |
| O1-06 | just above the strict `-1` boundary | `~-0.999999`, still signed |
| O1-07 | text / JSON parity | identical string in object, text and JSON |
| O1-08 | exact rational still authoritative | `-1/2000000` unchanged |
| O1-09 | ambient `Decimal` context | irrelevant - identical at precision 1, 5, 9, 28, 60 |
| O1-10 | sign preserved for every non-zero ratio | swept across six denominators spanning the boundary, both signs |
| O1-11 | against real PostgreSQL rows | cross-checked to `-1/2000000` from raw SQL |

## Owner finding 2 - "monetary magnitude is unrecoverable" was false

**The counterexample, executed:**

```
OPENED  1 @ 0.000003     scaled entry cost = 3
CLOSED  1 @ 0.000004     scaled result     = 1

gcd(1, 3) = 1   ->   reduction changes NOTHING
M081 emits 1/3, whose numerator and denominator ARE the scaled operands.
M080's scale is publicly fixed at 10^-6, so the money reads straight off it.
```

My D-F04 claim -- that gcd reduction "actively destroys the monetary magnitude"
-- is therefore **not universally true**, and I had generalised from a single
convenient example (`500/1000 -> 1/2`) without testing the coprime case.

**What is actually true, and is now what the artifact says:**

- M081 does **not semantically expose or label** any field as a monetary value;
- it emits only the exact reduced ratio and its metadata;
- a ratio does **not generally** identify a unique original scale factor, since
  infinitely many operand pairs reduce to the same rational;
- **but** when the scaled operands are already coprime the reduced pair coincides
  with them, so **no promise of non-recoverability is made**.

gcd reduction is a **normalisation**, so that `4/8` and `1/2` are one value. It
was never a sound confidentiality boundary and is no longer described as one.
The frozen requirement is **semantic non-aggregation and non-denomination** --
which the capability already satisfies, and which is unchanged by this
correction.

**No capability changed.** Only the claim.

| # | Owner attack | Result |
|---|---|---|
| O2-01 | coprime scaled pair `1/3` | reduced pair **equals** the scaled pair; asserted in unit **and** PostgreSQL tests |
| O2-02 | large coprime pair | `999993/7`, likewise unchanged by reduction |
| O2-03 | non-coprime `500000000/1000000000` | genuinely reduces to `1/2` - reduction is a real normalisation |
| O2-04 | is any field NAMED as money? | **no** - asserted over object, text and JSON key sets |
| O2-05 | is any currency invented? | **no** - unchanged from the original review |
| O2-06 | does any aggregate exist? | **no** - unchanged |
| O2-07 | does any non-recoverability claim survive? | **none** - swept branch-wide over six phrasings, asserted by test on every rendered surface |
| O2-08 | are exact ratio semantics preserved? | yes - every pre-existing ratio assertion passes unchanged |

## Owner re-review - the correction had not reached the test source

The finding-2 correction swept the rendered output, the design documents and the
evidence package. It **did not sweep the test source**, and two claims survived
there, both named by the Owner:

| Location | Was | Disposition |
|---|---|---|
| `test_the_ratio_is_reduced_so_four_eighths_and_one_half_are_one_object` docstring | "gcd reduction is applied, **which is also what destroys the money**" | **FIXED** - now "gcd reduction canonicalizes equivalent rational values", with the retraction recorded in the docstring |
| `test_the_reduced_ratio_does_not_reveal_the_monetary_magnitude` | the **name** asserted universal non-recoverability; the assertion only ever proved the mapping is many-to-one | **RENAMED** to `test_multiple_monetary_magnitudes_can_reduce_to_the_same_ratio`, with the old name and the reason recorded in the docstring. **The assertion is unchanged** - it was always valid evidence for the narrower claim |

**Why the earlier sweep missed them.** It searched rendered surfaces and prose,
on the assumption that a claim only matters where a reader sees it. A test name
and a test docstring are exactly where a future maintainer looks to learn what a
guarantee *is*, so they are load-bearing claims too. Recorded rather than quietly
fixed.

### The banner was stronger than the limitation

The corrected limitation already drew the semantic distinction. The **banner**
still said, flatly:

> ~~NO monetary value is emitted at all~~

which reads as an information-theoretic claim, and the coprime counterexample
disproves exactly that reading. **Reconciled** to match the limitation:

> M081 exposes NO field semantically labelled or authoritative as a monetary
> amount and provides NO monetary aggregate. That is a SEMANTIC boundary: it
> does NOT claim the numeric pair can never reveal anything about the underlying
> M080 operands, because when those operands are already coprime the reduced
> pair coincides with them.

**No arithmetic, temporal, schema or frozen-file change.** The production diff
contains no executable-line change at all - only banner wording - confirmed by
filtering the diff down to non-string, non-comment lines, which is empty.

| # | Owner attack | Result |
|---|---|---|
| O3-01 | stale docstring claim | **FIXED** |
| O3-02 | over-strong test name | **RENAMED**, assertion untouched |
| O3-03 | eight-term sweep across **test source** as well as prose | every occurrence classified below |
| O3-04 | any active occurrence outside a retraction record | **none** |
| O3-05 | banner stronger than the limitation | **reconciled** |
| O3-06 | production behaviour changed | **no** - wording only |

### Every occurrence of the eight swept terms, classified

| Kind | Where | Disposition |
|---|---|---|
| Active stale claim | test docstring; test name | **2 found, 2 reconciled** |
| Marked retraction (`~~...~~ RETRACTED`) | root design, snapshot, design review, reality gate | **kept** - this is the retraction record |
| Marked correction note | README, known-limitations, owner checklist | **kept** |
| Module `RETRACTED:` block | `operator_asserted_round_trip_ratio.py` docstring | **kept** |
| True corrected statement | the emitted limitation - "monetary magnitude is **NOT promised to be** unrecoverable" | **kept** - this is the current truth |
| Absence assertion | `test_no_surface_claims_monetary_magnitude_is_unrecoverable` and its forbidden-phrase list, unit and PostgreSQL | **kept** - names the phrases in order to forbid them |

---

## Ten probe errors of my own, recorded

**Six were wrong assertions in the unit suite**, all the same family - a search
that flagged the artifact's own *denial*:

1. `break-even` - the banner says "no zero, no break-even and no flat" in order
   to forbid them. Fixed by stripping the denial sentences first.
2. `total` - the banner says "NOT a total return". Fixed by checking the JSON
   **key set** rather than substring-scanning the whole payload.
3. `positive` / `win` - the banner denies emitting a "count of positive ratios".
   Same fix.
4. `asserted_round_trip_result` - matched **my own** self-describing key
   `asserted_round_trip_result_to_entry_cost_ratio_exact`. The key deliberately
   names its numerator; that is a feature. Fixed by exact key comparison.
5. `EDGE` - matched **`KNOWLEDGE_AS_OF`**. A naive substring token check reports
   a forbidden-vocabulary hit inside an ordinary field name. Fixed with
   word-boundary matching.
6. The whole banner string searched in the rendered text - the renderer splits it
   one sentence per line **by design**, so it is never contiguous.

**One in the integration suite:** the currency check split the text on
`effective_as_of`, but the limitations follow the entries and legitimately name
currencies to deny them. Fixed by stripping denials.

**Three in the attack harness itself:**

7. `R-I05` - my **expected value** was wrong. `3 @ 1000000 -> 3 @ 1000000.000003`
   gives `3/1000000000000`, not `1/1000000000000`. The code was right.
8. `R-D06`/`R-D07` - symbols `EURUSD` and `GBP.L` **contain** `EUR` and `GBP`.
   Echoing the operator's own instrument symbol is not inferring a currency.
9. `R-L03` - `position_plan` appears inside the pass-through field name
   `source_position_plan_governance_id`, which is not an import of M060.
10. `R-P08` - my "non-M081 files" filter looked for `m081`/`MILESTONE-081`, but
    the files are named `_ratio` and `MILESTONE_081_` with an underscore, so the
    filter matched none of them.

Plus two harness bugs of no consequence to the code: helper functions defined
after first use, and packaging attacks run before the work was committed so they
had nothing to diff.

---

## RATIO MATHEMATICS - 40 attacks

| # | Attack | Result |
|---|---|---|
| R-M01 | mandated lifecycle reduces to `-1/50` | yes |
| R-M02..R-M11 | `1/2`, `-3/4`, `0`, `2`, `1/3`, `2/3`, `1/7`, `1`, `1/2`, `1/1000000` | all exact |
| R-M12 | denominator `> 0` over 500 randomized valid cases | always |
| R-M13 | ratio `> -1` over 500 randomized valid cases | always |
| R-M14 | exact `-1` reachable | **no** - exit price `0` rejected by frozen M076 |
| R-M15 | negative zero | impossible - `0`, never `-0` |
| R-M16 | sign on the denominator | never |
| R-M17 | gcd reduction applied | yes - `1/2`, not `500000000/1000000000` |
| R-M18 | wildly different money gives the same ratio | yes - `2@1->1.5` and `1000@1000->1500` both `1/2` |
| R-M19 | boundary exactness | exact 20-digit rational |
| R-M20 | boundary approximation prints bare `-1` | **no** - `~-0.999999` after R01 |
| R-M21 | approximation magnitude exceeds exact, 200 randomized cases | never |
| R-M22 | inexact approximation carries `~` | always |
| R-M23 | exact approximation carries `~` | never |
| R-M24 | `float(` in the module body | absent |
| R-M25 | `Decimal(` in the module body | absent |
| R-M26 | `quantize` / `normalize` / `scaleb` | absent |
| R-M27 | `getcontext` call | absent |
| R-M28..R-M34 | ratio under ambient precision 1, 2, 5, 9, 28, 60, 200 | identical |
| R-M35..R-M37 | under `ROUND_UP`, `ROUND_FLOOR`, `ROUND_CEILING` | identical |
| R-M38 | ambient context mutated by building a report | no |
| R-M39 | three exits each contribute their own price | yes - `5/9` |
| R-M40 | very large ratio | exact `999999999999` |

## STRING INVERSION - 11 attacks

| # | Attack | Result |
|---|---|---|
| R-I01..R-I05 | round-trip at five different renderings | exact |
| R-I06 | inversion pads the fraction rather than stripping the point | explicit `ljust` |
| R-I07 | more than six decimal places | raises, naming the invariant |
| R-I08 | no-point form `100` | `100000000` |
| R-I09 | negative form `-20` | `-20000000` |
| R-I10 | six-place form `1.000001` | `1000001` |
| R-I11 | exact inverse of M080's own renderer over **500 random scaled integers** | always |

## MONEY ABSENCE - 12 attacks

| # | Attack | Result |
|---|---|---|
| R-$01..R-$04 | M080 money keys at report level | absent |
| R-$11..R-$14 | M080 money keys at entry level | absent |
| R-$20 | report dataclass has a monetary field | none |
| R-$21 | entry dataclass has a monetary field | none |
| R-$22 | the fixture's money value `-20` in the entries JSON | absent |
| R-$23 | the fixture's entry cost `1000` in the entries JSON | absent |
| R-$24 | money field labels in the text | absent |
| R-$25 | numerator is scaled money rather than reduced | reduced - `-1`, not `-20000000` |

## AGGREGATION - 15 attacks

`total`, `mean`, `average`, `median`, `sum`, `best`, `worst`, `aggregate`,
`portfolio`, `overall`, `combined`, `distribution`, `positive`, `win`,
`expectancy` - **no key at any level contains any of them.**

## HONESTY - 36 attacks

24 forbidden tokens (`ROI`, `TOTAL_RETURN`, `INVESTMENT_RETURN`,
`PROFIT_PERCENTAGE`, `PERFORMANCE_PERCENTAGE`, `GAIN_PERCENT`, `WIN_RATE`,
`HIT_RATE`, `EXPECTANCY`, `ACCURACY`, `ALPHA`, `EDGE`, `YIELD`, `R_MULTIPLE`,
`PNL`, `PROFIT`, `REALIZED`, `UNREALIZED`, `BROKER`, `FILL`, `CASH_PROCEEDS`,
`MARKET_VALUE`, `PERFORMANCE`, `RETURN`) asserted absent from every field name,
enum member and JSON key **with word-boundary matching**. No `%` sign in text or
JSON. Ten banner denials asserted present verbatim.

## DENOMINATION - 10 attacks

| # | Attack | Result |
|---|---|---|
| R-D01..R-D07 | `AAPL`, `XAU`, `BTC`, `7203.T`, `ZZZZ`, `EURUSD`, `GBP.L` | no currency token outside the explicit denials and the operator's own symbol |
| R-D08 | M080's denomination limitation carried verbatim | yes |
| R-D09 | two unknown-denomination positions combined | never - `1/2` and `1/10` stay separate |
| R-D10 | money ranks them opposite to the ratios | yes, and that is the point: `1000 > 500` while `1/10 < 1/2` |

## TEMPORAL - 13 attacks

| # | Attack | Result |
|---|---|---|
| R-T01..R-T06 | `K` at day 0, 100, 299, 300, 301, 400 | inclusive at 300, exactly as M079 |
| R-T07..R-T09 | post-`K` append changes the object / text / JSON | none of the three |
| R-T10 | module reads a timestamp itself | no - fully delegated |
| R-T11 | `now(` anywhere | absent |
| R-T12 | repeated builds differ | identical |
| R-T13 | caching between cutoffs | none |

## STATUS AND ABSENCE - 13 attacks

Open position: no ratio, explicit reason, not zero, still listed. Unresolved
sequence: no ratio, own reason. Partial exit: exited-quantity denominator,
still-open reported, and distinct coverage wording on the ratio line itself.
Counts correct. Empty and withheld reports keep the denomination limitation.

## ORDERING AND RENDERING - 8 attacks

Ordered by symbol, never by value - and the value order would genuinely differ
(`1/100` before `8` by identity; the reverse by magnitude). JSON deterministic,
text and JSON agree, no randomness, no mutable global state.

## LINEAGE - 5 attacks

Two positions citing one plan keep independent denominators (`1/2` and `-1/5`).
Citation shown, never dereferenced. No M060 or M078 import. Missing citation
tolerated.

## ARCHITECTURE - 15 attacks

No `shared.persistence` import, no re-fold, calls M080's builder, M080 constants
intact, no migration, stdlib only, frozen dataclasses with slots, both cutoffs
validated at the request boundary, handler withholds without a repository and
**propagates** database faults, no suppressions, `__all__` complete, no wall
clock.

## CLI - 13 attacks

No arguments, each cutoff missing, naive timestamp, unparseable timestamp and a
flag with no value are all rejected with a usage message. No default on either
cutoff. `entrypoints` does not import `decision_candidate`. Entry point
registered in `pyproject.toml`. JSON output sorted for determinism.

## JSON AND TEXT - 15 attacks

Serialisable, typed, deterministic; banner verbatim; no float anywhere in the
payload; `(APPROXIMATE)` marker present exactly when the value is inexact; no
trailing whitespace; withheld report renders its reason.

## THE TESTS THEMSELVES - 15 attacks

The suite asserts the `-1` bound and the no-bare-`-1` rendering. The PostgreSQL
cross-check **does not import M080's helper at all** and reads raw SQL. All seven
mandated scenarios A-G present. Double-database proof present. Cross-denomination
attack present. The second pass drops and recreates its database, scopes the env
override to the alembic call only, and uses four instruments the first suite
never touches. Token matching is word-boundary. Denials are stripped before
currency searches.

## PACKAGING AND REPOSITORY - 9 attacks

No migration. M076, M079 and M080 modules untouched. `PROJECT_CHECKPOINT.md`
untouched. No M082 file. Seal debt untouched. The only non-M081 file changed is
`pyproject.toml`. No new dependency.
