# M080 — Hostile Implementation Review

A **new** adversarial pass against the real code and real persistence
behaviour. **Not an independent review** — the same agent wrote the code.
Counts are computed programmatically from this file.

**188 attacks executed against the running code, the usecase layer and real PostgreSQL, across three Owner review passes.** 1 defect found by my own review (R01); the Owner found **four** more that my attacks were too weak to catch. **Six** of my own probe assertions were wrong, and one of my own reconciliation records was false; all seven are recorded as such below.

The unit suite passed **54/54 on its first run**. As in M078 and M079, that was
evidence the tests were not yet pointed at the right places rather than evidence
of correctness — and the review below found a real honesty defect in the
rendering that 54 green tests had not touched.

## Defect found and corrected

### R01 — the result line did not say what quantity it covered

**Attack.** Render a fully-exited position, a mostly-open one and an
unreconciled one, and read the three outputs as an operator would.

**Executed finding.** The three result lines were **word-for-word identical**
apart from the number:

```
ASSERTED ROUND-TRIP RESULT (arithmetic on assertions, costs excluded): -20   <- wording since corrected
ASSERTED ROUND-TRIP RESULT (arithmetic on assertions, costs excluded): 120
ASSERTED ROUND-TRIP RESULT (arithmetic on assertions, costs excluded): -60
```

The second covers 4 of 10 units with 6 still open. The third covers 6 of 10
units with 4 **unaccounted for**. Nothing on the line said so.

**Why that matters.** The design already carried the facts — `exited_quantity`,
`still_open_quantity` and `unaccounted_quantity` on the entry, plus a
report-level limitation. That is not sufficient, and believing it was is exactly
the failure the reality gate forbids: **the number is what gets read, quoted and
pasted into a message**, and a caveat three lines away does not travel with it. A
partial figure that reads as a whole result is a misleading number rescued by a
disclaimer.

**Fix.** The result line now states its own coverage, and the three cases are
worded distinctly:

| Status | Line reads |
|---|---|
| `FULLY_EXITED_ASSERTED` | `...on all 10 exited unit(s)...` |
| `PARTIAL_EXIT_ASSERTED` | `...on the 4 exited unit(s) ONLY; 6 still open and NOT covered...` |
| `EXIT_QUANTITY_UNRECONCILED` | `...on ONLY the 6 exited unit(s) visible here; 4 of the 10 opened are unaccounted for at this knowledge cutoff, so this is NOT the whole position's result...` |

**Regression tests.** Four, including
`test_the_three_coverage_phrasings_are_distinct`, which asserts the three lines
differ. All four fail against the pre-fix renderer.

## One correction to my own test, not to the code

`test_the_three_coverage_phrasings_are_distinct` initially failed with
`len({'OPERATOR-ASSERTED ROUND-TRIP RESULT'}) == 1`. The **assertion** was wrong,
not the renderer: `next(... if "ASSERTED ROUND-TRIP RESULT" in line)` matched the
report's **title** line, which contains that substring. The assertion now anchors
on the indented entry line. Recorded because a test that passes for the wrong
reason is worse than one that fails.

## An intermittent failure observed once, and not reproduced

Recorded rather than buried. On the **first** chain run after a cold PostgreSQL
start in this container, `test_m077_all_plans_acted_text_and_json_agree` failed
once. It then passed everywhere:

| Re-run | Result |
|---|---|
| that test in isolation | passed |
| `-k "m077 or m080"` | 39 passed |
| broad chain, run 1 | 364 passed |
| broad chain, run 2 | 364 passed |
| broad chain, run 3 | 364 passed |

It is an **M077** test, in a module M080 does not modify, exercising M072 session
seeding M080 never touches. It did not reproduce in five subsequent runs.
**It is not claimed to be explained.** The authoritative check is the full
regression failing-ID diff, which is identical to the baseline.

## Attacks executed

### A. Arithmetic

| # | Attack | Result |
|---|---|---|
| R-A01 | The mandated position `OPENED 10@100 / REDUCED 4@110 / CLOSED 6@90` | `980 − 1000 = −20`, exact |
| R-A02 | Asserted gain | `300`, positive |
| R-A03 | Asserted loss | `−300`, signed |
| R-A04 | Exact break-even | `0`, not `-0` |
| R-A05 | Several reductions, each at its own price | `3×120 + 2×80 + 5×110 = 1070` |
| R-A06 | Reduction landing exactly on zero, no `CLOSED` event | fully exited, one exit component |
| R-A07 | Entry cost uses the **exited** quantity, not the opened one | asserted on the partial case |
| R-A08 | Each exit uses **its own** price | asserted |
| R-A09 | Sum order changes the total | no — exact `Decimal` addition |
| R-A10 | Result recomputed from raw SQL columns agrees | asserted in integration |

