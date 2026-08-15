# M080 — Hostile Design Review (pre-implementation)

My own attack on my own design. **Not an independent review.** Every **FIXED**
item was corrected in the design document before a line of implementation code
was written. Counts in the header are computed programmatically from this file,
not asserted by hand — the lesson of M079's R02.

**137 attacks. 46 genuine defects found and corrected in the design before implementation; the remainder passed or were accepted with stated reasons.**

The three load-bearing fixes are **T07** (the derived-`CLOSED`-quantity hazard,
which makes a coherent fold hide missing exits), **A03** (composing M078's
session audit would void the whole answer on one unrelated truncated key) and
**H09** (an open position's arithmetic silently reading as the whole position's
result).

## A. Architecture and composition

| # | Attack | Verdict |
|---|---|---|
| A01 | M080 re-implements M076's lifecycle fold | PASS — it calls `derive_position_state` per key and never decides open vs closed itself |
| A02 | M080 re-implements M079's knowledge filter | PASS — it calls the public `events_known_by` exactly once |
| A03 | **M080 composes M078's session audit and inherits whole-ledger voiding** | **FIXED** — `audit_research_decision_follow_through` needs a `held_state` from `derive_position_state`, which raises on the *first* non-folding key. Knowledge filtering makes truncated prefixes common, so one unrelated position would return `NOT_ASSESSABLE` for everything. Design changed to **position-centric** with per-key folding, M079-style |
| A04 | M080 re-implements M078's lineage projection | **FIXED** — calls the public `cited_plan_by_position` instead of reading `source_position_plan_governance_id` directly |
| A05 | M080 claims a session→ledger join without M078's identity defenses | **FIXED** — M080 reports the citation as metadata and explicitly disclaims the join; §11 names M078 as sole authority |
| A06 | A new PostgreSQL table is added for ceremony | PASS — zero new tables; the data is already persisted |
| A07 | A migration is added | PASS — none |
| A08 | A new repository protocol is added | PASS — reads the existing M076 repository |
| A09 | Frozen M076 is edited to expose exit prices | PASS — projected from the same event tuple already read, exactly as M078 did for lineage |
| A10 | Frozen M079 is edited to expose filtered events | PASS — `events_known_by` was already public |
| A11 | `entrypoints` imports `decision_candidate`, breaking the architecture rule | **FIXED** — the CLI passes primitives and the usecase owns the domain call, as M076's CLI does |
| A12 | `usecases` imports `shared.persistence` | PASS — repository injected via protocol |
| A13 | The module performs I/O | PASS — pure; no clock, no network, no filesystem |
| A14 | The module uses `float` anywhere | PASS — `Decimal` throughout, asserted by test |
| A15 | The M072 daily brief is modified to show results | PASS — untouched; this is a question about the past, not about today |
| A16 | M077's capital feasibility is made to consume the result | PASS — untouched |

## B. Temporal — the two cutoffs

| # | Attack | Verdict |
|---|---|---|
| B01 | An assertion recorded after `K` changes the arithmetic | PASS — structurally impossible; the evaluation core is handed only `events_known_by` survivors |
| B02 | An assertion recorded after `K` changes the status | PASS — same structure |
| B03 | …changes the counts | PASS |
| B04 | …changes the limitations | PASS |
| B05 | …changes the ordering | PASS |
| B06 | …changes whether an outcome exists at all | PASS |
| B07 | `recorded_at` used as effective time | PASS — roles never cross |
| B08 | `event_timestamp` used as knowledge time | PASS |
| B09 | One cutoff silently serves both | **FIXED** — an early draft took a single `as_of`; both are now required with no default on either |
| B10 | `knowledge_as_of` defaults to now, making the answer irreproducible | **FIXED** — required, no default, in domain and CLI |
| B11 | `effective_as_of` defaults to the session's own timestamp | **FIXED** — no default; §8 explains that defaulting would silently redefine the question |
| B12 | Exact `K` boundary is exclusive, losing an event recorded at exactly `K` | PASS — inclusive, inherited from `events_known_by` |
| B13 | Exact `E` boundary is exclusive | PASS — inclusive, inherited from frozen M076 |
| B14 | One microsecond after `K` leaks in | PASS |
| B15 | Naive `effective_as_of` accepted | **FIXED** — both cutoffs validated timezone-aware in the domain *and* the query object; M078's R03 lesson |
| B16 | Naive `knowledge_as_of` accepted | **FIXED** — same |
| B17 | Two timestamps in different zones at the same instant compare unequal | PASS — comparison is by instant, not by zone |
| B18 | `K < E` rejected as invalid, refusing a meaningful question | ACCEPTED as meaningful — "what did we know then about what had happened by later?"; named in a limitation whenever used |
| B19 | `K` set to the present is a hidden effective-time query | ACCEPTED and stated openly in §8 — it *is* current reconstruction, and the table says so |
| B20 | An exit effective after `E` but recorded before `K` is counted | PASS — excluded by M076's effective filter; reported in the effective-exclusion count |
| B21 | An exit effective before `E` but recorded after `K` is counted | PASS — excluded by the firewall; **this is exactly T07's hazard** |
| B22 | The evaluation reports a count of what the firewall hid | PASS — deliberately absent, per M079's frozen correction; counting hidden rows requires reading them |
| B23 | Decision time is used as a silent filter | **FIXED** — reported, never filtered on |

