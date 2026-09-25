# M085 corrective pass — send-time policy, uncertain outcomes, terminal immutability

> **Superseded in part by the identity-safety correction:** this pass was committed as
> `b24c471592619b71dac296d538bb03715d4962da`; its verification, the identity-collision defect
> (F1) found while reviewing it, and the correction that followed are in
> [identity-collision-correction.md](identity-collision-correction.md). The 422 rule stated
> in item 2 below is now semantic, not "status and JSON object".

Status: CORRECTED CANDIDATE — OWNER REVIEW REQUIRED. Not merged, not frozen, not
deployed. M086 NOT_STARTED. No Paper or Live order was submitted, no order endpoint was
called, and no human approval, configuration, context, proposal, intent, authorization
or attempt was created in the acceptance database.

Starting candidate: `754cedac51b68cd6e50a62b72bb72ea39845304d` on
`feature/m085-alpaca-paper-human-approved-execution` (PR #15, open, unmerged), base
`master` `a224076754fb38909ee04c2464e50e51df12d7ad`.

This document supersedes, for the rules it names, the earlier sections of
`temporal-correction.md`, `validation-results.md`, `final-delivery-report.md`,
`mutation-matrix.md` (run 3), `temporal-mutation-matrix.md` and
`provenance-mutation-matrix.md`. Those documents are kept as historical evidence of the
runs they record, blocked runs included; their counts do not describe this head.

## What the review found, and what changed

| # | Finding | Repair | Where it is refused |
|---|---|---|---|
| 1 | The preview and submit commands accepted the notional cap, quote age and watchlist as **command-line arguments**, so a submit could run under `500 99999 AAPL,TSLA` against an authorization granted under `5 60 AAPL`. | The arguments are gone. The send-time policy (`ExecutionPolicy`: cap, quote age, spread, watchlist, prohibited instruments, entry window, timezone) is derived only from the stored configuration version the intent names, fingerprinted, stored on the preview, and copied into the authorization. | CLI arity; preview; database preview guard; authorization binding; submit before any broker call; pre-claim guard; final guard |
| 2 | Any HTTP status other than 200/201 was recorded as a terminal `REJECTED`, so a 5xx, a proxy page or a malformed acknowledgement that followed an acceptance left a live paper order untracked. | Only 400, 401, 403 or 422 carrying the broker's own JSON error object is a refusal. Everything else after the request may have left — timeout, reset, 5xx, 408/409/429, a non-JSON body, a redirect answering the POST, a 200 that is not the order, any fault in this process — is `SUBMISSION_UNKNOWN`, recorded with what was said, and resolved only by reconciliation on the same `client_order_id`. | adapter classification; handler dispatch mapping |
| 3 | The mandatory liquidation deadline was translated through the proposal basis, which **extended** it when the evaluating host ran slow (15:45 became 16:15). | See *Temporal design*. Skew can shorten the deadline, never extend it; a deadline written for another calendar date refuses. | preview; issuance chronology; pre-claim guard; final guard |
| 4 | Nothing checked that the database was at the schema the guards were written for. | `require_exact_m085_schema_head` refuses unless `alembic_version` is exactly `9c4b2e7d5a18`, before any runtime is handed out. | composition |
| 5 | A terminal attempt could be rewritten by a same-state UPDATE (broker order id, fills, status). | Repository refuses legibly under `FOR UPDATE`; the database update guard refuses every UPDATE of a terminal row; broker order id and submission/acknowledgement instants are written once. | repository; database |
| 6 | An authorization was bound only to a fingerprint, id and account. | It now carries symbol, side, quantity, order type, limit price, cap, quote bid/ask/timestamp, configuration id/version, policy fingerprint and the preview binding fingerprint, each compared field by field in the domain and in an AFTER INSERT database guard, and frozen by the update guard. At submit it is compared against the stored preview, whose policy and binding fingerprints are re-verified when that row is read. | domain; database; submit |
| 7 | The final send guard judged the market session and the quote from values cached before the claim. | `final_send_refusal` runs once before the claim and again inside `before_send`, after connect, on values read again there: kill switch and configuration from the database, clock and quote from the broker. | final guard |
| 8 | `tools/m085_paper_acceptance.py --dry-run` wrote a configuration, a scripted approval, an intent and a preview. | `--dry-run` is refused before any import, connection or file. The legacy script was not run. | tool entry |
| 9 | Evidence counted families and tests of the replaced code. | Campaign retargeted and extended, run sequentially with per-file and tree-wide restoration digests; collection reconciled; historical documents labelled. | — |
| 10 | Governance. | See *Governance findings*. | — |

## Temporal design

Every rule is judged on the timeline of the act that produced its inputs, and every
uncertain interval is resolved against the order.

- **Two timelines, both required.** Host-recorded deadlines (`expires_at`,
  `mandatory_liquidation_at`, the authorization's own expiry) are checked against the
  host's monotonic-safe instant. The same deadlines are also checked on the broker's
  clock as a `BoundedInstant` interval: an interval that *might* have reached a deadline
  has reached it.
- **Provenance.** `expires_at` is translated only through the proposal-time basis; the
  approval expiry only through the decision-time basis; the authorization expiry only
  through the authorization-time basis. Unchanged from the previous pass.
- **Liquidation (T1).** M084 writes the liquidation deadline as a time of day on the
  evaluating host's calendar date, not as a duration. `effective_liquidation_deadline`
  is `min(calendar instant, proposal-basis mapping)`: a host that ran fast still moves
  it earlier; a host that ran slow can no longer move it later. The replaced mapping
  let a dispatch at 15:50 New York through a 15:45 deadline after a 30-minute slow host.
  `liquidation_session_refusal` refuses when either end of the broker interval falls on
  a different operator-timezone date from the one the deadline was written for, because
  such a deadline cannot be evaluated conservatively.
- **Entry window.** Both ends of the broker interval, converted to the operator
  timezone, must lie inside `[earliest_entry_time, latest_entry_time]` (inclusive) on one
  date. It is never judged through a host offset.
- **Quote.** The oldest age the broker interval permits must not exceed the configured
  limit (exactly the limit passes, one microsecond more refuses). Future-dating refuses
  only beyond the latest possible broker instant. Positive, uncrossed, spread against the
  mid price within the configured limit.
- **Market session.** Closed if the broker says closed, if no close is known, or if the
  interval might be at or after the close.
- **Certainty.** Before a preview, before the claim and inside `before_send`, the broker
  interval must be narrower than the configured quote age, or the command refuses
  (`PaperTimeUncertainError`, and inside `before_send` a definite not-sent).
- **Waits.** The claim re-reads host and broker time after acquiring the row lock;
  `before_send` fetches the broker clock and the quote after connect. A database wait, a
  lock wait, connection preparation or a slow quote therefore ages the evidence.
- **Authorization.** It may not outlive the approved intent (exactly the intent's expiry
  passes, one tick more refuses) and may not be granted on a preview older than the
  configured quote age.

Deterministic tests: a 30-minute slow host at evaluation with dispatch at 15:50; the
deadline to the tick; a fast host; issuance after the calendar deadline; a deadline for
another date; wall-clock and broker-clock rollback (existing families); a real
PostgreSQL row-lock wait (`claim_time_after_lock`); the entry window closing during
connection preparation; elapsed work in every phase against every deadline; the market
closing after the claim and at the tick.

## State-machine design

```
DISPATCH_CLAIMED      -> SUBMISSION_IN_PROGRESS | REJECTED | EXPIRED
SUBMISSION_IN_PROGRESS-> PAPER_SUBMITTED | SUBMISSION_UNKNOWN | REJECTED
PAPER_SUBMITTED       -> PAPER_ACCEPTED | PARTIALLY_FILLED | FILLED | CANCEL_REQUESTED
                         | CANCELED | REJECTED | EXPIRED | SUBMISSION_UNKNOWN
SUBMISSION_UNKNOWN    -> PAPER_SUBMITTED | PAPER_ACCEPTED | PARTIALLY_FILLED | FILLED
                         | CANCEL_REQUESTED | CANCELED | REJECTED | EXPIRED
terminal (immutable)  :  FILLED, CANCELED, REJECTED, EXPIRED
```

No edge leads back into `SUBMISSION_IN_PROGRESS`, in the domain table and in the
database trigger. The dispatch outcome mapping:

| What happened | Recorded as |
|---|---|
| `before_send` refused, or connect failed before any byte was written | `REJECTED`, `NOT_SENT` — nothing reached the broker |
| request write failed; no answer; read timeout | `SUBMISSION_UNKNOWN`, `AMBIGUOUS` |
| POST answered by a redirect (refused, never followed) | `SUBMISSION_UNKNOWN`, `AMBIGUOUS` |
| 200/201 whose body is not the order sent | acknowledgement stored; `SUBMISSION_UNKNOWN` |
| 400/401/403/422 with the broker's JSON error object | acknowledgement stored; `REJECTED`, `HTTP_n` |
| any other status or body | acknowledgement stored; `SUBMISSION_UNKNOWN` |
| any other exception once `before_send` passed | `SUBMISSION_UNKNOWN`, `UNUSABLE_ANSWER` |
| 200/201 validated field by field | `PAPER_SUBMITTED`, then the mapped broker status |

Reconciliation looks up the original `client_order_id`. Found: the attempt moves to
`PAPER_SUBMITTED` and then to the mapped status. Absent: for `SUBMISSION_UNKNOWN` —
reached only after the dispatcher's single send attempt has returned — the bounded
not-found policy (two consecutive observations and 60 seconds) applies, unchanged.

An attempt still `SUBMISSION_IN_PROGRESS` is looked up only once it is older than that
window, and **an absence answer never changes it**. Age is not proof that the dispatcher
has stopped: connect, the database reads and the clock and quote fetches inside
`before_send` are not bounded by 60 seconds, and the reconciling host's clock may differ
from the dispatcher's. SUPERSEDED within this pass: the first version resolved such an
attempt to `REJECTED` after two not-found answers, and a dispatcher still inside
`before_send` would then have sent an order recorded as rejected (found by the
independent review; regression test
`test_absence_while_the_dispatcher_is_still_sending_never_rejects`). Only a found order
moves it. An interrupted dispatch whose order never reached the broker therefore stays
`SUBMISSION_IN_PROGRESS` and needs an operator; that is stated as a limit rather than
guessed at. A terminal attempt is returned without a lookup or a write.

## Proof that command arguments cannot weaken an authorization

1. **No channel.** `PreviewPaperSubmissionCommand` and `SubmitAuthorizedPaperOrderCommand`
   carry identities only; a test enumerates their fields. The console scripts take
   exactly three positionals; the reviewed six-argument vectors, including
   `500 99999 AAPL,TSLA`, exit with usage. The composition seam receives identities only.
2. **One source.** `execution_policy_from_configuration` reads the stored configuration
   version the intent names and nothing else; a missing version refuses.
3. **Stored and checked at insert.** The preview row stores the policy and its
   fingerprint. The AFTER INSERT guard refuses a preview whose limits, watchlist,
   prohibited set, window or timezone differ from that configuration row, or whose order
   differs from the intent row.
4. **Bound.** The authorization copies the binding. The domain and the AFTER INSERT
   guard refuse any difference from the stored authorizable preview; the update guard
   freezes every bound column; reading a row whose policy or binding fingerprint does
   not match its columns fails closed.
5. **Re-derived at send.** Before any broker call, before the claim and inside
   `before_send`, the policy is re-derived from the stored configuration and must have
   the authorized fingerprint and cap; the limits then applied are that policy's. A
   configuration rewritten looser under the same id and version refuses before any
   broker call; one changed after the claim refuses at `before_send` with nothing sent.

## Proof that an uncertain outcome cannot create a duplicate submission

1. The claim consumes the authorization with an UPDATE conditional on
   `consumed_at IS NULL` and inserts the attempt in the same transaction, before any
   network request; the database allows one consumed authorization and one attempt per
   intent and a unique `client_order_id`.
2. The adapter makes one POST per call and has no retry; the handler calls it once.
3. Every possibly-delivered outcome is `SUBMISSION_UNKNOWN`, which is non-terminal but
   has no edge back into submission, in the domain and in the trigger.
4. A second submit for the intent returns the persisted attempt with `dispatched=False`;
   a new human authorization for the same intent cannot create a second attempt.
5. Tests: for each of seven uncertain kinds (timeout after send, 503 with a body, 500
   without a view, 429, 422 from a proxy page, 200 without an order, a fault after send)
   the broker fake receives exactly one submission across a first submit, a second
   submit, a fresh authorization and a third submit, and `SUBMISSION_IN_PROGRESS` is
   entered once. Through PostgreSQL: a server error is stored as unknown and never
   re-sent, and reconciliation resolves it through the database edges. The existing
   concurrency races are unchanged.

## Database

Migration `9c4b2e7d5a18` (down revision `e61b3f9a4c27`):

- preview: 13 NOT NULL policy and binding columns, fingerprint shape CHECKs, positive
  cap and age, non-negative spread, ordered window, and
  `ck_paper_preview_authorizable_within_cap`;
- `paper_submission_preview_guard_policy` (AFTER INSERT): exact intent order, existing
  configuration version, exact policy;
- `paper_execution_authorization_guard_insert` (AFTER INSERT): inserted unconsumed,
  existing preview without refusals, every bound field equal, not outliving the intent,
  not granted after the preview's freshness limit;
- authorization update guard extended to freeze the binding columns;
- attempt update guard: identity fixed, terminal rows immutable (same-state included),
  broker order id and instants written once, then the closed transition table.

The new insert guards run AFTER INSERT so the earlier milestones' CHECK constraints
still report themselves. The upgrade refuses if previews or authorizations already
exist, because their binding cannot be derived after the fact. Downgrade restores the
previous guard functions exactly. The limits of any trigger guard — DISABLE TRIGGER,
DROP, TRUNCATE, a superuser — are unchanged and stated in the authority contract.

**The acceptance database** `m085_acceptance_2e5c38c` remains at `e61b3f9a4c27`, holding
only its watermark and configuration `CFG-085-ACCEPT-2026` v1. It was read only, before
and after this pass, with identical results. Because of item 4, every M085 command now
refuses against it until the Owner authorizes upgrading it to `9c4b2e7d5a18`. It holds
no preview or authorization, so that upgrade would not be refused.

## Verification

RESULTS_PENDING

## Mutation campaign

Families run strictly one at a time. Each: green baseline, mutation of the real governing
rule, the named test required to fail for the named reason, restoration, per-file SHA-256
verified, test green again. The whole source tree (every file under `src`, `tests`,
`tools`, `migrations`, `scripts`, byte-compiled caches excluded) is digested before the
first family and after the last. PostgreSQL families ran against the disposable
`m085_pgon_c7a41f0` only.

The campaign now has **121 families**: the 82 of the previous head (13 retargeted because
their rule moved, was rewritten or is now installed by `9c4b2e7d5a18`) and 39 new ones
covering D1, P2, P3, T1, D2, D3, items 4, 7 and 8 and the review's blocker. Runs 1 and 2
had 120; the 121st was added with the blocker fix.

**Run 1 — BLOCKED, 111 of 120** (kept as `corrective-pass-mutation-matrix-run1.md`).
Tree-wide restoration verified (`187492de…9132` before and after). The nine blockers,
each diagnosed from the full test output, and what was corrected:

| Family | Run 1 | Diagnosis | Correction |
|---|---|---|---|
| `database_transition_trigger` | SURVIVED | mutated `b1e9d47c30a5`, whose attempt guard `9c4b2e7d5a18` replaces; nothing installed changed | campaign target moved to `9c4b2e7d5a18` |
| `reconcile_a_stale_in_progress_attempt` | SURVIVED | **real test weakness**: the fake store does not enforce the transition table, so skipping `PAPER_SUBMITTED` was invisible (the database would refuse it) | unit test now asserts every recorded edge is allowed by the closed table; new PostgreSQL test reconciles an interrupted dispatch through the real trigger |
| `database_single_use_trigger` | wrong reason | **fixture regression of this pass**: the second consumption ran at `now()`, after the 60 s validity, so the expiry rule refused it too | the test consumes inside the validity, so only single use can refuse |
| `liquidation_deadline_at_dispatch` | wrong reason | the test's 15:30 entry window, then its 300 s authorization, refused first | test widened to a 15:55 window and a six-hour authorization; the mutation now dispatches at 15:50 (`DID NOT RAISE`) |
| `broker_basis_authorization_expiry` | wrong reason | the new future-dated check also refuses this scenario (defence in depth) | expected reason names that refusal |
| `redirect_refusal` | wrong reason | a POST redirect is now ambiguous; without the rule the 301 is still ambiguous, not as a redirect | expected reason: the message match fails |
| `reconcile_leaves_a_live_dispatch_alone` | wrong reason | the state assertion fails before the lookups assertion | expected reason names the state |
| `schema_head_exact`, `schema_head_checked_by_the_composition` | wrong reason | the test's `pytest.fail` inside the body reports it | expected reason names that message |

No limit, rule or production behaviour was changed to clear a blocker. Two tests were
strengthened and one fixture corrected; five expected-reason strings were corrected
after reading the actual failure. All nine were re-run through the campaign's own
`run_family` before run 2 and detected, with tree-wide restoration verified.

**Run 2 — 120 of 120, SUPERSEDED** (kept as `corrective-pass-mutation-matrix-run2.md`).
Tree-wide restoration verified (`783ebb56…39db` before and after). It ran on the source
before the independent review's blocker fix below, so it does not certify the final head.

**Independent review.** A separate read-only adversarial review of the whole diff found
one BLOCKER, introduced by this pass: reconciliation applied the bounded not-found policy
to an attempt still `SUBMISSION_IN_PROGRESS` once it was 60 s old, so a dispatcher still
inside `before_send` (connect, database reads, clock and quote fetches are not bounded by
60 s, and the reconciling host's clock is not the dispatcher's) could have its attempt
recorded `REJECTED` and then send the order. Corrected: an absence answer never changes
`SUBMISSION_IN_PROGRESS`; only a found order moves it. Regression tests:
`test_absence_while_the_dispatcher_is_still_sending_never_rejects`,
`test_absence_never_resolves_an_interrupted_dispatch`, and the PostgreSQL
`test_absence_never_resolves_an_interrupted_dispatch_in_the_database`; new family
`reconcile_absence_never_rejects_a_live_dispatch`. The review's MINOR finding that the
unit fake called `before_send` without the transport's wrapping was also corrected: the
fake now reports any `before_send` failure as a definite not-sent, as production does.

**Run 3 — RUN3_PENDING**

## Collection reconciliation

Collected with PostgreSQL off. Baseline: `git archive` of `754ceda`'s `src`, `tests`,
`migrations`, `tools`, `pyproject.toml` and `alembic.ini`, collected with that `src`
first on the path (a detached worktree could not be created on Windows because of
over-long root file names).

| | Nodes |
|---|---|
| baseline `754ceda` | 4829 |
| retained | 4809 |
| removed | 20 |
| added | 249 |
| head | 5058 |

Removed, each accounted for: 10 cases of
`test_an_error_status_yields_no_acknowledgement_and_keeps_its_code`, replaced by the
split into definitive refusals (4), uncertain statuses (9) and definitive statuses with a
non-JSON body (4); 5 cases of `test_nothing_but_consumption_may_change`, whose ids embed
the SQL and changed with `consumed_at = authorized_at` (the same 5 are added back); and
5 tests of limit-argument parsing (`test_a_negative_quote_age_is_refused`,
`test_a_non_decimal_notional_is_refused_by_name`, `test_an_empty_watchlist_is_refused`,
`test_the_notional_reaches_the_seam_as_a_decimal`,
`test_the_watchlist_is_upper_cased_and_split`) for arguments that no longer exist,
replaced by tests that no limit can be passed. Added: 103 corrective domain, 62
corrective PostgreSQL, 36 corrective handler, 21 hostile HTTP, 9 composition, 6
entrypoints, 5 lifecycle PostgreSQL, 3 temporal PostgreSQL, 2 dry run, 2 domain.

## Residual limits, stated (independent review, MINOR and NOTE findings)

None of these exposes a send; each is recorded rather than dissolved.

- **Authorization freshness is measured from preview creation on two host clocks.** The
  domain and trigger compare the authorizing host's `basis_host_at` with the previewing
  host's `created_at`, so a quote already near its limit at preview can be authorized up
  to twice the limit after capture, and host skew between the two acts loosens it. The
  dispatch re-checks a freshly fetched quote on the broker timeline, so no stale quote
  reaches a send. A broker-timeline rule (`basis_broker_latest_at - quote_captured_at`)
  would be stricter.
- **"Not outliving the intent" compares expiries written by two hosts.** Dispatch still
  enforces intent expiry on the broker timeline through the proposal basis.
- **The final send guard re-reads kill switch, configuration, clock and quote only.**
  Asset status, buying power, account status and existing position are checked before the
  claim, not again inside `before_send`.
- **The database guards compare stored fingerprints; they do not recompute them.**
  Previews are re-verified on read; a writer with direct SQL access can store a
  consistent forgery. Defence in depth, like every trigger guard.
- **Downgrade removes the binding columns even if authorizations exist.**
- **An interrupted dispatch whose order never reached the broker stays
  `SUBMISSION_IN_PROGRESS`** and needs an operator; absence is never taken as proof.
- **If reconciliation records a found order as terminal while its own dispatcher is still
  recording the acknowledgement,** that dispatcher's write is refused by the immutable
  terminal row and the command exits with an error; the stored state is the broker's.
- **`RECONCILE_UNUSABLE_ANSWER` events reuse one event id** (pre-existing): a second
  non-404, non-200 reconciliation answer for the same attempt fails to append its event.

## Governance findings

> **G1 resolved (2026-09-25).** The Owner ratified `1127134` for exactly its six files and
> directed that the frozen-path guard be extended to M084; both are recorded in
> `PROJECT_CHECKPOINT.md` section 119 and proved by
> `tests/architecture/test_frozen_milestones.py`. See
> [identity-collision-correction.md](identity-collision-correction.md), section 6. The
> paragraph below is kept as the record of the finding.

**G1 — post-freeze M084 audit-tooling commit, Owner confirmation required.** Commit
`1127134623b25178b4d98236d5ab75f8f2134760` ("fix(m084): pin the derived audit to the
approved tree, and let it run anywhere", 2026-09-10) is on this branch only, not on
`master`. It modifies files of frozen MILESTONE-084: `tools/render_m084_file_audit.py`,
`tools/render_m084_exhaustion_table.py`, `tests/integration/test_m084_file_audit.py`,
`external-review/MILESTONE-084/file-audit-matrix.json` and `.md`, and adds
`tests/unit/test_m084_audit_portability.py`. Its message describes the change as two
owner-authorized administrative corrections and states that no M084 production module,
migration, authority file or recorded result changed. The repository holds no record of
that authorization other than the commit message itself, and `tools/check_frozen_paths.py`
governs M083 paths only, so no mechanical check covers M084 files. This pass did not
modify, revert or re-run that change; it records it for the Owner to confirm or reject
separately from M085.

**G2 — historical operator evidence describes the replaced CLI.**
`operator-walkthrough.md`, `hostile-http-results.md` and `paper-acceptance-results.md`
record runs of the code before this pass (six-argument commands, 102 HTTP attacks, the
2026-09-10 blocked acceptance). They were not re-run: the walkthrough and the acceptance
tool create records, and this pass is prohibited from creating any. They remain accurate
as history and are not evidence for this head.

**G3 — the authority contract is unchanged.** `current-authority.json` is a closed
schema whose claims remain true at this head; the rules added here strengthen claims it
already makes and are evidenced in this document and the mutation matrix rather than by
widening the contract without Owner review.

## External Paper acceptance: still PENDING

Not attempted and not closed by this pass. The next acceptance requires the Owner to
authorize upgrading the acceptance database, and a human to preview, authorize and
submit through the three-argument commands.