### B. Lifecycle

| # | Attack | Result |
|---|---|---|
| R-B01 | `OPENED` only | `NO_EXIT_ASSERTED_YET`, **no** arithmetic emitted |
| R-B02 | Zero exited renders `0` instead of nothing | no — all three monetary fields are `None` |
| R-B03 | Partial exit | covers 4 of 10; `120`, not `300` |
| R-B04 | Partial result extrapolated to the open remainder | no — `100`, not `1000` |
| R-B05 | Unrealized value for the open quantity | no such field exists |
| R-B06 | Instrument mismatch inside one key | unresolved / `INSTRUMENT_MISMATCH_FOR_POSITION` |
| R-B07 | Exit visible without its opening | unresolved, `POSITION_NOT_OPEN`, no arithmetic |
| R-B08 | One unresolved position voids the report | no — per-key isolation |
| R-B09 | Every visible key appears exactly once | asserted |
| R-B10 | Counts agree with the entries | asserted |

### C. The unreconciled hazard

| # | Attack | Result |
|---|---|---|
| R-C01 | Coherent fold with a late-recorded reduction | `EXIT_QUANTITY_UNRECONCILED`, shortfall 4 |
| R-C02 | Its result covers only the visible exits | `−60`, not the full-history `−20` |
| R-C03 | It is mislabelled fully exited | no |
| R-C04 | It carries an explicit limitation | yes |
| R-C05 | It recovers once the reduction is recorded | `FULLY_EXITED_ASSERTED`, `−20` |
| R-C06 | It voids the whole report | no — a healthy position beside it is unaffected |
| R-C07 | **Can `unaccounted_quantity` go negative?** | **No — swept 39 recording times × 39 cutoffs, 1521 combinations, minimum observed 0.** Proven rather than argued: visible reductions are a subset of those the persisted `CLOSED` quantity was derived from, so the shortfall cannot be negative |
| R-C08 | Can `PARTIAL` co-occur with a non-zero shortfall | no — a shortfall requires a `CLOSED`, which forces `still_open = 0` |

### D. The knowledge firewall

| # | Attack | Result |
|---|---|---|
| R-D01 | An exit recorded after `K` changes the arithmetic | no — full object equality |
| R-D02 | …changes any single field, parametrised over 3 future shapes | no — per-field assertion |
| R-D03 | …changes the text or JSON | no — both compared |
| R-D04 | …changes the ordering, with a row that would sort first | no |
| R-D05 | `_report_from_known_evidence` can reach post-cutoff rows | no — signature and source inspected |
| R-D06 | A hidden-assertion count leaks | no such field, per M079's frozen correction |
| R-D07 | A total-ledger count leaks | no such field |
| R-D08 | Two real databases, identical `recorded_at <= K`, different futures | identical object, text and JSON |
| R-D09 | Those two databases are actually different | proven — `−100` vs `500` once `K` advances |
| R-D10 | The earlier answer is retroactively strengthened | no — re-queried at the original `K`, still identical |
| R-D11 | Appending post-cutoff rows between two reads moves the answer | no — second pass, byte-identical text |

### E. Temporal boundaries

| # | Attack | Result |
|---|---|---|
| R-E01 | `K` boundary exclusive | inclusive, correct |
| R-E02 | One microsecond past `K` | excluded |
| R-E03 | `E` boundary exclusive | inclusive, correct |
| R-E04 | Exit effective after `E`, recorded before `K` | excluded and counted |
| R-E05 | Naive `effective_as_of` | `ValueError` |
| R-E06 | Naive `knowledge_as_of` | `ValueError` |
| R-E07 | Same instant in two zones | identical answer |
| R-E08 | `K < E` | permitted, limitation named |
| R-E09 | Three cutoffs over one persisted timeline | evolves only as evidence is recorded |
| R-E10 | Raw SQL eligibility count agrees at each cutoff | 1, 2, 3 |

### F. Precision

| # | Attack | Result |
|---|---|---|
| R-F01 | Maximum `NUMERIC(20,6)` price | exact |
| R-F02 | Minimum positive price | exact, `−0.000001` |
| R-F03 | Six decimals through multiply and sum | `3.703701 / 7.037034 / 3.333333` |
| R-F04 | A `float` reaches the output | no — JSON walked recursively |
| R-F05 | Result reloaded from PostgreSQL renders differently | no |
| R-F06 | Boundary decimals at **both** ends in one position | second pass: `299999999999999.999989` |
| R-F07 | Negative-zero rendering | guarded; proven unreachable via `a − a` |
| R-F08 | Exponent form leaks into output | no — `format(..., "f")` |

