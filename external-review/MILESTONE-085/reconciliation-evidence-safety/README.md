# M085 reconciliation evidence safety (REV-R1) and strict boundary parsing (REV-R2)

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Local commits only; not pushed,
not merged, not frozen, not OWNER_ACCEPTED, not READY_FOR_PAPER. Paper acceptance NOT_STARTED. M086
NOT_STARTED. No Alpaca call of any kind; no real Proposal/Approval/Intent; no acceptance-database
mutation; every test ran against controlled fakes and the disposable PostgreSQL database
`m085_pgon_b24c471`. M083/M084 frozen paths untouched; no authentication, privilege or
security-policy change; the unrelated Claude worktree untouched.

Reviewed baseline: published head `e7a089a06c518800682b232b8719d6f05e4224a2` (L1 code `806896b`,
V1 renderer `05eec31`). The local count-correction commit
`94ffe908067e3b5bf10753352afe0abeaf258b24` (24 → 21 collected ids) is preserved as the parent of
this round's commits and rides with this candidate rather than in a separate publication loop. The
reviewer's findings came from isolated copied-function probes; both were **reproduced through the
production handlers** (fakes) and **on PostgreSQL across process restarts** before any edit.

## 1. REV-R1 — absence could revoke what had been observed

### 1.1 What the reviewed code did

`ReconcilePaperOrderHandler._handle_absence` counted **every** `RECONCILE`/404 acknowledgement of
the attempt (`len([... if http_status == 404])`), not the trailing consecutive run, and applied
the bounded not-found policy (2 observations, ≥ 60 s) to **any** non-terminal state other than
`SUBMISSION_IN_PROGRESS`. A reconciliation lookup that raised left no acknowledgement and no event.
Consequences, all reproduced:

| Case | Sequence | Reviewed outcome (`e7a089a` content) | Later reconciliation possible |
|---|---|---|---|
| A. ambiguous POST (1 request left; `SUBMISSION_UNKNOWN` / `UNCERTAIN_HTTP_503`) | 404 → 500 → 404 | `REJECTED` / `NOT_FOUND_AT_BROKER` at the third answer; acks `SUBMIT 503, RECONCILE 404, RECONCILE 500, RECONCILE 404`; events `…INSUFFICIENT, RECONCILE_UNUSABLE_ANSWER, RECONCILE_RESOLVED_NOT_FOUND` | no (terminal) |
| A′. same, the middle lookup **raises** | 404 → exception → 404 | the exception propagated with **no record**; acks `RECONCILE 404, RECONCILE 404` read as consecutive → `REJECTED` | no |
| B. accepted order, `PAPER_ACCEPTED`, `broker_order_id=broker-1` persisted | 404 → 404 | `REJECTED` / `NOT_FOUND_AT_BROKER`; broker id retained on the row but the order is terminally "rejected" (`PAPER_ACCEPTED → REJECTED` is an allowed edge, so the database trigger does not stop it) | no |
| C. inconclusive pre-send lookup (`IDENTITY_UNRESOLVED_UNSENT`, **0 POSTs**) | 404 → 200 (existing order, observed, **not attributed**) → 404 | `REJECTED` / `NOT_FOUND_AT_BROKER`; the positive observation (`RECONCILE 200 broker-historical`, `IDENTITY_OBSERVED_NOT_ATTRIBUTED`) discarded | no |

Unit facts per step: `rev/facts-on-e7a089a.txt`; unit suite on the reviewed content
(`tests/unit/test_m085_absence_policy.py`): 4 failed / 2 passed (`rev/unit-reproduction-on-e7a089a.txt`);
PostgreSQL with a fresh persistence service per "process"
(`tests/integration/test_m085_absence_policy_postgres.py`): A, B, C all `REJECTED NOT_FOUND_AT_BROKER`
(`rev/postgres-reproduction-on-e7a089a.txt`). **REV-R1: REPRODUCED**, through production paths and
across restarts. POST counts in every case: A/A′/B 1, C 0 — nothing was ever resent.