## C. The derived-`CLOSED`-quantity hazard

| # | Attack | Verdict |
|---|---|---|
| **T07** | **A coherent fold hides missing exit quantity** | **FIXED — the most important finding of this review.** `validate_appended_event` derives a `CLOSED` event's quantity at append time from the *full* effective-time history and persists it. Proven by execution: `OPENED 10 (rec d1)`, `REDUCED 4 (rec d9, late)`, `CLOSED (rec d3)` persists `CLOSED q=6`. At `K=d3` the visible prefix `OPENED(10), CLOSED(6)` **folds coherently** and M079 reports `KNOWN_CLOSED` — yet visible exits account for 6 of 10 shares. Naive arithmetic would report a 6-share result as the closed position's result, or extrapolate it to 10. **Fix:** reconcile `Σ visible exit quantity` against the visible opened quantity and emit `EXIT_QUANTITY_UNRECONCILED` with the shortfall named |
| T07a | The unreconciled case is treated as an error and the whole report withheld | **FIXED** — it is a legitimate knowledge state, not corruption; it is reported per position, not fatal |
| T07b | The unreconciled case silently reuses `FULLY_EXITED_ASSERTED` | **FIXED** — distinct status |
| T07c | The unreconciled case still emits a result labelled complete | **FIXED** — the arithmetic over the *visible* exits is still shown, explicitly labelled as covering only the reconciled quantity, with the shortfall stated |
| T07d | Reconciliation uses the persisted `CLOSED.quantity` as authority for "everything exited" | **FIXED** — it is treated as one exit component among others, never as proof of completeness |
| T07e | The shortfall is computed against the *full* opened quantity rather than the visible one | **FIXED** — visible evidence only, or it would leak |

## D. Lifecycle shapes

| # | Attack | Verdict |
|---|---|---|
| D01 | `OPENED` only | PASS — `NO_EXIT_ASSERTED_YET`, no arithmetic emitted |
| D02 | `OPENED → CLOSED` | PASS — full round trip, reconciles |
| D03 | `OPENED → REDUCED → CLOSED` | PASS |
| D04 | Multiple `REDUCED` events | PASS — every reduction is an exit component |
| D05 | Reduction landing exactly on zero, **no `CLOSED` event** | **FIXED** — proven by execution that M076 closes the position with no closing event; an early draft required a `CLOSED` event to declare a full exit and would have mis-stated this as unreconciled |
| D06 | Reduction exceeding open quantity | PASS — M076 rejects at append; unreachable in persisted data |
| D07 | A reduction visible without its opening | PASS — does not fold → `UNRESOLVED_KNOWLEDGE_SEQUENCE`, M079's word, no arithmetic |
| D08 | A close visible without its opening | PASS — same |
| D09 | Two `OPENED` events on one key | PASS — M076 rejects at append |
| D10 | Re-opening a closed key | PASS — M076 rejects; requires a new position id |
| D11 | An instrument mismatch inside one position key | PASS — M076's own rejection surfaces as unresolved |
| D12 | A position with zero events after filtering | PASS — not a key at all; produces no entry |
| D13 | `CLOSED` with a derived quantity of zero (close of an already-empty position) | PASS — M076 rejects closing a non-open position |
| D14 | The open remainder is treated as exited | **FIXED** — see H09 |

## E. Numeric and precision