### G. Lineage

| # | Attack | Result |
|---|---|---|
| R-G01 | Cited plan reported | yes, as metadata |
| R-G02 | Blank citation treated as an id | no — M078 strips it |
| R-G03 | Missing citation treated as an error | no |
| R-G04 | Two positions citing one plan merged | no — separate entries |
| R-G05 | A session membership is claimed | no — explicitly disclaimed |

### H. Honesty

| # | Attack | Result |
|---|---|---|
| R-H01 | Forbidden token in any status, field or enum | none of 13 tokens |
| R-H02 | Forbidden token in any JSON key | none |
| R-H03 | Banner states what the result is not | asserted phrase by phrase |
| R-H04 | Cost components named on every report | all 8, structured field and limitations |
| R-H05 | The cost caveat states the direction of the bias | ⚠ **RETRACTED** — the caveat asserted a universal favourable bias that does not hold, and the direction is not generally knowable. Original verdict, preserved: "more favourable than a real economic outcome" |
| R-H06 | An aggregate, win rate or return percentage exists | none |
| R-H07 | **The result line hides its own coverage** | **R01 — DEFECT, fixed** |
| R-H08 | Simulated M062/M067 `realized_pnl` conflated with this | no — named as a distinct claim in design, module docstring and reality gate |

### I. Interface and failure

| # | Attack | Result |
|---|---|---|
| R-I01 | CLI with no arguments | usage error naming the missing flag |
| R-I02 | CLI with only one cutoff | usage error naming the other |
| R-I03 | CLI with a naive timestamp | usage error demanding an offset |
| R-I04 | CLI with a garbage timestamp | usage error |
| R-I05 | CLI flag with no value | usage error |
| R-I06 | An append path reachable from the read CLI | none |
| R-I07 | Unavailable ledger renders as empty | no — `NOT_ASSESSABLE`, withheld |
| R-I08 | A database fault disguised as a soft verdict | no — propagates, matching M079 |
| R-I09 | `json.dumps` fails on the payload | no — serialises |
| R-I10 | Text renders the cost list for a withheld report | no — body skipped |

### J. Architecture and packaging

| # | Attack | Result |
|---|---|---|
| R-J01 | Architecture boundaries | exit 0 |
| R-J02 | Negative architecture fixture still fails as required | exit 1 |
| R-J03 | `ruff check` | clean after one import-order fix |
| R-J04 | `ruff format --check` | 594 files formatted |
| R-J05 | `mypy` | clean, 302 source files |
| R-J06 | A `type: ignore` or concealing `noqa` added | none |
| R-J07 | `python -m build` | sdist + wheel |
| R-J08 | Secret scan | 0 findings |
| R-J09 | `pip-audit` | no known vulnerabilities |
| R-J10 | A frozen module was modified | none — verified by diff |
| R-J11 | A migration was added | none |
| R-J12 | `__slots__` present on both dataclasses | yes |
| R-J13 | Concurrent writer during a read | consistent snapshot, barrier-synchronised |

### K. Usecase and handler layer

| # | Attack | Result |
|---|---|---|
| R-K01 | Naive `effective_as_of` reaches the domain as a data verdict | no — `ValueError` at the request boundary, M078's R03 lesson |
| R-K02 | Naive `knowledge_as_of` likewise | `ValueError` |
| R-K03 | A `None` repository renders as empty | no — `NOT_ASSESSABLE` |
| R-K04 | A database fault disguised as a soft verdict | no — `RuntimeError` propagates |
| R-K05 | An empty ledger is an error | no — `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF` |
| R-K06 | Handler carries `__slots__` | yes |
| R-K07 | Query object is mutable | no — frozen |

### L. Immutability and typing

| # | Attack | Result |
|---|---|---|
| R-L01 | The report can be mutated after construction | no — frozen |
| R-L02 | An entry can be mutated | no — frozen |
| R-L03 | `entries` is a mutable list | no — tuple |
| R-L04 | `limitations` is a mutable list | no — tuple |
| R-L05 | `excluded_cost_components` is mutable | no — tuple. ⚠ *field since renamed to `unrepresented_economic_components` by Owner findings 2 and 4* |
| R-L06 | A raw `Decimal` escapes into an entry field | no — canonical strings only |
| R-L07 | A monetary field is neither `str` nor `None` | no |
| R-L08 | A quantity field is not `int` | no |

### M. Rendering completeness