### 1.2 The correction

Domain (`decision_candidate/paper_execution.py`):
- `BOUND_ORDER_STATES` = {`PAPER_SUBMITTED`, `PAPER_ACCEPTED`, `PARTIALLY_FILLED`, `CANCEL_REQUESTED`}.
- `POSITIVE_OBSERVATION_EVENT_TYPES` = {`IDENTITY_OBSERVED_BEFORE_SEND`, `CLIENT_ORDER_ID_COLLISION`,
  `IDENTITY_OBSERVED_NOT_ATTRIBUTED`, `IDENTITY_COLLISION_MISMATCH`, `RECONCILED`};
  `attempt_positively_observed(acknowledgements, events)` — any acknowledgement carrying a broker
  order id or an echoed client_order_id, or any of those events.
- `RECONCILE_LOOKUP_FAILED_EVENT_TYPE`; `consecutive_not_found_suffix(acknowledgements, events)` —
  the trailing run of `RECONCILE`/404 answers in `sequence` order; any other answer ends the run;
  a recorded lookup failure at or after the run began discards the answers before it.

Usecase (`usecases/paper_execution.py`):
- `handle`: a lookup that raises is recorded as `RECONCILE_LOOKUP_FAILED` (event id
  `EVT-<attempt>-RECON-FAIL-<n>`) and then **re-raised**.
- `_handle_absence` (after the unchanged `IN_PROGRESS` "dispatcher may be live" rule): a bound
  order → `RECONCILE_NOT_FOUND_KNOWN_ORDER`, state and broker id unchanged; an UNKNOWN that carries
  a broker id or was positively observed → `RECONCILE_NOT_FOUND_AFTER_OBSERVATION`, unchanged;
  otherwise the bounded policy over `consecutive_not_found_suffix`. Absence-event ids are keyed on
  the acknowledgement **sequence**, not the run length (the run length repeats once a run is
  broken — the PostgreSQL primary key caught that during this round; the fakes could not).

The distinctions the record now keeps: never positively observed (policy applies, over the
consecutive run) · previously observed but not attributable (surfaced, never resolved by absence)
· acknowledged and bound to this attempt (surfaced, never revoked) · current lookup unavailable
(`RECONCILE_UNUSABLE_ANSWER` for a non-404 answer, `RECONCILE_LOOKUP_FAILED` for a raise; both
break the run) · confirmed broker lifecycle outcome (only a FOUND order moves the state, as
before). No retry, no replacement identity, no cancellation, no liquidation, no new threshold.
`MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS = 2` and `MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS = 60`
are unchanged.

**Authority contract.** `current-authority.md` states that "a single not-found answer does not
resolve an unknown outcome — the policy requires repeated observations and elapsed time" and that
the policy is "a stated, reviewable CHOICE … not a proof that the order never existed";
`RECONCILIATION_UNKNOWN_POLICY` names `minimum_consecutive_not_found_observations`. The correction
implements "consecutive" as written and narrows the policy's applicability to an outcome that was
never observed; it does not change the published constants or wording (renderer `--check` green).
No contract change is required.

### 1.3 Corrected behaviour (unit and PostgreSQL restarts)

| Case | Now | Still reconcilable |
|---|---|---|
| A | third answer → `SUBMISSION_UNKNOWN`, cause unchanged, `RECONCILE_NOT_FOUND_INSUFFICIENT` ×2; a **consecutive** second 404 afterwards resolves it → `REJECTED` / `NOT_FOUND_AT_BROKER` (positive control) | yes |
| A′ | `RECONCILE_LOOKUP_FAILED` recorded, exception re-raised; the next 404 starts a new run of 1 → unchanged | yes |
| B | `PAPER_ACCEPTED` / `broker-1` unchanged after both 404s, `RECONCILE_NOT_FOUND_KNOWN_ORDER` ×2; a later found `filled` → `FILLED` | yes |
| C | `SUBMISSION_UNKNOWN` unchanged, `RECONCILE_NOT_FOUND_AFTER_OBSERVATION`; never attributed, never resent; a new dispatch is refused | yes |
| never observed UNKNOWN | 404, 404 ≥ 60 s → `REJECTED` / `NOT_FOUND_AT_BROKER` (positive control) | — |
| `SUBMISSION_IN_PROGRESS` | never resolved by absence (unchanged rule) | yes |

