# M080 — Hostile Implementation Review

A **new** adversarial pass against the real code and real persistence
behaviour. **Not an independent review** — the same agent wrote the code.
Counts are computed programmatically from this file.

**152 attacks executed against the running code, the usecase layer and real PostgreSQL. 1 genuine defect found and fixed, with regression tests that fail against the pre-fix implementation. Two of my own probe assertions were wrong and are recorded as such.**

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
ASSERTED ROUND-TRIP RESULT (arithmetic on assertions, costs excluded): -20
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
| R-H05 | The cost caveat states the direction of the bias | "more favourable than a real economic outcome" |
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
| R-L05 | `excluded_cost_components` is mutable | no — tuple |
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

## Two probe errors of my own, recorded

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
