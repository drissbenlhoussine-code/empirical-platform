# M077 — Hostile Design Review (pre-implementation)

My own attack on my own design. **Not an independent review.** Every **FIXED**
item was corrected in the design document before a line of code was written.
Failed first designs are recorded here rather than deleted.

64 attacks. 9 genuine defects found and fixed; 4 accepted with stated reasons.

## A. Frozen-contract mutation

| # | Attack | Verdict |
|---|---|---|
| A01 | M077 changes M075's meaning | PASS — M075 is neither imported for mutation nor re-interpreted; M077 is a separate artifact, forced by M075's own banner denying prior-day exposure |
| A02 | M077 modifies M076 source | PASS — read-only via `list_all()` and the pure `derive_position_state()` |
| A03 | M077 needs a field M076 doesn't expose (`source_position_plan_governance_id` is absent from `DerivedPosition`) | **FIXED** — the first design was going to add a defaulted field to M076's frozen `DerivedPosition`. Rejected. M077 instead projects lineage from the same raw event tuple it already reads. **Zero M076 modification.** |
| A04 | Adding a brief field breaks the frozen M072 contract | PASS — keyword-only defaulted field, exactly M074's and M075's own additive pattern |
| A05 | M077 silently reuses `PortfolioAllocationOutcome.ALLOCATED` | PASS — M077 owns its vocabulary; `ALLOCATED` is forbidden by test |
| A06 | Reusing M067's `PortfolioRejectionReason` overclaims | PASS — those reasons are generic capital reasons; reusing them keeps one definition, exactly as M075 already does |
| A07 | M077 requires a schema change | PASS — zero new table, zero migration |
| A08 | M077 repairs M062/M064/M065 seal debt | N/A — introduces no fixture and no byte seal |

## B. Fabricated execution / valuation semantics

| # | Attack | Verdict |
|---|---|---|
| B01 | Held notional is presented as market value | PASS — labelled asserted, computed at asserted **entry** price, never revalued |
| B02 | Held notional is presented as a verified cost basis | PASS — banner denies broker verification |
| B03 | The result implies an order was executed | PASS — forbidden-vocabulary test over module and rendered output |
| B04 | "Remaining capital" implies a real cash balance | **FIXED** — renamed throughout to *remaining capital **under this policy***, and the banner states the capital base is a supplied equity figure, not a verified balance |
| B05 | **Charging held notional against equity double-counts, because buying an asset converts cash into stock and leaves equity unchanged** | **FIXED — the sharpest conceptual attack.** The first design's prose implied capital was being *depleted*. It is not. M067's model is **utilization**: `max_capital_utilization_percent` measures how much of the capital base is deployed. Held asserted notional is deployed capital. The design now states this explicitly, so the figure is not misread as cash depletion |
| B06 | An approved plan is treated as evidence a trade happened | PASS — only ledger assertions contribute held exposure |
| B07 | M068 dependence evidence becomes an operational concentration control | PASS — explicit non-goal §12 |
| B08 | M067 historical simulation becomes operational portfolio truth | PASS — only the *policy value object* is reused, never a simulation result |
| B09 | The artifact implies profitability | PASS — no return, no P&L, no revaluation anywhere |

## C. Double counting

| # | Attack | Verdict |
|---|---|---|
| C01 | A position asserted from today's own plan is counted as both held and proposed | **FIXED** — lineage index over `OPENED` events of positions open at `as_of`; matching plans excluded exactly once and named |
| C02 | The lineage exclusion silently drops a plan | **FIXED** — excluded plans are reported with an explicit reason, never omitted |
| C03 | A plan cited by a position that is **closed** at `as_of` is wrongly excluded | **FIXED** — only positions **open at `as_of`** drive exclusion. A closed position released its exposure, so re-entering is legitimate. Recorded as a deliberate decision, not an oversight |
| C04 | Two positions cite the same plan | **FIXED** — the index is a set membership test, so the plan is excluded once regardless of how many positions cite it |
| C05 | Same instrument held and proposed without lineage | ACCEPTED — legitimately a *new* position (M076 forbids re-opening a closed key and requires a new key for a new entry). Named as an observation, not excluded |
| C06 | Lineage cites a plan from a different session | PASS — exclusion is by membership in *this* session's approved plan ids only |
| C07 | Lineage cites a non-existent plan | PASS — a membership test cannot fail on an unknown id; it simply does not match |

## D. Temporal

| # | Attack | Verdict |
|---|---|---|
| D01 | Future-dated events inflate held exposure | PASS — M076's `event_timestamp <= as_of` filter, reused unchanged |
| D02 | Excluded future events are hidden | PASS — M076 already surfaces `excluded_future_event_count`; M077 propagates it |
| D03 | Exact-boundary event excluded by an off-by-one | PASS — `<=` is inclusive; named boundary test |
| D04 | `recorded_at` leaks into the snapshot | PASS — M076's fold reads `event_timestamp` only |
| D05 | Two offsets for one instant disagree | PASS — aware datetimes compared as instants; named test |
| D06 | Naive `as_of` silently assumed UTC | PASS — M076 rejects naive `as_of`; the brief's `as_of` is already validated aware |
| D07 | Reduction after `as_of` reduces the snapshot | PASS — excluded by the same filter; named test |
| D08 | Reduction before `as_of` is ignored | PASS — fold decrements; named test |
| D09 | Session `as_of` differs from "now", so the snapshot is stale | ACCEPTED — the session's own `as_of` is the only defensible anchor; using wall-clock would make the brief non-reproducible. Named as a limitation |

## E. Capital arithmetic