| # | Attack | Result |
|---|---|---|
| R-M01 | JSON omits a dataclass field, hiding a caveat from machine consumers | no — key set equals field set exactly |
| R-M02 | Banner missing from JSON | present |
| R-M03 | Banner missing from text | present |
| R-M04 | A cutoff missing from JSON | both present |
| R-M05 | A cutoff missing from text | both present |
| R-M06 | A limitation computed but never rendered | all rendered |
| R-M07 | JSON limitations is not a list | it is |
| R-M08 | Text lacks a trailing newline | it has one |
| R-M09 | `json.dumps(..., sort_keys=True)` fails | serialises |
| R-M10 | A withheld report still renders entries | none |
| R-M11 | A withheld report hides its reason | names `LEDGER_UNAVAILABLE` |

### N. Scale and shape

| # | Attack | Result |
|---|---|---|
| R-N01 | 50 positions, some dropped | all 50 reported |
| R-N02 | 50 positions, ordering unstable | sorted |
| R-N03 | 50 positions, counts drift from entries | sum equals 50 |
| R-N04 | 20 reductions on one position, exits miscounted | 20 |
| R-N05 | …exited quantity wrong | 20 |
| R-N06 | …arithmetic drifts over 20 summands | exact against an independently computed `Decimal` |
| R-N07 | …still-open quantity wrong | 80 |
| R-N08 | …status wrong | `PARTIAL_EXIT_ASSERTED` |

### O. Purity

| # | Attack | Result |
|---|---|---|
| R-O01 | A `float(` conversion appears | none |
| R-O02 | The module reads a clock | none |
| R-O03 | The module uses randomness | none — **the first probe for this was wrong**, matching the word "randomness" in the docstring; re-run against `import random` / `random.` and confirmed clean |
| R-O04 | The module opens a file | none |
| R-O05 | The module performs network I/O | none |
| R-O06 | A `type: ignore` was added | none |
| R-O07 | A `noqa` was added | none |
| R-O08 | The domain module imports persistence | no |
| R-O09 | `__all__` drifted from the design | exactly 8 |
| R-O10 | An export does not resolve | all resolve |

### P. Cross-milestone compatibility

| # | Attack | Result |
|---|---|---|
| R-P01 | M080 copies M076's fold instead of calling it | calls `derive_position_state`; no `_fold_one_position` copy |
| R-P02 | M080 reimplements the knowledge filter | calls `events_known_by` |
| R-P03 | M080 reimplements lineage projection | calls `cited_plan_by_position` |
| R-P04 | M080 composes M078's session audit and inherits whole-ledger voiding | it does not — design review A03 |
| R-P05 | M080 redefines M076's rejection vocabulary | no |
| R-P06 | M080 redefines M079's status vocabulary | no |
| R-P07 | `operator_position_ledger.py` modified | untouched |
| R-P08 | `same_day_capital_feasibility.py` modified | untouched |
| R-P09 | `portfolio_aware_capital_feasibility.py` modified | untouched |
| R-P10 | `research_decision_follow_through.py` modified | untouched |
| R-P11 | `operator_evidence_availability.py` modified | untouched |
| R-P12 | `PROJECT_CHECKPOINT.md` modified by this branch | untouched |
| R-P13 | A migration was added | none |
| R-P14 | M079 behaves differently once M080 is importable | identical |
| R-P15 | M076 behaves differently once M080 is importable | identical |

## Two probe errors of my own, recorded (three more follow, from a later pass)

Both were wrong **assertions**, not wrong code, and both were the same mistake —
an unanchored substring match:

1. `test_the_three_coverage_phrasings_are_distinct` matched the report **title**
   line because it contains `ASSERTED ROUND-TRIP RESULT`. Fixed by anchoring on
   the indented entry line.
2. The R-O03 purity probe matched **"randomness"** in the module docstring while
   searching for `random`. Re-run precisely against `import random` and
   `random.`; the module is clean.

They are recorded because an attack that fails for the wrong reason is as
misleading as a test that passes for the wrong reason.

---

# Owner review correction — two findings, both real

**This section supersedes design-review verdicts E04, E06, E07, E12 and H08.
Those entries are retained there, visibly retracted, not deleted.**

## Finding 1 — Decimal arithmetic was not exact for all persistence-valid inputs

### What was wrong

M080 claimed exact arithmetic, no rounding and exact reproducibility. All three
were false, and my own numeric attacks missed it because **every one of them
paired a large price with a small quantity**. None used the maximum
persistence-valid quantity.

M076 persists `quantity` as PostgreSQL `INTEGER`. `2147483647` is a legal row.
At the maximum price:

```
exact:    214748364699999999997852.516353     (30 significant digits)
produced: 214748364699999999997852.5164       (rounded to the ambient 28)
```

