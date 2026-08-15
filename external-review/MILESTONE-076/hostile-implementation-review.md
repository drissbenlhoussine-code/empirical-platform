# M076 — Hostile Implementation Review

My own attack on my own diff. Not an independent review.
`PASS` held · `FIXED` genuine defect found and corrected · `ACCEPTED` bounded and documented.

## Genuine defects found and fixed

**I-01 — I broke 74 previously-passing tests by appending an identifier class in the
wrong place.** The new `OperatorPositionEventId` landed between `ResearchSessionId`'s
docstring and its `prefix = "RESEARCH"` line, so `ResearchSessionId` silently inherited
the empty base prefix (pattern `^-\d{4}$`) and the new class stole `RESEARCH`. The full
regression caught it: 82 failures with PostgreSQL off against a baseline of 8. Fixed by
restoring `types.py` from master and appending correctly with its own `OPEV` prefix.
Regression test asserts **the whole identifier registry** has no empty prefix, so a
future append cannot repeat it.

**I-02 — `LedgerRejectionError` was unraisable in some paths.** It was a
`@dataclass(frozen=True, slots=True)` over `Exception`. `slots=True` rebuilds the class
object, which breaks zero-arg `super()` resolution, and the error raised
`TypeError: super(type, obj): obj … is not an instance or subtype of type` when rendered.
Unit tests missed it because they only read `.reason`; **integration testing exposed it.**
Now a plain exception with an explicit `__init__`. Regression test raises it, stringifies
it, and reprs it.

**I-03 — money strings depended on the database column scale.** PostgreSQL
`NUMERIC(20,6)` returns `Decimal("750.000000")`, which `==` `Decimal("750")` but does not
`str()` the same, so the identical position rendered differently from memory and from the
database. Found by integration testing. Fixed with a canonical `_money()`
(`normalize()` then `format(…, "f")`, since `normalize()` alone yields `7.5E+2`).
Regression test pins memory-vs-database equality and that `10.25 × 2 == "20.5"`.

**I-04 — the CLI violated a frozen architecture boundary.** `entrypoints` may not import
`decision_candidate`, and my first entrypoints did. **The architecture checker caught it.**
Fixed properly rather than suppressed: the application layer gained a primitive-only
builder and view, and `run_get_operator_position_state` now returns the finished rendering,
so no domain object crosses the boundary at all. A follow-on `Any` shortcut was itself
rejected by `ANN401` and removed.

## Matrix

### Domain invariants
| # | Attack | Disposition |
|---|---|---|
| 01 | A position is created from an approved `PositionPlan` | PASS — only `OPENED` creates one; a test proves lineage never changes the fold |
| 02 | `CLOSED` quantity supplied by the operator disagrees with reality | PASS — derived; a test passes `999999` and asserts `70` |
| 03 | `REDUCED` to exactly zero leaves a phantom open position | PASS — closes the key; named test |
| 04 | Reduction exceeds open quantity | PASS — `REDUCTION_EXCEEDS_OPEN_QUANTITY` |
| 05 | Second close | PASS — `POSITION_ALREADY_CLOSED` |
| 06 | Reduce/close with no open | PASS — `POSITION_NOT_OPEN` |
| 07 | Double open on a live key | PASS — `POSITION_ALREADY_OPEN` |
| 08 | Reopen a closed key | PASS — rejected; re-entry needs a new position id |
| 09 | Zero quantity | PASS — rejected in domain and by CHECK |
| 10 | Negative quantity | PASS — same |
| 11 | Instrument mismatch inside one position key | PASS — `INSTRUMENT_MISMATCH_FOR_POSITION` |
| 12 | Float money | PASS — `Decimal` throughout, `NUMERIC` column |

### Temporal
| # | Attack | Disposition |
|---|---|---|
| 13 | A past query sees a later event | PASS — `event_timestamp <= as_of`; CLI-verified |
| 14 | Exact-boundary `as_of` excluded by an off-by-one | PASS — inclusive; named test |
| 15 | `recorded_at` leaks into state | PASS — test varies it by 999 days, state identical |
| 16 | Back-dated event corrupts a later one | PASS — whole sequence re-folded; unit **and** integration tests |
| 17 | Naive timestamp accepted from the CLI | PASS — rejected, explicit offset required |

