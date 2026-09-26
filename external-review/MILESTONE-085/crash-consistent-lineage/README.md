# M085 crash-consistent attempt lineage (review finding L1)

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Local commits only; not pushed,
not merged, not frozen, not OWNER_ACCEPTED, not READY_FOR_PAPER. Paper acceptance NOT_STARTED.
M086 NOT_STARTED. No Alpaca call of any kind, no real Proposal/Approval/Intent, no
acceptance-database mutation; every test ran against controlled fakes and the disposable
PostgreSQL database `m085_pgon_b24c471`. M083/M084 frozen paths untouched. No authentication,
privilege or security-policy change.

Review base: published head `6b6518c29550292a713c069b462e577485845584`, tested code
`00716e460ffdb7de99f554d443e05c3ddf9003a9`. The unpublished evidence commit
`b80ef2829867aa7684bd4dc6dc666e2b958b2f13` (exact-head CI record for `6b6518c`) is preserved as
the parent of this round's commits. The attached proposed regression
`test_m085_pre_send_crash_review.py` was **not present** on this machine (not in the message, the
repository, the scratchpad or the user's download/desktop folders); the regression below was
written from the three scenarios the finding names, on the existing helpers, preserving the
invariant and the positive control.

## 1. The finding, and what the code did

L1 (HIGH). `SubmitAuthorizedPaperOrderHandler.handle` persists `SUBMISSION_IN_PROGRESS`
(`usecases/paper_execution.py`, the transition right after the claim) **before** `before_send`
runs — before the identity lookup, the configuration/clock/quote reads, the kill-switch read and
`final_send_refusal`. `attempt_may_have_transmitted` returned True for that state unless an
UNSENT failure code or event had already been persisted. A process that died during the pre-send
lookup, or after finding an existing order but before `_identity_observed` persisted anything,
left neither marker. Reconciliation (≥ 60 s later, in a new process) then found the historical
order under the derived `client_order_id`, matched every term and the account, saw "lineage", and
attributed it — `PAPER_SUBMITTED` → `FILLED` with `broker_order_id=broker-historical` — to an
attempt that transmitted zero requests. A crash-consistency gap between preparation and possible
transmission; not a duplicate-order path (nothing is ever resent).

## 2. Reproduction BEFORE any production edit (executable content identical to `00716e4`)

### 2.1 Unit, `BaseException` death (first reproduction) — `l1/unit-reproduction-on-00716e4.txt`, `l1/facts-on-00716e4.txt`

| Scenario | At death | After restart + reconcile (+61 s) |
|---|---|---|
| A. historical order exists; death DURING the pre-send lookup | `SUBMISSION_IN_PROGRESS`, failure_code None, broker_order_id None, **POSTs 0**, acks 0, attempt events [], lineage **True** | **`FILLED`, `broker_order_id=broker-historical`, event `RECONCILED`, POSTs 0** — attributed |
| B. historical order FOUND; death before the observation was persisted | same as A | same as A — attributed |
| C. positive control: our POST left; death before the acknowledgement | `SUBMISSION_IN_PROGRESS`, **POSTs 1**, lineage True | `PAPER_ACCEPTED`, `broker_order_id=broker-1`, POSTs 1 — legitimate recovery, no resend |

`tests/unit/test_m085_pre_send_crash.py` on `00716e4`: 4 failed (A, B, "death before the lookup",
the bare predicate) / 1 passed (C).

### 2.2 PostgreSQL, REAL process death — `l1/postgres-child-reproduction-on-00716e4-run2.txt`

`tests/integration/test_m085_pre_send_crash_postgres.py` spawns
`tests/integration/_m085_crash_child.py` (`python -m`), which runs the production submit handler
over its own `PostgresPersistenceService` on the shared disposable database and terminates with
`os._exit(3)` — no unwinding, no `finally` — at the boundary (A: inside the lookup, having asked
about exactly the derived id; B: at the first persistence call after discovery, placed by a
delegating wrapper because the repositories use `__slots__`; C: at the first persistence call after
the POST). The parent reconnects through a **fresh** service, reads the rows, and reconciles.

On `00716e4`: A and B — `the historical order was attributed: state=FILLED
broker_order_id=broker-historical events=['AUTHORIZATION_GRANTED', 'PREVIEW_CREATED', 'RECONCILED']`,
child exit 3, parent broker fake received nothing; C passed (child recorded `post_count: 1`,
recovery attributed `broker-child-1`, no resend). (A first run, `…-on-00716e4.txt`, stopped at
the lineage predicate for A and failed B/C on the `__slots__` patching; kept.)

**L1: REPRODUCED**, at unit level and with a real child-process death against PostgreSQL.

## 3. The correction — a persisted phase distinction

### 3.1 Domain (`decision_candidate/paper_execution.py`)

- `SEND_BOUNDARY_EVENT_TYPE = "SEND_BOUNDARY_ENTERED"`: the append-only event that records that
  THIS attempt entered the phase in which transmission is possible.
- `send_boundary_binding(...)` — the event detail:
  `attempt=… authorization=… fingerprint=… account=… client_order_id=… identity_lookup=404`.
- `send_boundary_event_binds(event, attempt, *, account_reference=None)` — the event must name the
  attempt (`attempt_id`) and its detail must equal the attempt's `attempt_id`, `authorization_id`,
  `request_fingerprint`, `client_order_id`, carry `identity_lookup=404` (identity verified absent),
  and — when the caller knows it — the authorized account. Field by field; nothing borrowed.
- `reached_send_boundary(attempt, events, *, account_reference=None)`.
- `attempt_may_have_transmitted(attempt, events, *, account_reference=None)`: UNSENT markers (code
  or event) still deny first; then `SUBMISSION_IN_PROGRESS` → `reached_send_boundary`; UNKNOWN with
  `AMBIGUOUS` / `UNUSABLE_ANSWER` / `UNCERTAIN_HTTP_*` → transmitted-looking code **and**
  `reached_send_boundary`; acknowledged states → True (they carry a broker id the broker echoed).
  **The absence of an unsent marker proves nothing.** Legacy uncertain records without the event
  stay visible and unresolved (observed, never attributed); nothing is backfilled.

The three durable phases the record now distinguishes:

| Phase | Durable evidence | Lineage |
|---|---|---|
| preparation / identity verification (transmission not yet possible) | `SUBMISSION_IN_PROGRESS`, no `SEND_BOUNDARY_ENTERED` for this attempt | none — a found order is observed, not attributed |
| send-capable (transmission may have occurred) | `SEND_BOUNDARY_ENTERED` bound to the attempt, authorization, request, account, identity (404) | yes, for `IN_PROGRESS` and for a transmitted-looking UNKNOWN |
| observed identity / uncertain identity / known outcome | `IDENTITY_*` events and `IDENTITY_EXISTS_*`/`IDENTITY_UNRESOLVED_UNSENT` codes; acknowledgements; acknowledged states | as before: unsent markers deny; acknowledged states carry the broker's id |

### 3.2 Usecase (`usecases/paper_execution.py`)

`before_send` now: 1 identity lookup → 2 configuration, broker clock, quote →
**3 `_enter_send_boundary(...)`: the boundary event is written (a database write that may
block)** → 4 kill switch → 5 time sampled, `require_broker_certainty_within`, `final_send_refusal`
→ 6 nothing else; the transport POSTs. A6 is not reintroduced: the write precedes the final
kill-switch read and the time sample, so an authorization that expires or a kill switch that
engages **during** the write is seen (tests below: zero POSTs). A database failure during the
write raises out of `before_send`; the transport reports a definite not-sent; the attempt closes
`REJECTED` / `NOT_SENT` (nothing at the broker). If that transition fails too, the process ends
with the error and the record is `SUBMISSION_IN_PROGRESS` without the event — no lineage.
`ReconcilePaperOrderHandler` passes `account_reference=authorization.account_reference` into the
lineage check. The write does **not** claim the broker received anything; it records that the
request could leave. No new state, no migration: the event table is append-only and event types
are strings; the authority contract is unchanged (renderers `--check` green).

### 3.3 The accepted residual window

A death **after** the boundary event and before the POST leaves lineage with no request sent.
That is what the record is for — an order found later under this identity may be ours — and it
is bounded by the `identity_lookup=404` the record carries: a historical order did not exist at
the boundary. Documented and pinned by
`test_a_death_right_after_the_boundary_write_is_lineage_by_design` (absence still never resolves
it; nothing is sent).

## 4. Tests collected

`tests/unit/test_m085_pre_send_crash.py` (24 ids): A, "death before the lookup", B, C; the
predicate on a bare record (incl. a legacy UNKNOWN/AMBIGUOUS without the event → False); a
boundary record that does not bind (8 tampers: event attempt id, attempt, authorization,
fingerprint, client_order_id, `identity_lookup=200`, account, event type); a tampered account in
the persisted record blocks attribution even after our POST; death during the boundary write;
death right after it (the window); database failure at the write → `NOT_SENT`, 0 POSTs; database
failure at the write and at the refusal → `IN_PROGRESS`, no lineage; authorization expiring during
the write → 0 POSTs (unsent outranks the boundary record); kill switch engaged during the write →
0 POSTs; a concurrent reconciliation during preparation attributes nothing and the dispatcher
then observes the order and sends nothing. `tests/integration/test_m085_pre_send_crash_postgres.py`
(3 ids, real child death) + `tests/integration/_m085_crash_child.py`.
`tests/unit/test_m085_send_boundary.py`: the ordering test now also pins `configuration/clock/quote
< persist_boundary < kill_switch < POST`. `tests/unit/test_m085_identity_lineage.py`: the
event-outranks-state cases start from a bound boundary record.

Tests that encoded the gap and were corrected (not weakened — the interruption moves to AFTER the
request left, and they now also assert exactly one POST): `test_m085_temporal_postgres.py::
test_reconciliation_resolves_an_interrupted_dispatch_through_the_database_edges` (it replaced
`submit_order` wholesale, i.e. died before any send, and asserted adoption) and
`test_m085_corrective_pass_handlers.py::TestAnInterruptedDispatchCanBeReconciled._stuck_in_progress`
(same shape; its consumers' lookup counts now include the dispatcher's own pre-send lookup).

## 5. Mutation families (148 → 153)

| Family | Rule removed | Detecting test |
|---|---|---|
| `lineage_requires_the_send_boundary_record` | `IN_PROGRESS` → `return True` (unconditional lineage restored) | crash A |
| `send_boundary_record_is_bound_field_by_field` | binding comparison → `return True` | tamper `[authorization_id]` |
| `send_boundary_recorded_before_the_send` | the boundary write removed | positive control C (recovery cannot attribute) |
| `final_checks_follow_the_boundary_write` | kill switch read BEFORE the write | kill switch engaged during the write |
| `historical_adoption_requires_the_account_binding` | reconcile passes `account_reference=None` | tampered account blocks attribution |

Anchors renumbered for two existing families (`# 5.` → `# 6.`, `# 4.` → `# 5.`). Results of the
pre-commit and exact-SHA runs: [verification.md](verification.md).

## 6. Boundaries

Local commits only. No push. No Alpaca call. No real Proposal/Approval/Intent, no
acceptance-database mutation. No M086, authentication, privilege or security-policy change.
M083/M084 frozen paths protected (guard in the verification). The unrelated Claude worktree
(`.claude/worktrees/serene-yalow-f53f00`) was not touched.