Two distinct defects, not one:

| # | Defect |
|---|---|
| 1a | `Decimal(quantity) * asserted_price` evaluates under the **ambient** context and rounds to its precision |
| 1b | `_money()` rendered through `Decimal.normalize()`, which **re-rounds** an exact value on the way out — so even exact arithmetic could not have been rendered faithfully |

Both made the output depend on the **caller's** precision and rounding mode,
which M080 never controlled. My first verification of this finding was itself
wrong: I "independently" recomputed the product with `Decimal(int) / Decimal(10**6)`,
which is *also* context-sensitive, so it rounded identically and appeared to
confirm the code. Only pure integer arithmetic settled it.

### The fix — exact scaled-integer arithmetic

Chosen over deriving a local `Decimal` context precision because it requires
**no precision parameter to justify**: it is exact by construction rather than
exact up to a proven bound.

The justification is a property frozen M076 already guarantees: an asserted
price carries **at most six decimal places** (validated in
`operator_position_ledger.py`, `ASSERTED_PRICE_MAX_DECIMAL_PLACES = 6`). So
every price is an exact integer multiple of `10⁻⁶`, and since quantities are
`int`, **every monetary quantity M080 computes is an integer multiple of
`10⁻⁶`**. The whole computation therefore fits in Python `int`, which is
arbitrary-precision and entirely context-free.

| Step | How |
|---|---|
| price → scaled integer | `_scaled_price()` reads `Decimal.as_tuple()` — **pure data, no Decimal operation** — and shifts by appending zero digits |
| entry cost | `exited_quantity * entry_price_scaled` (int) |
| exit consideration | `Σ event.quantity * _scaled_price(...)` (int) |
| result | integer subtraction |
| rendering | `_money_from_scaled()` — integer `divmod` and string formatting, **no Decimal at all** |

`_scaled_price` deliberately avoids `scaleb`, `quantize` and multiplication by a
power: every one of those is context-sensitive. Global `getcontext().prec` is
**not** raised and no global state is mutated.

Two incidental improvements fall out. Negative zero is now **impossible by
construction** rather than guarded, because the sign comes from an integer. And
the renderer cannot emit exponent form, because it never builds a Decimal.

### Proof

| # | Owner attack | Result |
|---|---|---|
| R-Q01 | PostgreSQL INTEGER max quantity `2147483647` | persists and computes exactly |
| R-Q02 | Maximum price `99999999999999.999999` | exact |
| R-Q03 | Minimum price `0.000001` | exact, including at INTEGER-max quantity |
| R-Q04 | Exact entry-cost boundary | `214748364699999999997852.516353` |
| R-Q05 | Exact exit-consideration boundary | `2147.483647` |
| R-Q06 | Exact negative result boundary | **`-214748364699999999995705.032706`**, matching the Owner's stated value digit for digit |
| R-Q07 | Several `REDUCED` events totalling near INTEGER max | exact; identical entry and exit prices give exactly `0` |
| R-Q08 | Caller context at `prec` 1, 5, 9, 28, 60 | **identical** object, text and JSON |
| R-Q09 | Caller rounding `ROUND_UP`, `ROUND_FLOOR` | **identical** |
| R-Q10 | Raw PostgreSQL rows recomputed by an independent integer method | matches byte for byte |
| R-Q11 | Text and JSON carry the identical full-precision string | 30 digits, both |
| R-Q12 | `_money` formatting of a >28-digit exact value | no rounding, no exponent form |
| R-Q13 | Structural: does `_entry_for_key` still perform any Decimal operation? | **no** — asserted against its source for `Decimal(`, `.normalize(`, `.quantize(`, `.scaleb(` |

## Finding 2 — "every omitted component is a cost" was false

### What was wrong

The banner, the limitations, the evidence package and the PR body all claimed
that because every excluded component is a cost, **every result is
systematically more favourable than a real economic outcome**.

That is an overclaim in the *opposite* direction from the usual failure mode —
it asserts a universal bound that does not hold:

| Component | Why it is not a cost |
|---|---|
| dividends | on a long position a dividend **raises** the real economic outcome |
| corporate actions | splits, mergers and spin-offs alter quantity or basis in **either** direction |
| taxes | jurisdiction- and context-dependent; can be a liability or a relief |

So the **direction of the total omitted effect is not generally knowable**, and
a name like `EXCLUDED_COST_COMPONENTS` was itself the misleading part — a field
name a consumer would read as a claim.

### The fix — vocabulary corrected before freeze

> ⚠ **The "After" column and the partition below are themselves superseded by
> Owner finding 4**, in the final honesty reconciliation pass further down this
> file. Preserved unedited as the record of what this pass concluded.

