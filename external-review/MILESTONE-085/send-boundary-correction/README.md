# M085 send-boundary and identity-recovery correction

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Not pushed, not merged,
not frozen, not deployed, not OWNER_ACCEPTED, not READY_FOR_PAPER. M086 NOT_STARTED. No Paper
or Live order was submitted, no Alpaca endpoint was called (not even read-only), no real
Proposal/Approval/Paper Intent was created, and the acceptance database
`m085_acceptance_2e5c38c` was neither read nor written in this round. Every test in this
round ran against controlled fakes, a local hostile HTTP server bound to 127.0.0.1, or a
disposable PostgreSQL database.

Base of this correction: `2726f6f` (the published final candidate, PR #15) with the docs-only
commit `38dc069` on top. The commit that contains this document is the code candidate; its
SHA (`CODE_CANDIDATE_SHA`) is reported in the round report and the exact-SHA verification of it
is recorded in [verification.md](verification.md) by a docs-only follow-up, because a document
cannot name the commit that first contains it.

## 1. What was wrong on `2726f6f`

The focused pre-Paper review of `2726f6f` ([../final-candidate-2726f6f/README.md](../final-candidate-2726f6f/README.md))
found:

| Id | Severity | Finding |
|---|---|---|
| A6 | HIGH, blocked Paper acceptance | The pre-send identity lookup (`GET /v2/orders:by_client_order_id`) ran as the LAST step of the in-connection guard, after `final_send_refusal` had already decided. A slow lookup let a POST leave after the authorization or intent expired, after the kill switch was engaged, after the quote went stale, or after the market closed. |
| B | MEDIUM | An order found under our `client_order_id` was ADOPTED whenever its symbol/side/quantity/type matched — by a fresh attempt, by a pre-send find, or by a reconstructed database — without any persisted evidence that THIS authorization created it. Identity comparison also existed in three variants (adapter acknowledgement, usecase collision check, reconciliation) that compared different field sets and none compared `limit_price`, `time_in_force` or `extended_hours`. |
| B2 | MEDIUM | A pre-send lookup that failed (exception, 5xx, malformed body) became a terminal REJECTED, discarding the possibility that the broker holds an order under our identity. |
| B3 | LOW | Definitive refusal was decided by HTTP status alone (`{400, 401, 403, 422}`) plus a shape test for the duplicate 422; an undocumented code under a "definitive" status was still treated as proof that nothing exists. |

### Defect-exposing tests were run BEFORE any production edit

[defects-on-2726f6f.log](defects-on-2726f6f.log) records the new regression suites executed
against the `2726f6f`/`38dc069` production code (identical executable content) before the fix:

| Suite | On `2726f6f` | Meaning |
|---|---|---|
| `tests/unit/test_m085_send_boundary.py` | **12 failed**, 7 passed | POSTs left after expiry / kill switch / stale quote / market close during a slow lookup; kill switch engaged during ANY slow read let the POST leave (`assert 'kill_switch' == 'lookup'` — the lookup ran after the decision). Four of the failures are the harness itself refusing to build an authorization outliving the intent; they are fixed in the test, not the product, and are listed so the log is read honestly. |
| `tests/integration/test_m085_send_boundary_transport.py` | **1 failed**, 1 passed | Through the REAL `AlpacaPaperClient` and real HTTP framing: the kill switch flipping during a slow lookup still produced a POST (count 1, expected 0). The positive control (1 POST while permitted) passed. |
| `tests/integration/test_m085_acknowledgement_terms_http.py` | **8 failed**, 7 passed | The real adapter accepted an acknowledgement whose `limit_price`, `time_in_force` or `extended_hours` differed from what was sent, and substituted expected values for missing ones. |
| `tests/unit/test_m085_identity_lineage.py` | ImportError | Tests target the corrected API (`order_terms_mismatches`, `attempt_may_have_transmitted`, `RECOGNIZED_DEFINITIVE_REFUSAL_CODES`); the old API had no lineage concept to test. |

## 2. What changed

### 2.1 The send boundary (A6) — `usecases/paper_execution.py::before_send`

The in-connection guard now runs, in this order and with nothing after step 5:

1. **Identity lookup FIRST.** `fetch_order_by_client_order_id(derived id)`. Found → `BrokerIdentityExistsError(request_sent=False)`. Exception, non-404 status, or a body that cannot be read → `BrokerIdentityUnresolvedError`. Only a definite 404 continues.
2. **Every other potentially blocking read**: the persisted configuration for the intent's version (`_policy_for`), the broker clock (bracketed by host monotonic reads, `observe_broker_clock`), the quote.
3. **Kill switch re-read** after all of the above.
4. **Time sampled after everything**: `timing.now()` (host, monotonic-anchored) and `timing.broker_now()` (broker-bounded interval); `require_broker_certainty_within`; then `final_send_refusal` re-validates every rule — authorization validity, intent expiry, mandatory liquidation deadline, market session, quote freshness, notional cap, kill switch, configuration fingerprint — on that fresh evidence.
5. **Nothing else.** The transport POSTs on return; no network operation sits between the decision and `connection.request`.

**The guarantee, stated exactly.** This is a refusal at the **bounded application send boundary**:
every read that can block completes before the decision, the decision uses time sampled after
those reads, and the request leaves immediately after the decision or not at all. It is NOT a
claim of control over the broker's receipt time, over the TCP send after `connection.request`
is invoked, or over events after the request leaves. What can still happen after the boundary
is exactly what `SUBMISSION_UNKNOWN` and reconciliation exist for.

`PaperExecutionRefusedError`/`PaperTimeUncertainError` raised inside the boundary are wrapped as
`BrokerNotSentError`; the attempt becomes terminal REJECTED/`NOT_SENT` with `DISPATCH_NOT_SENT`,
because nothing was sent. `BrokerIdentityExistsError` and `BrokerIdentityUnresolvedError` are
NOT refusals (§2.3, §2.4).

### 2.2 One canonical order-terms contract — `decision_candidate/paper_execution.py::order_terms_mismatches`

Used by all four places that compare a broker order with the authorized one: the adapter's
acknowledgement of our own POST (`_validated_order_view`), the post-send duplicate observation,
the pre-send observation, and restart reconciliation. It compares `client_order_id`, `symbol`,
`side`, `order_type`, `quantity` (as `Decimal`), `limit_price` (present and equal for LIMIT,
absent for MARKET), `time_in_force`, `extended_hours` (a real boolean), and — when the attempt
has already bound one — `broker_order_id`. A missing or malformed field is a mismatch; nothing
is ever substituted with the expected value. Account/endpoint context is verified separately by
reconciliation (`account.account_reference != authorization.account_reference` → mismatch
`account`). A mismatching acknowledgement to our own POST is `BrokerAmbiguousDispatchError` →
`SUBMISSION_UNKNOWN`, never an acceptance and never a refusal.

`_OrderView` now carries `time_in_force` and `extended_hours` (None when absent/malformed) and
the `BrokerOrderView` protocol exposes `limit_price`, `time_in_force`, `extended_hours`.

### 2.3 Observing is not attributing — `attempt_may_have_transmitted`

Three facts are persisted separately: **transmitted?** (attempt state + failure code + events),
**exists?** (acknowledgement rows + `IDENTITY_*` events), **attributable?** (lineage).

Attribution — adopting a broker order as the result of THIS authorization — requires lineage:
a durable attempt that may have transmitted a request able to create it. That is
`SUBMISSION_IN_PROGRESS` (a dispatcher that claimed and never recorded an answer) or
`SUBMISSION_UNKNOWN` whose recorded cause is an ambiguous/unusable answer to OUR POST
(`AMBIGUOUS`, `UNUSABLE_ANSWER`, `UNCERTAIN_HTTP_*`). Any event or failure code recording that
this attempt did not send (`IDENTITY_OBSERVED_BEFORE_SEND`, `IDENTITY_LOOKUP_INCONCLUSIVE`,
`CLIENT_ORDER_ID_COLLISION`, `DISPATCH_NOT_SENT`; codes `IDENTITY_EXISTS_UNSENT`,
`IDENTITY_UNRESOLVED_UNSENT`, `IDENTITY_EXISTS_SENT`, `NOT_SENT`) denies lineage, and the event
outranks the code so a rewritten code cannot erase what was appended.

Without lineage — a fresh attempt whose pre-send lookup finds an order, a duplicate-identity
answer to our POST (proof the order predates it), or a reconstructed database — the order is
**observed**: looked up, recorded with its broker id and status
(`IDENTITY_OBSERVED_NOT_ATTRIBUTED`, or `IDENTITY_COLLISION_MISMATCH` when its terms differ,
or `IDENTITY_LOOKUP_UNRESOLVED` when it cannot be read back), the attempt rests in
`SUBMISSION_UNKNOWN` with `IDENTITY_EXISTS_UNSENT`/`IDENTITY_EXISTS_SENT`, `broker_order_id`
stays unbound, and the result note says so for the operator. It is never adopted, never
resent, never replaced, never cancelled, never liquidated; a later authorization for the same
intent is refused because the intent already has an attempt. The previous adoption paths
(`IDENTITY_RECONCILED_EXACT_MATCH` from a pre-send find or from reconciliation without lineage)
are gone and their tests were removed as superseded, not weakened
(`tests/unit/test_m085_identity_collision.py` docstring records which).

### 2.4 An inconclusive pre-send lookup is recoverable uncertainty

Lookup exception / non-404 / unreadable body → `SUBMISSION_UNKNOWN`, `IDENTITY_UNRESOLVED_UNSENT`,
event `IDENTITY_LOOKUP_INCONCLUSIVE`, zero POSTs. Reconciliation (same process or after a
restart) looks the identity up again: 404 twice over ≥ 60 s → REJECTED/`NOT_SENT` (the same
bounded not-found policy as before); found → observed, not attributed (no lineage), zero
resends. Later refusals cannot discard the recorded uncertainty because the events are
append-only and lineage consults them.

### 2.5 Definitive refusal is a documented (status, code) pair

`RECOGNIZED_DEFINITIVE_REFUSAL_CODES` (from Alpaca's published error guide):
400 → {40010000, 40010001}; 401 → {40110000}; 403 → {40310000, 40310100};
422 → {40010001, 42210000}. The 422/40010001 pair whose message names uniqueness/duplication is
`CLIENT_ORDER_ID_EXISTS`. Anything else — an undocumented code, a code under the wrong status,
a body without an integer `code`, any other status — is `UNCERTAIN` → `SUBMISSION_UNKNOWN`.

## 3. Invariants → regression tests → mutation families

| Invariant | Collected regression | Mutation family (rule removed → named test must fail) |
|---|---|---|
| Lookup precedes the decision; kill switch is read after every slow read; POST is last | `test_m085_send_boundary.py::test_the_boundary_reads_everything_before_the_kill_switch_and_samples_time_last` | `send_boundary_no_read_after_the_decision` (a lookup inserted after step 5) |
| Kill switch engaged during ANY slow read → 0 POSTs | `…::test_the_kill_switch_engaged_during_a_slow_read_stops_the_post[lookup|configuration|clock|quote]`; transport: `test_m085_send_boundary_transport.py` | `send_boundary_kill_switch_read_after_the_slow_reads` (pre-claim snapshot reused) |
| Authorization expiry / intent expiry / liquidation deadline / market close / stale quote during a slow read → 0 POSTs | `…::test_the_authorization_expiring_during_a_slow_read_stops_the_post[*]`, `…intent_expiring…`, `…liquidation_deadline…`, `…market_closing…`, `…quote_going_stale…[*]`, `…stale_when_read…` | `send_boundary_time_sampled_after_the_reads` (decision time = command time) |
| Positive control: while permitted exactly one POST leaves | `…::test_while_permitted_exactly_one_post_leaves`; transport positive control | (control — proves the refusals are not vacuous) |
| A refused send is terminal NOT_SENT and a repeat reads nothing and sends nothing | `…::test_a_refused_send_is_terminal_not_sent_and_a_repeat_sends_nothing` | existing `no_resend_after_a_collision`, `single_dispatch_per_intent` |
| Acknowledgement of our POST compared on every term; missing fields refused | `test_m085_acknowledgement_terms_http.py` (real adapter), `test_m085_hostile_http.py::TestAnAnswerAboutTheWrongOrderIsRefused` | `acknowledgement_terms_compared_canonically`, `response_identity_validation`, `response_quantity_validation` |
| Canonical comparison covers limit_price, time_in_force, extended_hours, bound broker_order_id | `test_m085_identity_lineage.py::TestTheCanonicalTermsComparison` | `terms_compare_limit_price`, `terms_compare_time_in_force`, `terms_compare_extended_hours`, `terms_compare_bound_broker_order_id`, existing `identity_match_checks_the_{symbol,quantity,side}` |
| Pre-send find → observed, not adopted, 0 POSTs, the derived id is what was asked about | `…::TestAnIdentityObservedBeforeTheSendIsNotAttributed::test_an_exact_match_found_before_sending_is_observed_not_adopted` | `identity_collision_looks_the_identity_up`, `pre_send_lookup_uses_the_derived_identity` |
| Attribution requires lineage; unsent evidence outranks state/code | `…::TestLineage` (5 parametrized event-outranks-state cases), `…::test_nothing_is_ever_resent_and_no_later_authorization_reopens_it` | `reconcile_requires_lineage_before_adoption`, `lineage_unsent_never_attributed` |
| Reconciliation verifies the account and every term before adopting even WITH lineage | `…::TestLegitimateRecoveryAfterALostAcknowledgement` | `reconcile_verifies_the_account`, `reconcile_refuses_a_mismatching_order` |
| Inconclusive lookup → UNKNOWN, 0 POSTs; restart → surfaced, not attributed, 0 resends | `…::TestAnInconclusiveLookupBeforeTheSendStaysRecoverable`; PostgreSQL: `test_m085_identity_collision_postgres.py::test_an_inconclusive_lookup_then_a_restart_surfaces_the_order_without_attribution` | `inconclusive_lookup_is_not_a_rejection`, `unresolved_identity_recovered_after_restart` |
| Rebuilt database meets the broker's order → observed, not attributed, nothing sent | PostgreSQL: `…::test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending`, `…surfaces_a_different_order…as_a_collision`, `…duplicate_answer_after_the_send_is_observed_and_not_attributed` | `database_rebuilt_meets_existing_identity` |
| Refusal = documented (status, code); unknown/inconsistent → UNCERTAIN | `…::TestRefusalsAreClassifiedByDocumentedSemantics`, `test_m085_hostile_http.py::test_a_code_that_does_not_belong_to_its_status_is_uncertain[401|403]`, `test_m085_corrective_pass_domain.py` | `unknown_error_code_is_uncertain`, `duplicate_identity_422_is_not_a_refusal`, `unknown_422_shape_fails_closed`, `definitive_refusal_statuses` |

The campaign now holds **148 families** (134 on `2726f6f` + 14 new). Two of the twenty families
run before the commit survived on the first pass — `pre_send_lookup_uses_the_derived_identity`
(the fake broker answered its scripted view for any id) and `lineage_unsent_never_attributed`
(the pre-send observation's state/code also maps to "not transmitted" through the fallback
branch, so the event rule was untested). Both were test gaps, not product defects; the
detecting tests were strengthened (the lookup id is asserted; five event-outranks-state cases
were added) and both families are detected. The pre-commit run's tree digest was identical
before and after. The exact-SHA rerun on the committed content is in
[verification.md](verification.md).

### 3.1 Found by the exact-SHA verification of the first candidate `80d1faa`

Running the 108 families whose target file changed (plus the 14 new ones) against the
committed `80d1faa` detected 106 and left two survivors, both in `classify_broker_refusal`:
`definitive_refusal_statuses` (the early `status not in DEFINITIVE_BROKER_REFUSAL_STATUSES`
exit) and `definitive_refusal_requires_the_brokers_document` (a non-object body given a
fabricated `code: 0`). Neither was a behavioural defect: the new per-status code table
(`RECOGNIZED_DEFINITIVE_REFUSAL_CODES.get(status, frozenset())`) already refuses any status
absent from the table and any code it does not list, so both mutations had become
*equivalent* — exactly the "second copy masks the removal of the first" condition the
campaign exists to catch. Correction in the second candidate: `DEFINITIVE_BROKER_REFUSAL_STATUSES`
is now derived from the table's keys, the redundant early exit is gone, and the two families
mutate the table itself (a 500 entry; a fabricated *documented* code). The `80d1faa` run is
kept in [verification.md](verification.md) with its two survivors; the full sequence was rerun
on the second candidate.

## 4. Boundaries respected

- M083 / M084 frozen paths untouched (frozen-path guard in the verification).
- No migration, no schema change, no authentication/privilege/security-policy change.
- No gate weakened, no coverage floor lowered, no frozen test modified. Superseded tests of the
  adoption behaviour were removed and are named in the file that held them.
- CI: `.github/workflows/m085-temporal.yml` gains the four new suites and the 16 affected/new
  families; runs only when the Owner publishes.