Two existing tests encoded the defect and were rewritten: `TestReconcilePaperOrder::
test_one_not_found_does_not_resolve_an_unknown_outcome` and
`::test_the_bounded_policy_resolves_only_with_enough_observations_and_time` built a
`PAPER_SUBMITTED` attempt **with** `broker-1` bound and expected two 404s to reject it; they now
run on a never-observed UNKNOWN fixture, and a new test pins that the bound order is never changed
and is recorded (`test_not_found_never_changes_a_bound_order_and_records_it`).

## 2. REV-R2 — boundary evidence parsed strictly

`_binding_fields` (reviewed) split on whitespace, skipped tokens without `=`, and let a later
duplicate key overwrite an earlier one, so ambiguous or damaged evidence could still satisfy
`send_boundary_event_binds`. Now `parse_send_boundary_binding(detail) -> dict | None` accepts
**exactly** `SEND_BOUNDARY_BINDING_KEYS` = (`attempt`, `authorization`, `fingerprint`, `account`,
`client_order_id`, `identity_lookup`): six tokens, single-space separated, in that order, each
`key=value` with a non-empty value containing no whitespace and no `=`; anything else → `None`,
and a `None` binding lends no lineage. The producer `send_boundary_binding` refuses values that
could not be parsed back (`ValueError`). Negative tests (`tests/unit/test_m085_boundary_binding_parser.py`,
36 ids): identical and conflicting duplicates (appended and in place of another field), empty
value, malformed tokens (no `=`, two `=`), missing field, truncation before the separator and at
the separator, unknown field (appended; replacing a required one), fields out of order, double
space, leading/trailing space, key case, embedded whitespace, empty record, non-string detail; a
value-truncated but well-formed record (`identity_lookup=4`) parses and is refused at the binding
step; well-formed records for another attempt/authorization/fingerprint/account/identity lend
nothing; one valid record among damaged ones still binds (positive control). No typed-column
migration: the strict parser removes the demonstrated ambiguity without one. No legacy record is
invented or backfilled.

## 3. Mutation families (153 → 160)

| Family | Rule removed | Detecting test |
|---|---|---|
| `absence_counts_only_the_consecutive_suffix` | the run's `break` → `continue` (every historical 404 counts) | case A |
| `lookup_failure_breaks_the_absence_run` | a recorded failure no longer discards earlier answers | case A′ |
| `lookup_failure_is_recorded` | the failure event is not written | case A′ |
| `absence_never_rejects_a_known_order` | bound-order branch removed | case B |
| `absence_never_revokes_a_positive_observation` | observed-UNKNOWN branch removed | case C |
| `binding_parser_rejects_padding_and_duplicates` | token-count rule removed | `[identical duplicate appended]` |
| `binding_parser_requires_canonical_keys` | per-position key check removed | `[fields out of canonical order]` |

Positive controls retained: valid canonical binding; actual send + lost acknowledgement + recovery
(`test_m085_pre_send_crash.py` C, PostgreSQL child death); preparation crash with 0 POSTs and no
attribution; one inconclusive lookup non-terminal; expiry/kill-switch after a slow boundary write;
no duplicate send after restart; two consecutive 404s still resolve a never-observed UNKNOWN.
Results: [verification.md](verification.md).

## 4. Boundaries

Local commits only; no push. No Alpaca call. No real Proposal/Approval/Intent; no
acceptance-database mutation. No M086, authentication, privilege or security-policy change.
M083/M084 frozen paths protected; V1's narrow correction intact (its rows are untouched by this
round; Owner ratification of the table remains separate).