| Before | After (⚠ superseded) |
|---|---|
| `EXCLUDED_COST_COMPONENTS` | `EXCLUDED_ECONOMIC_COMPONENTS` → now `UNREPRESENTED_ECONOMIC_COMPONENTS` |
| `excluded_cost_components` (field) | `excluded_economic_components` → now `unrepresented_economic_components` |
| `"excluded_cost_components"` (JSON key) | `"excluded_economic_components"` → now `"unrepresented_economic_components"` |
| "systematically more favourable than any real economic outcome" | "**NOT a complete economic outcome**; the **direction** of the total omitted effect is **NOT generally knowable**" — this part still stands |

The list is additionally **partitioned**, so the honest statement can be made
about each group rather than a false one about the whole:

- ~~`EXCLUDED_FRICTION_COMPONENTS` — commissions, spread, slippage, exchange and
  regulatory fees, financing and borrow cost. Omitting these **would normally
  make a raw result look better** than reality.~~ ⚠ **RETRACTED by finding 4** —
  spread and slippage do not belong in a group that asserts both exclusion and a
  direction.
- ~~`EXCLUDED_NON_DIRECTIONAL_COMPONENTS` — taxes, dividends, corporate actions.~~
  ⚠ **Renamed** to `CONTEXT_DEPENDENT_COMPONENTS`; the statement about them was
  correct and still stands.

Correcting the API name now is deliberate: M080 is not frozen, and freezing a
field named for a claim that is false would be far worse than renaming it.

### Proof

| # | Owner attack | Result |
|---|---|---|
| R-R01 | Any surviving claim that every excluded item is a cost | none — banner, limitations, text and field names all checked |
| R-R02 | Any surviving universally-favourable-bias claim | none — four phrasings checked including "upper bound" |
| R-R03 | Dividends classified as a cost | no — in the non-directional group |
| R-R04 | Corporate actions classified as a cost | no |
| R-R05 | Taxes classified as a cost | no |
| R-R06 | The two groups partition the full list exactly | yes — union equal, intersection empty |
| R-R07 | Text and JSON expose the corrected terminology | yes; the old key is absent |
| R-R08 | The report states it is not a complete economic outcome | yes |
| R-R09 | The banner states the direction is not knowable | yes |
| R-R10 | **All original broker / P&L / profit guards still intact** | yes — 13 forbidden tokens and six banner phrases re-asserted at the boundary case |

## One correction to my own verification, recorded

My first attempt to confirm Finding 1 computed the "exact" control value with
`Decimal(q * price_scaled) / Decimal(10**6)`. Decimal **division** is
context-sensitive too, so the control rounded exactly like the code and printed
`EQUAL: True` — appearing to refute the Owner. Only pure integer arithmetic is a
valid control here. Recorded because a verification that agrees for the wrong
reason is more dangerous than one that fails.


---

# Owner review — final honesty reconciliation pass

Two further defects, both real, plus stale wording left active by the previous
correction. **This section supersedes the "frictions" grouping introduced in the
previous pass.**

## Finding 3 — no currency / denomination authority

**The premise, verified rather than assumed.** M076 persists exactly:
`instrument_symbol`, `quantity`, `asserted_price`, the two timestamps, the
optional plan citation and a note. There is **no** `currency`, `quote_currency`,
`price_currency` or `denomination` column — confirmed against the migration
(`b7e1c4a95d38`), the frozen domain event and the repository adapter.

**The defect.** M080 emitted values named `asserted_entry_cost`,
`asserted_exit_consideration` and `asserted_round_trip_result` with **no
statement of what units they are in**. A reader — or a future aggregating
milestone — would naturally assume a single currency. Nothing in the platform
supports that.

**The fix.** `ASSERTED_PRICE_DENOMINATION_LIMITATION` is carried on **every**
report shape, including the empty and the withheld ones, and the banner repeats
it. It states that values are in the same **unspecified asserted price units**
the ledger carries; that no currency is persisted; that `instrument_symbol` is
**not** a currency authority; that a value must not be read as USD, EUR or
anything else on M080's authority; and that two values must **not** be assumed to
share a denomination merely because both appear in one report.

No currency value is invented anywhere. No schema change and no migration.