### Determinism and ordering
| # | Attack | Disposition |
|---|---|---|
| 18 | Input order changes the result | PASS — reversed input, identical output |
| 19 | Timestamp ties order arbitrarily | PASS — `(event_timestamp, governance_id)` total order |
| 20 | Dict/set iteration leaks | PASS — grouping sorts explicitly |
| 21 | SQL returns rows in an unstable order | PASS — every query has `ORDER BY event_timestamp, governance_id` |

### Persistence
| # | Attack | Disposition |
|---|---|---|
| 22 | Same event recorded twice | PASS — domain rejects, and the unique constraint is the durable backstop; integration asserts `count == 1` |
| 23 | Adapter can mutate history | PASS — only INSERT and SELECT exist; no UPDATE, no DELETE |
| 24 | Round-trip loses a field | PASS — full-object equality test through the database |
| 25 | Lineage column lost | PASS — raw SQL asserts the plan id present on one row, `NULL` on the other |
| 26 | Migration not reversible | PASS — up→down→up test using `to_regclass` |
| 27 | Migration not on the real head | PASS — `down_revision = 31365632c016`, verified as the unique head |
| 28 | SQL injection via built strings | PASS — literal SQL, bound parameters; the f-string version was removed rather than `# noqa`'d |
| 29 | CHECK constraints absent | PASS — kind vocabulary, non-negative quantity, positive quantity for OPENED/REDUCED, positive price |
| 30 | Rejected event still persisted | PASS — integration asserts the row count is unchanged after a rejection |

### Frozen-boundary preservation
| # | Attack | Disposition |
|---|---|---|
| 31 | A frozen milestone's semantics changed | PASS — no M057–M075 source file modified; see `changed-files.txt` |
| 32 | `PositionPlan` altered | PASS — untouched, and not even read |
| 33 | M075's feasibility silently consumes the ledger | PASS — deliberate non-goal, deferred to M077 |
| 34 | `entrypoints` imports `decision_candidate` | FIXED (I-04) |
| 35 | Existing identifier types disturbed | FIXED (I-01), with a registry-wide regression test |
| 36 | Existing migration edited | PASS — only a new revision added |
| 37 | Runtime composition broken for existing repositories | PASS — additive slot and property only; full suite green |

### Honesty
| # | Attack | Disposition |
|---|---|---|
| 38 | Vocabulary implies execution | PASS — `OPENED`/`REDUCED`/`CLOSED`; test asserts no `EXECUTED`/`FILLED`/`LIVE_`/`BROKER_` |
| 39 | Notional reads as market value or P&L | PASS — `asserted_open_notional`, plus an explicit limitation line |
| 40 | Output implies a broker record | PASS — banner in text and JSON; CLI-verified |
| 41 | Empty state implies a verified flat account | PASS — wording says it reflects what the operator recorded |
| 42 | Text and JSON disagree | PASS — one object renders both; parity test |
| 43 | A profitability or advice claim appears | PASS — none; banner disclaims both |

### Operator misuse and recovery
| # | Attack | Disposition |
|---|---|---|
| 44 | Missing required CLI option | PASS — usage error naming the option |
| 45 | Unparseable price/quantity/timestamp | PASS — usage error |
| 46 | Rejection surfaces as a stack trace | PASS — `SystemExit("rejected: …")` |
| 47 | Reconstruction after restart | PASS — state is derived from rows every call; the CLI proves it across separate processes |
| 48 | Two concurrent appends both validate | ACCEPTED — the unique constraint stops duplicates; two *different* conflicting events could interleave. Single-operator CLI primitive; documented in `known-limitations.md` rather than locked with a mechanism this milestone cannot justify |
| 49 | Symbol not validated against `instrument_master` | ACCEPTED — deliberately uncoupled so the primitive stands alone; documented |
