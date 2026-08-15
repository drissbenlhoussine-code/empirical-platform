# MILESTONE-076 — Operator-Asserted Position Ledger — Scope and Design

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

## 1. Repository Truth

Verified from git before any file was modified; not taken from the mission text.

| Fact | Value |
|---|---|
| `origin/master` | `92ff47217716aebba7b88633afed40b5265c68b2` |
| ahead / behind | 0 / 0, working tree clean |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-075` |
| `M075_STATUS` | `APPROVED_AND_FROZEN` (freeze commit `7bd4bb3`) |
| `M074_STATUS` | `APPROVED_AND_FROZEN` |
| `M076_STATUS` | `NOT_STARTED` |
| Alembic head | `31365632c016` |

## 2. Problem Statement

The platform can size a position, judge whether today's proposed set fits in capital,
and surface historical portfolio evidence — but it **cannot answer what the operator
actually holds**. Every day starts from zero.

## 3. Evidence-Backed Gap Analysis

Measured against source, not milestone prose.

**43 tables exist. Not one models an operational position.** The full list —
`campaign`, `run`, `decision_candidate`, `trade_plan`, `position_plan`,
`research_session`, `portfolio_study`, `survivorship_study`, … — contains no holding,
no ledger, no open/closed lifecycle.

- `position_plan` columns are `…status, entry_price, stop_price, quantity,
  position_notional, actual_risk`. **A terminal sizing verdict. No lifecycle, no
  outcome, no open/closed, no timestamp of action.**
- The only `OPEN`/`CLOSED` concepts in the repository live in `portfolio_study.py` and
  `portfolio_dependence.py` — M067/M068 **historical simulation** over frozen M064
  studies. That is *replay*, not operational state.
- M071 continuity compares `SessionComparisonEntry(instrument_symbol, outcome,
  target_scan_decision, target_trade_plan_decision, baseline_…)` — **decisions only.
  No exposure, no quantity, no capital.**
- M075's own module docstring states it: *"No prior-day position is known or
  considered — this repository has no durable position state."*

### The seven questions of the special gate, answered from code

| Question | Answer today |
|---|---|
| What positions were notionally opened previously? | **Cannot answer** — nothing records an opening |
| Which remain open as of today? | **Cannot answer** — no open/closed concept |
| What capital is already committed before today's candidates? | **Cannot answer** |
| What instruments are already held? | **Cannot answer** |
| What exposure carries across sessions? | **Cannot answer** — M071 carries decisions only |
| What prior decisions materially constrain today's? | **Cannot answer** |
| Can M075 distinguish new from existing exposure? | **No** — it assesses only today's set and says so in its banner |

### Candidate ranking

| # | Candidate | Product leverage | Arch. leverage | Impl. risk (5=low) | Frozen risk (5=low) | Honesty risk (5=low) | Unlocks | **Total** |
|---|---|---|---|---|---|---|---|---|
| **1** | **Durable cross-day position state (A)** | 5 | 5 | 3 | 4 | 3 | 5 | **25** |
| 2 | Portfolio-aware daily capital awareness (C) | 5 | 3 | 3 | 3 | 3 | 2 | 19 |
| 3 | Explainability / audit trail (J) | 2 | 3 | 4 | 5 | 5 | 2 | 21 |
| 4 | Data-quality fallback (H) | 3 | 2 | 3 | 4 | 4 | 2 | 18 |
| 5 | Scheduling / automation (K) | 2 | 2 | 4 | 5 | 3 | 1 | 17 |
| 6 | Alerting / actionability (L) | 2 | 1 | 4 | 5 | 3 | 1 | 16 |
| 7 | P&L state (E) | 4 | 3 | 2 | 3 | 1 | 3 | 16 |
| 8 | Paper trading (F) / execution simulation (G) | 4 | 2 | 1 | 2 | 1 | 2 | 12 |

**(C) cannot be built without (A)** — portfolio-aware daily capital *is* M075 plus prior
exposure, and prior exposure is exactly what does not exist. **(E), (F), (G) all sit
downstream of (A)** and score badly on honesty risk precisely because, without a
recorded operator action, any P&L or fill claim would be fabricated. **(J), (H), (K),
(L)** are real but lower-leverage: none of them unblocks anything else.

**Durable cross-day position state wins**, and it wins on evidence: it is the single
primitive whose absence is cited by name in M073's, M074's *and* M075's own frozen text.

## 4. Selected Capability

**An operator-asserted, event-sourced position ledger.**

The operator explicitly records what they did. The platform derives what is held as of
any timestamp by folding those events. Nothing is ever inferred from a recommendation.

## 5. Rejected Alternatives

| Rejected | Why |
|---|---|
| A mutable `current_position` table | destroys history, cannot answer "as of last Tuesday", and makes replay impossible |
| Deriving positions from approved `PositionPlan`s | **the central honesty error.** An approved plan is a *recommendation*, not an action. Treating it as a position would fabricate holdings the operator never took |
| Broker/live integration | no broker exists; would be a fabricated claim |
| Fill/execution simulation | would imply an order was filled; nothing established that |
| Wiring the ledger into M075's feasibility now | would change M075's frozen meaning. Deferred to M077 by design (Section 21) |

## 6. Architecture

| Layer | Change |
|---|---|
| `identifiers/types.py` | **additive**: `OperatorPositionEventId` |
| `decision_candidate/operator_position_ledger.py` | **new**, pure: event types, the fold, and derived state |
| `decision_candidate/operator_position_ledger_repository.py` | **new**: Protocol |
| `shared/persistence/postgres_repositories/operator_position_event_repository.py` | **new**: adapter |
| `migrations/versions/…_create_m076_operator_position_event_schema.py` | **new**: one additive table |
| `usecases/record_operator_position_event.py`, `usecases/get_operator_position_state.py` | **new** |
| `entrypoints/record_operator_position_event.py`, `entrypoints/get_operator_position_state.py` | **new** CLI |
| `shared/persistence/postgres_repositories/runtime.py` | **additive** property |

**No frozen milestone's semantics change.** M060's `PositionPlan` is untouched: the
ledger *may* cite a plan as motivation via an optional lineage field, but never requires
one and never derives an event from one.

## 7. Domain Semantics

Three event kinds, appended and never mutated:

| Kind | Meaning | Quantity rule |
|---|---|---|
| `OPENED` | operator asserts they took a position | `> 0` |
| `REDUCED` | operator asserts a partial reduction | `> 0`, and `<= currently open` |
| `CLOSED` | operator asserts the remainder is closed | quantity is **derived**, not supplied |

- **What creates a position:** an `OPENED` event, and only that. Never a plan.
- **What changes it:** `REDUCED`.
- **What closes it:** `CLOSED`, or a `REDUCED` that takes the quantity to exactly zero.
- **Stable identity:** `position_key = (instrument_symbol, position_governance_id)`. The
  operator supplies the governance id, so two separate entries in the same instrument are
  two separate keys, and a re-entry after a close is a *new* key, never a resurrection.
- **"Open" means:** net asserted quantity `> 0` at the requested `as_of`.
- **Known vs asserted:** every field is operator-asserted. The type name, the CLI, the
  rendered output and the column comments all say so.

## 8. Persistence Semantics

One additive table, `operator_position_event`, `down_revision = "31365632c016"`:

- `runtime_id` PK, `governance_id` UNIQUE — the idempotency key
- `position_governance_id`, `instrument_symbol`, `event_kind`, `quantity`,
  `asserted_price`, `event_timestamp`, `recorded_at`, `source_position_plan_governance_id`
  (nullable lineage), `note`
- CHECK constraints: `event_kind` in the closed vocabulary; `quantity >= 0`;
  `quantity > 0` for OPENED/REDUCED; `asserted_price > 0`
- Indexes justified by the two real query paths: `(position_governance_id,
  event_timestamp)` and `(instrument_symbol, event_timestamp)`
- `downgrade()` drops the table — fully reversible, and tested up→down→up

**Append-only.** The repository exposes `append` and reads. No update, no delete.

## 9. Usecase Semantics

- `RecordOperatorPositionEventHandler` — validates the event against the *derived state
  at that event's own timestamp*, then appends. Rejects impossible transitions.
- `GetOperatorPositionStateHandler` — folds events with `event_timestamp <= as_of` into
  the derived state.

## 10. Determinism

Fold order is `(event_timestamp, governance_id)` — a total order, since `governance_id`
is unique. Ties on timestamp are therefore deterministic, not arbitrary. Derived state is
a pure function of the event set and `as_of`; the same inputs always produce the same
output, regardless of insertion order.

## 11. Temporal Semantics

- `event_timestamp` — when the operator asserts the action happened. **This alone drives
  the fold.**
- `recorded_at` — when it was written down. Audit only; never affects state.
- `as_of` is **inclusive**: `event_timestamp <= as_of`. A boundary-equality test is
  mandatory.
- Events after `as_of` are excluded — a state query about the past can never see the
  future, even though the row already exists.

## 12. Lineage

`source_position_plan_governance_id` is optional and purely informational. It records
*what motivated* the assertion. It is never required, never validated as a precondition,
and an event with a plan reference is not treated differently from one without — because
the plan did not cause the position; the operator did.

## 13. Error and Absence Semantics

| Situation | Behaviour |
|---|---|
| duplicate `governance_id` | rejected — the unique constraint is the idempotency key |
| `REDUCED` beyond open quantity | rejected, `REDUCTION_EXCEEDS_OPEN_QUANTITY` |
| `CLOSED` on an already-closed key | rejected, `POSITION_ALREADY_CLOSED` |
| `OPENED` on an already-open key | rejected, `POSITION_ALREADY_OPEN` |
| `REDUCED`/`CLOSED` with no prior `OPENED` | rejected, `POSITION_NOT_OPEN` |
| no events at all | explicit empty state, never an error, never "flat" implied as fact |
| quantity `<= 0` on OPENED/REDUCED | rejected by domain and by CHECK |

## 14–18. Compatibility, Preservation, Security

Purely additive: one new table, new modules, new CLIs, one new identifier type, one new
runtime property. **No frozen file's semantics change.** M020/M024 UOW and repository
conventions are reused as-is. M060's `PositionPlan` is read-only to this milestone and in
fact is not read at all. No secret, no credential, no network. The adapter issues
parameter-bound SQL only.

## 19. Testing Strategy

Domain unit tests; usecase tests; repository tests; real-PostgreSQL integration; a
migration up→down→up test; CLI end-to-end; and an adversarial regression test for every
genuine defect found. The specific attacks the mission names — same event twice, ties,
out-of-order insertion, open→reduce→close, double close, multi-instrument, multi-session,
future events excluded, exact-boundary `as_of`, zero and negative quantity, lineage
mismatch, rollback, round-trip equality — are each a named test.

## 20. Acceptance Criteria

1. An operator can record an opening and later see it as held.
2. A partial reduction is reflected in the derived quantity.
3. A close removes it from open state without deleting history.
4. State as of a past timestamp excludes later events.
5. The same event recorded twice is rejected, not double-counted.
6. Impossible transitions are rejected with a named reason.
7. Migration is reversible.
8. Full canonical gates pass with the coverage floor unchanged.

## 21. Explicit Non-Goals

No P&L, realized or unrealized. No fills, orders, execution or broker anything. No
market-value revaluation. No cash ledger, margin or leverage. No paper-trading claim. No
automatic creation of events from plans or sessions. **No modification of M075's
feasibility rule** — consuming this ledger there would change M075's frozen meaning and is
deliberately left to M077.

## 22. Reality and Honesty Constraints

Every name says what it is: `OperatorAssertedPositionEvent`, `operator_asserted`,
`asserted_price`. The words `executed`, `filled`, and `live` appear nowhere as a claim.
The rendered output states that this is what the operator *said* they did — not a
broker record, not a verified fill, not evidence that any trade occurred, and not a
profitability or advice claim. A test enforces the forbidden vocabulary.

## 23. HOSTILE DESIGN REVIEW (pre-implementation)

My own attack on my own design. Not an independent review. Every **FIXED** item was
corrected in this document before a line of code was written.

| # | Attack | Verdict |
|---|---|---|
| D01 | Deriving a position from an approved `PositionPlan` fabricates holdings | PASS — only an `OPENED` event creates a position; lineage is informational and optional |
| D02 | A supplied `CLOSED` quantity could disagree with the open quantity | PASS — `CLOSED` quantity is **derived**, never supplied |
| D03 | `REDUCED` that lands on exactly zero leaves a phantom open position | **FIXED** — defined as closing the key; a named test asserts it |
| D04 | Ties on `event_timestamp` order arbitrarily | PASS — total order `(event_timestamp, governance_id)`, and `governance_id` is unique |
| D05 | **A back-dated event inserted after later events corrupts history** | **FIXED** — this was the sharpest hole. Validation no longer checks "state at this event's timestamp"; it **re-folds the entire resulting sequence for that position key in timestamp order and rejects if any transition becomes invalid.** Otherwise a back-dated `OPENED` could be accepted after a `CLOSED` and silently produce an incoherent ledger |
| D06 | Zero or negative quantity | PASS — rejected in the domain *and* by a CHECK constraint |
| D07 | The same event recorded twice double-counts | PASS — `governance_id` UNIQUE is the idempotency key; the handler surfaces a named error rather than a raw driver exception |
| D08 | `REDUCED` cites a different instrument than the `OPENED` it reduces | **FIXED** — all events sharing a `position_governance_id` must share one `instrument_symbol`; mismatch rejected as `INSTRUMENT_MISMATCH_FOR_POSITION` |
| D09 | Exposing a notional reads as a market value or a P&L | **FIXED** — the field is `asserted_open_notional`, computed at the **asserted entry price**, explicitly labelled as neither market value nor P&L |
| D10 | Confusion with M067/M068 historical replay | PASS — different module, different table, different vocabulary; the banner names the distinction |
| D11 | Two concurrent appends both pass validation | **ACCEPTED AND DOCUMENTED** — the unique constraint prevents duplicates, but two *different* logically-conflicting events could interleave. This is a single-operator CLI primitive; the limitation is stated in the freeze evidence rather than papered over with a lock this milestone cannot justify |
| D12 | Migration is not reversible | PASS — `downgrade()` drops the table; up→down→up is a named test |
| D13 | Text and JSON disagree | PASS — one derived object renders both; parity test |
| D14 | Re-entering an instrument after closing resurrects the old position | PASS — a new entry uses a new `position_governance_id`, hence a new key; re-`OPENED` on a closed key is rejected |
| D15 | Symbols are not validated against `instrument_master` | **ACCEPTED AND DOCUMENTED** — deliberately not coupled, so the primitive stands alone; the operator asserts the symbol and the limitation is stated |
| D16 | `recorded_at` leaks into state | PASS — audit only; the fold reads `event_timestamp` exclusively |
| D17 | A state query about the past sees later rows | PASS — filter is `event_timestamp <= as_of`; a dedicated future-exclusion test |
| D18 | Boundary equality excluded by an off-by-one | PASS — `<=`, with an exact-boundary test |
| D19 | Wiring this into M075 changes M075's frozen meaning | **FIXED** — explicitly a non-goal; deferred to M077 |
| D20 | The words "executed"/"filled"/"live" imply facts not established | PASS — forbidden-vocabulary test over the module and the rendered output |
| D21 | Partial writes leave a half-recorded event | PASS — one row per event, one INSERT; nothing to half-write |
| D22 | Float money | PASS — `Decimal` throughout, `NUMERIC` in the schema |
| D23 | Frozen `identifiers/types.py` is modified | PASS — additive only: one new `Identifier` subclass, no existing type touched |

**No unresolved HIGH or CRITICAL finding remains.** D05 and D08 were genuine correctness
holes and are corrected above; D11 and D15 are accepted, bounded, and documented.