| # | Owner attack | Result |
|---|---|---|
| R-S01 | M076 schema contains a currency field | **no** — asserted against the frozen event's fields |
| R-S02 | An arbitrary symbol produces an invented denomination | no — `AAPL`, `XAU`, `BTC`, `ZZZZ` all clean |
| R-S03 | JSON carries an invented currency | no |
| R-S04 | Text carries an invented currency | no |
| R-S05 | `$`, `USD`, `EUR`, `GBP`, `JPY`, `CHF`, `CAD`, `AUD`, `€`, `£`, `¥` appear as an inferred unit | none, outside the explicit denials |
| R-S06 | The limitation is missing from some report shape | present on closed, open, partial, empty **and** withheld |
| R-S07 | A future M081 could read two entries as a same-currency aggregate | denied in the limitation, and no aggregate field exists |

## Finding 4 — spread and slippage are not provably excluded

**The defect.** The previous correction placed `spread` and `slippage` in
`EXCLUDED_FRICTION_COMPONENTS` and said their omission "would normally make a
raw result look better than reality". **Too strong.**

M080's arithmetic uses the operator's **own asserted execution prices**. If those
prices are what the operator says they actually paid and received, spread and
slippage are **already embedded in them**. M076 stores no benchmark price, no
quoted bid or ask, no intended price and no arrival price — so there is nothing
to measure an execution effect against, and M080 cannot determine whether they
are absent, embedded, partly embedded or independently attributable.

**The fix — a three-way split**, replacing the previous two-way one:

| Group | Members | What may honestly be said |
|---|---|---|
| `UNREPRESENTED_CASHFLOW_COMPONENTS` | commissions, exchange and regulatory fees, financing and borrow cost | cash the ledger never records; including them would normally **reduce** a raw result |
| `CONTEXT_DEPENDENT_COMPONENTS` | taxes, dividends, corporate actions | can move the real outcome in **either** direction |
| `NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS` | spread, slippage | **not claimed excluded**; may already be embedded in the asserted prices; not measurable from this data |

The umbrella name also changed, for the same reason: `EXCLUDED_ECONOMIC_COMPONENTS`
→ `UNREPRESENTED_ECONOMIC_COMPONENTS`. "Excluded" asserts absence, which is
exactly what cannot be asserted for spread and slippage. The dataclass field and
JSON key are `unrepresented_economic_components`.

| # | Owner attack | Result |
|---|---|---|
| R-T01 | Spread/slippage still grouped with directional frictions | no — own group |
| R-T02 | Any claim they are definitely excluded | none — "NOT claimed to be excluded" |
| R-T03 | Are they described as not separately attributable | yes, with the four missing reference prices named |
| R-T04 | Do they appear in the line that claims a direction | **no** — asserted against that line |
| R-T05 | Does the cashflow group still contain an execution effect | no — exactly three members |
| R-T06 | Do the three groups partition the union exactly | yes — disjoint, union equal |

## Three more probe errors of my own, this pass

Recorded on the same principle as the earlier two: an attack that fails for the
wrong reason misleads exactly as much as a test that passes for the wrong one.

1. **The currency-token searches flagged my own denial.** `USD`, `EUR`, `$` and
   the rest appear in `ASSERTED_PRICE_DENOMINATION_LIMITATION` and the banner
   **in order to forbid them**. Three tests failed on that text. The tests were
   wrong, not the output; they now strip the banner and limitation sentences
   first, via a `_without_denials` helper, and search what remains.
2. **An assertion pinned the previous banner wording**, and failed when the
   banner was corrected for finding 4. The assertion was stale, not the banner.
3. **A fixture I wrote for the denomination tests gave a position id and an
   instrument symbol that did not correspond**, so the expectation it encoded
   was wrong before the code ever ran. Fixed at the fixture.

None of the three was a code defect. Counting them as findings would have
inflated this review; hiding them would have overstated the quality of my own
attacks.

## Stale active claims found and reconciled

**The first sweep in this pass was too narrow.** It covered the source tree and
four evidence documents, reported "7 found, 7 reconciled", and **one of those
seven was recorded as fixed when it was not**. Re-running the sweep across
**every** file the branch touches — including the root design document — found
twelve more. Both errors are recorded below rather than quietly replaced.

Terms searched: `EXCLUDED_COST_COMPONENTS`, `excluded_cost_components`,
`EXCLUDED_ECONOMIC_COMPONENTS`, `EXCLUDED_FRICTION_COMPONENTS`,
`EXCLUDED_NON_DIRECTIONAL_COMPONENTS`, `costs excluded`, `excluded costs`,
`excluded cost`, `systematically more favourable`, `more favourable than`,
`upper bound`, `spread`, `slippage`, `currency`, `USD`, `EUR`, `$`. Every
occurrence outside `.venv/` classified:

| # | Location | Was | Disposition |
|---|---|---|---|
| 1 | `asserted_round_trip_io.py` result line | "(arithmetic on assertions, **costs excluded**)" | **FIXED** — the live renderer was still asserting the retracted claim on the most-read line in the output |
| 2 | `owner-review-checklist.md` row 3 | "Every excluded **cost** is named… `EXCLUDED_COST_COMPONENTS`" | **FIXED**, marked as corrected |
| 3 | `owner-review-checklist.md` row 4 | "systematically more favourable than a real economic outcome" | **FIXED**, marked retracted |
| 4 | `owner-review-checklist.md` rename rationale | referred only to finding 2 | extended to finding 4 |
| 5 | `owner-review-checklist.md` rows 7 and 8 | named `EXCLUDED_ECONOMIC_COMPONENTS` / `EXCLUDED_NON_DIRECTIONAL_COMPONENTS` as current | **marked superseded** in place |
| 6 | `reality-gate.md` closing paragraph | "name the **excluded costs** and the direction of their bias" | **FIXED — on the second attempt.** ⚠ The first sweep recorded this as FIXED **and it was not**; the paragraph was still live. The false record is corrected here, and the paragraph itself now carries a note saying so |
| 7 | `reality-gate.md` component table | every row read "**excluded**", including spread and slippage | **superseded table struck through and preserved**; a three-way table replaces it |
| 8 | `reality-gate.md` structured-field paragraph | `excluded_economic_components`, `EXCLUDED_FRICTION_COMPONENTS`, `EXCLUDED_NON_DIRECTIONAL_COMPONENTS` | **FIXED** to the current names |
| 9 | `reality-gate.md` "what the artifact now says" | "frictions such as commissions, **spread, slippage** and fees would normally reduce" | **FIXED** — spread and slippage moved to their own bullet with no direction claim; a denomination bullet added |
| 10 | `README.md` | "which **costs** are excluded" | **FIXED** |
| 11 | `hostile-implementation-review.md` R-H05 | asserted the bias direction as a pass | **marked RETRACTED**, original preserved |
| 12 | `hostile-implementation-review.md` R-L05 | named the old field | annotated with the rename |
| 13 | `hostile-implementation-review.md` finding-2 "the fix" table and partition | presented `EXCLUDED_ECONOMIC_COMPONENTS` and the two-way split as current | **marked superseded**, struck through in place, not deleted |
| 14 | `hostile-design-review.md` H08 | "The list is now `EXCLUDED_ECONOMIC_COMPONENTS`, split into frictions and non-directional components" | **further retraction appended**; original preserved |
| 15 | `known-limitations.md` item 2 | grouped spread and slippage with frictions that "would normally reduce a raw result" | **FIXED** — rewritten as the three-way split, with both prior versions recorded as retracted |
| 16 | `known-limitations.md` item 4 | "they omit **costs** and open exposure" | **FIXED**, and pointed at the new denomination limitation |
| 17 | `known-limitations.md` | no denomination limitation existed at all | **ADDED** as item 16 |
| 18 | `validation-results.md` "the vocabulary proof" | asserted the two-way partition as a verified current fact | **marked SUPERSEDED**, struck through; the still-valid part kept separately; current measured results added |
| 19 | `focused-re-review.md` finding-2 rows | "the two groups partition the list exactly"; "frictions would normally reduce" | **marked superseded** in place; finding 3 and 4 re-attack tables added |
| 20 | `focused-re-review.md` suite table | "78 passed" for the M080 unit suite | **updated** to the re-measured 98 |
| 21 | `scope-and-design-snapshot.md` header, §15 closing note, §23 | old constant names; "frictions"; "It excludes every cost component in §15" | **FIXED / marked superseded**; §15's body table left struck through and verbatim |
| 22 | **`MILESTONE_080_..._SCOPE_AND_DESIGN.md` (repository root)** | the same three, in the **frozen-facing** design document — missed entirely by the first sweep, which only looked under `external-review/` | **FIXED**, re-synced byte-for-byte with the snapshot |
| — | module comment, correction sections, reality-gate strikethrough, R01's quoted pre-fix output, tests asserting absence | name the old terms **in order to retract or forbid them** | **kept** — these are the retraction record, and deleting them would destroy it |
| — | `USD` / `currency` in `portfolio_study.py`, `run_portfolio_historical_evidence.py`, `portfolio_study_repository.py` | M067/M061 **do** persist a currency | **out of scope** — different milestone, real column, untouched |

**22 active stale claims found; 22 reconciled.** Nineteen were live text that
read as current truth; one (#6) was a **false reconciliation record** in this
very file; one (#17) was a missing statement rather than a wrong one; one (#22)
was in the frozen-facing root document that the first sweep never searched.

No historical conclusion was deleted. Every superseded statement remains
visible, struck through or annotated, with the finding that superseded it named.