| # | Attack | Verdict |
|---|---|---|
| E01 | `float` appears anywhere in the arithmetic | PASS — `Decimal` only, asserted by a test that walks every field |
| E02 | Quantity assumed `Decimal` | **FIXED** — proven by execution that M076's `quantity` is **`int`**; it is widened with `Decimal(q)` explicitly rather than relied upon |
| E03 | Six-decimal price loses precision | PASS — exact in `Decimal` |
| E04 | Maximum `NUMERIC(20, 6)` price overflows | PASS — the *result* is not persisted, so no column bound applies; `99999999999999.999999 × 1000` renders exactly |
| E05 | Minimum positive price `0.000001` underflows | PASS — exact |
| E06 | Multiplication precision loss | PASS — `Decimal` × `Decimal` from an exact integer is exact |
| E07 | Summation precision loss | PASS — exact addition of exacts |
| E08 | Result rounded or quantized silently | **FIXED** — no rounding; §14 states that rounding an implied number repeats the dishonesty M076 refused for prices |
| E09 | Exact break-even renders as something other than zero | PASS — `Decimal("0.000000").normalize()` → `0` |
| E10 | **Negative zero renders as `-0`** | **FIXED (defensively)** — proven that `Decimal("-0.000000")` renders `-0`. Also proven **not reachable** through `exit − entry`, since `a − a` is `+0` under the default rounding. A guard and a test are added anyway because the rendering would be misleading if a future refactor made it reachable. Recorded as defensive, not corrective |
| E11 | A loss renders without its sign | PASS — `-60` |
| E12 | A huge result renders in exponent form | PASS — `normalize()` then `format(..., "f")`, M076's own idiom |
| E13 | A value read from PostgreSQL renders differently from one built in memory | PASS — same canonical form; asserted by integration test |
| E14 | Fractional quantities | PASS — impossible; M076 quantity is `int`. Stated in §12 rather than assumed |
| E15 | Negative quantity | PASS — M076 rejects |
| E16 | Zero exited quantity yields a misleading `0` result | **FIXED** — no arithmetic is emitted at all when nothing is exited, rather than a zero that reads like break-even |
| E17 | Integer division or floor anywhere | PASS — none |
| E18 | Result compared with `==` against a differently-scaled Decimal in tests | PASS — canonical rendering compared as text |

## F. Lineage

| # | Attack | Verdict |
|---|---|---|
| F01 | A blank plan citation is treated as an identifier | PASS — M078's `cited_plan_by_position` strips blank and whitespace-only citations |
| F02 | A missing citation is treated as an error | PASS — reported as absent; a position need not cite a plan |
| F03 | A malicious citation makes M080 assert a session membership | **FIXED** — M080 reports the citation and explicitly disclaims any join |
| F04 | Conflicting plan identity across a session | PASS — out of scope by design; M078 owns it, and §11 says so |
| F05 | One plan cited by several positions | PASS — each position is its own entry; nothing is merged |
| F06 | A position changes its citation across events | PASS — only the `OPENED` event's citation is projected, by M078's rule |
| F07 | A position cites a plan for a different instrument | PASS — reported; M080 makes no claim about the plan's instrument |
| F08 | A citation is validated against `position_plan`, adding a frozen-table dependency | PASS — deliberately not done; M080 reads only the ledger |

## G. Rendering, CLI and output

| # | Attack | Verdict |
|---|---|---|
| G01 | Text and JSON drift apart | PASS — one object, two renderers, parity asserted |
| G02 | JSON emits `Decimal`, which is not JSON-serialisable | **FIXED** — canonical strings, as M076 renders money |
| G03 | A cutoff is missing from the output, making the answer unreproducible | **FIXED** — both cutoffs echoed in both renderings |
| G04 | The CLI defaults a cutoff | **FIXED** — both required; usage error otherwise |
| G05 | The CLI accepts a naive timestamp | **FIXED** — rejected with a usage message |
| G06 | An append path is reachable from the read CLI | PASS — read-only composition root |
| G07 | The banner is omitted from JSON | PASS — present in both |
| G08 | Limitations are omitted when the result is "good" | PASS — unconditional |
| G09 | The excluded-by-effective count is missing | PASS — reported |
| G10 | A hidden-by-knowledge count is added, leaking | PASS — deliberately absent, per M079 |

## H. Honesty and vocabulary