| # | Attack | Verdict |
|---|---|---|
| E01 | Held exposure exceeds the ceiling and the code still admits plans | **FIXED** — first design ran the admission loop unconditionally; it now short-circuits to `ALREADY_AT_OR_OVER_CAPITAL` with every plan excluded and a reason |
| E02 | Held exposure exactly equals the ceiling | **FIXED** — strict `>` means equality is *not* over the line, but headroom is zero, so any positive plan is excluded. Both facts asserted separately, because they are easy to conflate |
| E03 | Held position count already at `max_concurrent_positions` | **FIXED** — the count is seeded from held positions, so every plan is rejected `MAX_CONCURRENT_POSITIONS`. The first design seeded only notional and would have admitted an 11th position |
| E04 | Capital base zero or negative | PASS — `NOT_ASSESSABLE` / `NON_POSITIVE_CAPITAL_BASE`, mirroring M075 |
| E05 | Plans sized against different equities | PASS — minimum taken, mirroring M075, and named |
| E06 | Held exposure negative | PASS — impossible: quantity and price are both positive-constrained in M076 |
| E07 | Float creeps into money | PASS — `Decimal` only; the string↔`Decimal` boundary is canonical |
| E08 | `total_asserted_open_notional` is a **string**, so parsing it back could lose precision | **FIXED** — noted explicitly: M076's `_money()` emits a canonical exact `Decimal` string, so `Decimal(...)` round-trips it exactly. A test asserts equality against a raw-SQL-derived sum rather than trusting the parse |
| E09 | A plan larger than the whole ceiling | PASS — excluded with `MAX_CAPITAL_UTILIZATION_EXCEEDED` |
| E10 | Non-positive plan notional | PASS — excluded and named, mirroring M075 |
| E11 | Utilization percent divides by zero | **FIXED** — guarded; reported as `None` when the ceiling is zero, never `0%`, which would read as "nothing used" |
| E12 | A big plan blocks smaller feasible ones | PASS — deliberate, mirroring M075: admission continues so the operator learns the largest feasible subset |

## F. Absence, error, malformed state

| # | Attack | Verdict |
|---|---|---|
| F01 | Ledger unavailable renders as "no positions held" | **FIXED** — distinct `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE`. Absence must never render as a pass |
| F02 | Empty ledger is an error | PASS — assessed normally with zero held exposure, stated explicitly |
| F03 | Malformed persisted data raises and takes the brief down | **FIXED** — `LedgerRejectionError` caught and converted to `NOT_ASSESSABLE` / `LEDGER_INCOHERENT`. This is the M074 sort-crash lesson applied deliberately |
| F04 | Suppression is indistinguishable from "could not assess" | PASS — suppressed is `None`; unassessable is a populated object with a reason |
| F05 | Session not completed yields a confident verdict | PASS — withheld |
| F06 | No approved plans hides held exposure | **FIXED** — `NO_APPROVED_POSITION_PLANS` still reports held exposure, which is the operator's most useful fact in that state |
| F07 | A plan with no sizing is silently dropped | PASS — named, mirroring M075 |

## G. Determinism, rendering, boundaries

| # | Attack | Verdict |
|---|---|---|
| G01 | Verdict order depends on dict/set iteration | PASS — `(rank, symbol)` total order, never input order |
| G02 | Held positions render in nondeterministic order | PASS — M076 already orders deterministically |
| G03 | Text and JSON disagree | PASS — one derived object renders both; parity test |
| G04 | JSON section inventory test breaks | PASS — updated exactly as M074 and M075 each did |
| G05 | CLI flag differs between the two daily entrypoints | PASS — same flag on both |
| G06 | `entrypoints` imports `decision_candidate`, breaking the architecture rule | PASS — construction and rendering live in `usecases`, the M076 CLI lesson applied |
| G07 | Rendering a `None` assessment crashes | PASS — suppressed renders as an explicit "not computed" line |
| G08 | Money renders differently in memory vs after reload | PASS — canonical string formatting, the M076 `_money()` lesson |
| G09 | Two runs over identical inputs differ | PASS — pure function, no clock, no randomness |

## H. Persistence and concurrency

| # | Attack | Verdict |
|---|---|---|
| H01 | A concurrent M076 write tears M077's snapshot | PASS — `list_all()` is a single `SELECT`; `READ COMMITTED` gives one statement a consistent snapshot. Proven by a concurrency test, not asserted |
| H02 | M077 needs its own lock | ACCEPTED — it does not. The requirement is a point-in-time snapshot and one statement already provides it. Adding a lock would be unjustified ceremony |
| H03 | M077 writes to the ledger | PASS — no write path exists on its dependency |
| H04 | M077 opens a transaction it never closes | PASS — repository-managed unit of work |
| H05 | In-memory and PostgreSQL disagree | PASS — cross-checked with raw SQL |
| H06 | A write committed mid-fold is half-visible | PASS — per-position atomic commit under M076's advisory lock |

## I. Claim honesty

| # | Attack | Verdict |
|---|---|---|
| I01 | Banner is documentation only, not rendered | PASS — rendered in both formats, the M075 lesson |
| I02 | Vocabulary implies verification | PASS — forbidden-vocabulary test |
| I03 | "Portfolio-aware" implies a real portfolio | ACCEPTED — qualified everywhere by *operator-asserted*, and the banner denies broker verification |
| I04 | The artifact is read as advice | PASS — explicitly denied in the banner |

## Unresolved

**None.** No correctness FAIL remains. The four ACCEPTED items (C05, D09, H02,
I03) are bounded, stated, and carry reasons rather than being waved through.
