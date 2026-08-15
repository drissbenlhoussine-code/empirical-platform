# M078 — Hostile Implementation Review

A **new** adversarial pass against the real code and real persistence
behaviour, not a repeat of the design review. Not an independent review — the
same agent wrote the code.

**104 attacks. Three genuine defects found, every one by executing the code
rather than reading it, all fixed, each with a regression test that fails
against the pre-fix implementation.**

The unit suite passed 38/38 on its first run. That was not evidence of
correctness — it was evidence that the tests had not yet been pointed at the
right places. All three defects below were found afterwards, by running
adversarial inputs through the built module.

## Defects found and corrected

### R01 — a position on a different instrument was silently counted as follow-through

**Attack.** A position recorded on `TSLA` citing an `AAPL` plan.

**Expected.** The citation is reported, and the instrument disagreement is
visible.

**Actual.**

```
plan symbol AAPL, position symbol TSLA -> status: ASSERTED_POSITION_OPEN
reported as follow-through? 1
any limitation naming the mismatch? []
```

**Root cause.** Matching was by plan id alone; `instrument_symbol` was carried
on both sides and never compared.

**Severity.** High, and it is an *honesty* defect rather than a mere reporting
gap: the audit asserted that the operator had recorded a position against this
plan's instrument, which is precisely what had not happened.

**Fix.** `PlanFollowThroughEntry.mismatched_instrument_position_ids` plus a
named limitation. The citation is still reported — **dropping it would be its
own dishonesty**, since the citation is what the operator actually recorded.

**Regression tests.** `test_position_on_a_different_instrument_is_flagged_not_silently_counted`,
`test_matching_instrument_produces_no_mismatch_flag`.

### R02 — one plan id naming two instruments silently discarded an entry

**Attack.** Two approved plans sharing a plan id with different symbols.

**Actual.** `entries: [('AAA', 'DUP')]`, `approved_plan_count: 1`, no
limitation — malformed session data disappeared without trace.

**Root cause.** `dict.setdefault` deduplication with no collision detection.

**Severity.** Medium. The input is malformed, but silently discarding it hides
a data problem the operator should see.

**Fix.** The collision is named in `limitations`, stating which entry was
audited. Deduplication still happens — one plan is still one entry.

**Regression tests.** `test_duplicate_identical_plan_entries_produce_no_spurious_limitation`.

> ### ~~R02 disposition~~ — **RETRACTED by owner review of `2c14d0a`**
>
> The fix above — deduplicate deterministically and emit a limitation — is
> **superseded**. It is deterministic but **not semantically safe**: when
> `PLAN-X` names both `AAPL` and `TSLA`, a citation of `PLAN-X` refers to
> neither in particular, and keeping `AAPL` because it sorts first invents an
> answer the session data does not contain. A warning beside a fabricated join
> does not make the join honest.
>
> The correct behaviour is to withhold the entire audit as
> `NOT_ASSESSABLE / SESSION_PLAN_REFERENCES_INCOHERENT`. See
> `owner-correction-pass.md`. The original finding and its insufficient fix are
> left here in place, because what this review got wrong is itself part of the
> record.
>
> The test that asserted the weaker behaviour is corrected in place, with the
> old assertion recorded in its docstring, and is now
> `test_one_plan_id_naming_two_instruments_withholds_the_whole_audit`.

### R03 — a naive `as_of` was reported as corrupt persisted data

**Attack.** Call the handler with a timezone-naive `as_of`.

**Expected.** A request error.

**Actual.** M076's fold raises `LedgerRejectionError: NAIVE_TIMESTAMP`, which
the handler catches and converts to
`NOT_ASSESSABLE / LEDGER_INCOHERENT` — telling the operator their **persisted
events do not fold coherently** when in fact their *request* was malformed.

**Severity.** High. A false diagnosis is worse than a crash: it would send
someone hunting through their database for corruption that does not exist.

**Root cause.** One `except LedgerRejectionError` covering two unrelated
conditions — bad data and bad input — because both travel as the same
exception type.

**Fix.** `AuditResearchDecisionFollowThroughQuery.__post_init__` rejects a
naive `as_of` at construction, before any I/O, so the two can never be
conflated. The CLI converts it into a usage error naming the required offset.

**Regression test.** `test_m078_naive_as_of_is_a_request_error_not_a_data_claim`.

## Attack matrix

| Category | Attacks | Result |
|---|---|---|
| Domain statuses and precedence | 12 | 12 PASS |
| Lineage and matching | 11 | 9 PASS, 2 FIXED (R01, R02) |
| Temporal semantics | 12 | 12 PASS |
| Absence, withholding, malformed data | 11 | 10 PASS, 1 FIXED (R03) |
| Determinism and ordering | 10 | 10 PASS |
| Honesty and vocabulary | 13 | 13 PASS |
| Numeric / no-money guarantee | 7 | 7 PASS |
| Rendering, JSON, CLI | 12 | 12 PASS |
| Persistence and concurrency | 8 | 8 PASS |
| Architecture and frozen preservation | 8 | 8 PASS |

### Selected attacks worth naming

| Attack | Result |
|---|---|
| Any monetary value reaches the output | PASS — executed: neither `123.456789` nor the words `price`/`notional` appear in text or JSON; a test walks every dataclass field and rejects any `Decimal` or money-named field |
| A closed position's asserted **exit** price leaks | PASS — executed with an exit price of `110` and again of `415.999999`; neither appears in any rendering |
| `NO_ASSERTED_POSITION_RECORDED` renders without its caveat | PASS — the caveat is emitted unconditionally and asserted by test |
| A reduced-to-zero position counts as open | PASS — executed; reports `ASSERTED_POSITION_CLOSED`, matching M076's fold |
| A plan cited by both an open and a closed position loses one | PASS — precedence documented, both counts retained |
| A closed position appears as "unlinked" | PASS — only open positions can be unlinked |
| A position opened after `as_of` is counted | PASS — excluded by M076's filter; count surfaced |
| Exactly-at-`as_of` and one microsecond after | PASS — inclusive boundary, both directions tested |
| Two offsets for one instant disagree | PASS |
| Unlinked ordering depends on set iteration | PASS — executed with same-symbol positions; `('PAA','PZZ')` |
| Counts drift from entries when a mismatch is present | PASS — executed; counts still sum to `len(entries)` |
| A mismatched position is double-reported as unlinked | PASS — executed; it is matched, so it is not unlinked |
| Text and JSON disagree | PASS — executed field by field over real persisted rows |
| M077 and M078 contradict each other on the same ledger | PASS — a named integration test asserts M077 suppresses the plan as already-acted while M078 reports the same position as an open assertion citing it |
| `entrypoints` imports `decision_candidate` | PASS — architecture checker exit 0 |
| M076 or M077 source modified | PASS — `git diff` shows neither touched |
| A database failure is disguised as a soft verdict | PASS — only `LedgerRejectionError` is caught; a broken database propagates |

## Accepted, with reasons

| # | Item | Reason |
|---|---|---|
| A1 | A database-level failure propagates rather than becoming `LEDGER_UNAVAILABLE` | A dead connection is an infrastructure fault, not an absence of records. The M077 A1 precedent |
| A2 | A position citing a plan that never existed is reported as `CITES_PLAN_OUTSIDE_THIS_SESSION` | From this session's view that is exactly what it is; proving global non-existence would require reading every session |
| A3 | The audit reads the session and the ledger in two statements | The session is immutable once persisted and the ledger is read once, so the pairing is coherent |

## Retractions

**None.** No verdict in this review has been retracted. Design-review items
C10, G05, H02 and B07 were re-attacked here and all four held.