| # | Attack | Verdict |
|---|---|---|
| H01 | The result is called realized P&L | PASS — forbidden token, asserted by test |
| H02 | …called actual profit | PASS |
| H03 | …called verified proceeds | PASS |
| H04 | …called a market return | PASS |
| H05 | …called an execution result | PASS |
| H06 | The bare token `PNL` appears in a field or status | **FIXED** — banned outright; it survives only inside negative disclaimers |
| H07 | The result is presented as cash that moved | **FIXED** — named `asserted_round_trip_result`, and the banner says no cash claim is made |
| H08 | Fees, slippage, taxes, dividends and corporate actions are omitted silently | **FIXED** — itemised as a structured limitation on **every** result, per §15, not buried in prose |
| H09 | **An open position's partial result reads as the whole position's result** | **FIXED** — distinct `PARTIAL_EXIT_ASSERTED` status, the covered quantity stated explicitly, the still-open quantity reported separately, and no per-share extrapolation |
| H10 | An unrealized result is computed for the open remainder | PASS — impossible; no market price exists in the platform and none is invented |
| H11 | The result is aggregated across positions into a portfolio figure | **FIXED** — deliberately not built; aggregation implies a performance claim and belongs to an authorized calibration milestone |
| H12 | A win rate or expectancy is emitted | PASS — out of scope, §24 |
| H13 | A return percentage is emitted | **FIXED** — excluded; a percentage invites comparison with market returns |
| H14 | The result is described as investment performance | PASS |
| H15 | The result is confused with M062/M063/M067 simulated `realized_pnl` | **FIXED** — §3 names the collision explicitly; those are simulation over historical bars, M080 is operator assertion, and the artifact says which it is |
| H16 | A disclaimer is used to rescue a misleading number | PASS — the safeguards are structural (no aggregate, no percentage, no unrealized, no extrapolation), not textual |
| H17 | The operator's conduct is judged | PASS — no `FOLLOWED`/`ADHERENCE`/`COMPLIANCE` vocabulary |
| H18 | Silence in the ledger is read as inaction | PASS — M078's lesson inherited; absence is absence of record |
| H19 | The result implies the trade occurred | PASS — banner states it is an assertion, not evidence of a trade |
| H20 | Advice is implied | PASS |

## I. Failure and absence

| # | Attack | Verdict |
|---|---|---|
| I01 | An unreadable ledger renders as "no results" | **FIXED** — `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE`, everything withheld |
| I02 | A database error is disguised as a soft verdict | PASS — propagates; bad *data* is withheld, a broken *database* is not hidden |
| I03 | Nothing recorded by `K` renders as "nothing happened" | **FIXED** — distinct outcome with an explicit limitation |
| I04 | An empty position set renders as an error | PASS — a legitimate empty result |
| I05 | One unresolved position voids the whole report | **FIXED** — per-key isolation, M079's design adopted |
| I06 | A position is silently dropped from the report | **FIXED** — M079's R01 lesson: every visible key produces exactly one entry, asserted by test, and an invariant violation raises rather than skipping |

## J. Ordering and determinism

| # | Attack | Verdict |
|---|---|---|
| J01 | Ordering depends on dict insertion order | **FIXED** — sorted by `(instrument_symbol, position_governance_id)` |
| J02 | Ordering depends on a post-cutoff row | PASS — entries derive from visible keys only; asserted by test |
| J03 | Exit components consumed in arbitrary order, changing the sum | PASS — sum is order-independent in exact `Decimal`, and M076's own order key is used anyway |
| J04 | Two identical reads differ | PASS — pure function; determinism asserted |
| J05 | Insertion order into PostgreSQL changes the answer | PASS — asserted in the second pass with reversed insertion |

## K. Concurrency and persistence

| # | Attack | Verdict |
|---|---|---|
| K01 | A concurrent writer produces a torn read | PASS — `list_all()` is one `SELECT` in one transaction under `READ COMMITTED`; proven by a barrier-synchronised race |
| K02 | An index is assumed on `recorded_at` | PASS — none; in-memory filtering, inherited deferral stated |
| K03 | The persisted `CLOSED` quantity is trusted blindly | **FIXED** — see T07d |
| K04 | Raw SQL and the module disagree on prices | PASS — cross-checked independently in integration |
| K05 | `NUMERIC(20,6)` round-trip changes a rendered result | PASS — canonical form; asserted |

## L. Test-quality attacks on the design itself

| # | Attack | Verdict |
|---|---|---|
| L01 | Tests assert the implementation's shape rather than the claim | **FIXED** — tests are written from §22/§23 claims |
| L02 | The forbidden-vocabulary test checks only the banner | **FIXED** — it walks every dataclass field name, every enum value and both renderings |
| L03 | No test proves the firewall over *two databases* | **FIXED** — mandated double-database test designed in |
| L04 | No test proves a result changes only as knowledge advances | **FIXED** — multi-cutoff evolution test designed in |
| L05 | The unreconciled state is never exercised | **FIXED** — it is the T07 scenario and is a named test |
| L06 | Attack counts in this document are asserted by hand | **FIXED** — computed programmatically, M079 R02's lesson |
