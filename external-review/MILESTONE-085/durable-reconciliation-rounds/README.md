# M085 durable reconciliation rounds and clock-safe waiting (Q-2 / Q-4)

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Local commits only; not pushed,
not merged, not frozen, not OWNER_ACCEPTED, not READY_FOR_PAPER. Paper acceptance NOT_STARTED. M086
NOT_STARTED. No Alpaca call of any kind; no real Proposal/Approval/Intent; no acceptance-database
mutation; every test ran against controlled fakes and the disposable PostgreSQL database
`m085_pgon_b24c471`. M083/M084 frozen paths untouched; no authentication, privilege or
security-policy change; the unrelated Claude worktree untouched.

Reviewed baseline: published head `832b20b340f758726876fcd3181cd05d16e41de9` (REV-R1/REV-R2 code
`e010075`). Code candidate: `093baf76773f3b2f6a24127e832a786371fa76a7`; test-only follow-up
`c4cc3d05e36bee0c106f3cadf79a486d386558ac` (§6, F-5). The verification record for both exact SHAs
is [verification.md](verification.md); raw logs are in `runs-093baf7/` and `runs-c4cc3d0/`.

## 1. What was wrong at `832b20b` (published as Q-2 / Q-4, PR #15 comment)

The bounded not-found policy (2 consecutive not-found observations, ≥ 60 s) was evaluated over
records that were **not** a durable, ordered account of the reconciliation rounds that produced them:

- **Q-2 — a failed round could leave no trace.** A lookup that raised was recorded only as a
  `RECONCILE_LOOKUP_FAILED` event written *after* the failure. If that event write also failed
  (broker failure and database failure in one round), nothing durable said the round had happened.
  The next 404 completed a "consecutive" pair with the 404 before the failed round. The published
  claim that at most one observation could be lost this way was **withdrawn**: the failure could
  recur on every round, and the count was over acknowledgements, not rounds.
- **Q-4 — cross-host time ordered and measured safety decisions.** The consecutive run was computed
  from acknowledgements in sequence order but the failure events were placed by their timestamp
  (`command.at`, the reconciler's wall clock). A lagging reconciler's failure sorted *before* the run
  it should have broken and was ignored. The waiting interval was `command.at − dispatched_at`: the
  reconciling host's wall clock against the dispatching host's; a reconciler whose clock led by two
  minutes satisfied the 60 s threshold ten seconds after the dispatch.

Both were reproduced through the production handlers and on PostgreSQL before this round
(`reconciliation-evidence-safety/verification.md` §5 and the PR comment). The fixes here close them
at the root rather than narrowing them.

## 2. The correction

### 2.1 A durable round journal — `paper_reconciliation_round` (migration `a7d3c9e14f26`)

Each reconciliation round is a row, **inserted and committed before any network work**:

| Column | Meaning |
|---|---|
| `round_id` | `RND-{attempt_id}-{sequence}` |
| `attempt_id`, `intent_governance_id`, `authorization_id`, `client_order_id`, `account_reference` | the round's context, bound to the attempt's own identity and authorized account (insert trigger refuses a mismatch or a missing attempt) |
| `sequence` | per-attempt, allocated atomically; `UNIQUE (attempt_id, sequence)` |
| `started_at` | the reconciler's wall clock at begin — operator information, never used for ordering or measuring |
| `outcome` | `NULL` while the round is in flight; then exactly one of `NOT_FOUND`, `FOUND`, `UNUSABLE`, `FAILED` |
| `completed_at`, `acknowledgement_sequence`, `detail` | completion facts |
| `broker_earliest_at`, `broker_latest_at` | the **broker clock interval** sampled inside this round: `[timestamp, timestamp + round trip]`, bounded by this process's monotonic clock only |

Guards in the database: a round must begin incomplete; identity columns are immutable; completion
happens once (`outcome IS NOT NULL` refuses any further update) and only to a completed outcome;
`DELETE` is refused by the existing `m085_append_only()` function. CHECK constraints pair
`outcome`/`completed_at` and the two interval ends, and order the interval. The migration is
additive and reversible (`downgrade` drops the table, triggers and functions; tested down → up → up).
`M085_SCHEMA_HEAD` and the authority contract's revision list advance to `a7d3c9e14f26`.

### 2.2 The handler (`ReconcilePaperOrderHandler.handle`)

1. Resolve the attempt and its authorization (no authorization → `RECONCILE_ROUND_NOT_BEGUN`, no
   lookup).
2. `rounds.begin(...)` — its own transaction, committed. If this raises, **no lookup runs**.
3. Sample the broker clock (`fetch_clock`, monotonic before/after → `BoundedInstant`), then
   `fetch_order_by_client_order_id`. **No database transaction is open across either call.**
4. If step 3 raised: `rounds.complete(FAILED)` against this round's id, then the
   `RECONCILE_LOOKUP_FAILED` event, then re-raise. If even the completion write fails, the round
   stays **incomplete and visible**. No HTTP status is fabricated for it.
5. Otherwise append the acknowledgement, then complete the round `FOUND` / `NOT_FOUND` / `UNUSABLE`
   with the acknowledgement sequence and the broker interval. A completed round is immutable.
6. On a 404, evaluate absence (§2.3) on a snapshot; if resolvable, ask the repository to finalise
   (§2.4). Otherwise record why: `RECONCILE_ROUND_INCOMPLETE`, `RECONCILE_TIME_EVIDENCE_INSUFFICIENT`,
   `RECONCILE_FOUND_ROUND_WITHOUT_OBSERVATION` or `RECONCILE_NOT_FOUND_INSUFFICIENT`. Bound orders
   (`RECONCILE_NOT_FOUND_KNOWN_ORDER`) and positively observed identities
   (`RECONCILE_NOT_FOUND_AFTER_OBSERVATION`) are surfaced before any counting, as before.

### 2.3 The pure policy (`decision_candidate/paper_execution.py`)

- `rounds_in_order` — by `sequence`. **Never by a timestamp.**
- `consecutive_not_found_rounds` — the trailing run of *completed* `NOT_FOUND` rounds; a `FOUND`,
  `UNUSABLE`, `FAILED` **or incomplete** round ends it, wherever its completion time falls.
- `waiting_anchor` — the first completed round carrying a broker interval.
- `waiting_lower_bound_seconds` — `current.broker_earliest_at − anchor.broker_latest_at`, where
  `current` is the last completed round with an interval. `None` when there is no anchor, no later
  round with an interval, or the readings contradict a monotone broker clock (negative).
- `absence_evaluation(...)` → `AbsenceEvaluation(rounds_version, incomplete_sequences,
  found_sequences, consecutive_not_found, waiting_lower_bound_seconds, anchor_sequence, resolvable,
  reason)`. Resolvable only when, in order: state is `SUBMISSION_UNKNOWN`; no broker id and no
  positive observation; **no `FOUND` round**; **no incomplete round**; run ≥ 2; a lower bound exists;
  lower bound ≥ 60 s.
- `RECONCILIATION_UNKNOWN_POLICY` states all of this (`consecutiveness_evaluated_over`,
  `incomplete_round_blocks_resolution`, `found_round_blocks_resolution`, `waiting_interval_anchor`,
  `waiting_interval_lower_bound`, `time_assumptions`, `legacy_records`). The numbers 2 and 60 are
  unchanged; the contract is not, and the authority rendering says so.

### 2.4 The repository (`PostgresReconciliationRoundRepository`)

- `begin` — `SELECT … FROM paper_execution_attempt WHERE attempt_id = :id FOR UPDATE`, then
  `MAX(sequence) + 1`, then insert, in one transaction. The UNIQUE constraint is the guarantee; the
  lock turns a racing writer's failure into a wait (tested deterministically, §4).
- `complete` — `UPDATE … WHERE round_id = :id AND outcome IS NULL RETURNING …`; zero rows → the
  round is already complete (or absent) and a `ValueError` says which.
- `resolve_not_found(attempt_id, expected_version, …)` — locks the attempt row, re-reads rounds,
  acknowledgements and events **in that transaction**, re-runs `absence_evaluation`, requires
  `rounds_version == expected_version`, and only then writes `REJECTED / NOT_FOUND_AT_BROKER`
  through the existing guarded transition. Anything else returns `None` and writes nothing; the
  handler records `RECONCILE_RESOLUTION_REVALIDATION_FAILED`. No broker call inside.

## 3. Time model — what is measured, what is assumed, what is refused

- **Anchor.** The dispatch has no persisted broker-bounded instant and none is invented. The anchor
  is the first completed round with a broker interval, i.e. an act *after* the uncertain dispatch.
  Measuring from it can only **understate** how long the outcome has been unknown: conservative.
- **Both endpoints in one domain.** Each round's interval is the broker's own timestamp, widened by
  that process's measured round trip. The bound `N_min − A_max` is the smallest duration the evidence
  supports.
- **Never computed:** `broker_now − host_submitted_at`; any difference of host wall clocks from two
  hosts; any comparison of monotonic readings across processes.
- **Assumed, stated in the policy:** the broker's clock advances monotonically between rounds (a
  reading that contradicts this yields no interval); a broker clock sample says nothing about
  whether the broker finished processing an order; the reconciler's monotonic clock is valid within
  one process.
- **Missing or incompatible evidence → unresolved** (`RECONCILE_TIME_EVIDENCE_INSUFFICIENT`), never
  defaulted.
- **Legacy records.** `SUBMISSION_UNKNOWN` attempts reconciled before the journal existed have
  acknowledgements but no rounds. They are operator evidence, never rounds: no basis is fabricated
  and no round history is invented; resolution needs two new completed rounds with justified broker
  time. None exist in any acceptance database (Paper acceptance NOT_STARTED).

## 4. Concurrency — what the tests establish

- Eight services beginning rounds for one attempt at once obtain sequences 1–8, no errors.
- A **deterministic race**: writer S reads `MAX(sequence)` and pauses until writer F finishes or 3 s
  pass. Under the lock F cannot finish while S holds it (S times out, inserts 1, F then gets 2).
  Removing the lock makes F allocate 1 during the pause and S's insert collide — the mutation
  `database_round_sequence_allocated_under_the_attempt_lock` is detected by exactly this.
- A round begun by B and still in flight blocks A's later 404s (`RECONCILE_ROUND_INCOMPLETE`);
  when B's delayed answer is `FOUND`, it is recorded against B's own round and forbids absence
  resolution for good (`RECONCILE_FOUND_ROUND_WITHOUT_OBSERVATION` when the observation itself is
  not on the attempt).
- Positive evidence arriving from another process between A's judgement and A's finalisation —
  as a full round (version changes) or as an acknowledgement without a round (version unchanged) —
  prevents the rejection; each guard has its own test and its own mutation family.
- A round completed by another process after the snapshot, whose fresh rows would still permit
  resolution, is **not** finalised from the stale snapshot; the next round decides on the complete
  set.
- A real child process dies (`os._exit`) after the round began and inside the lookup: the parent
  finds the STARTED round and nothing else for it; later 404s never resolve while it is incomplete.

## 5. Safety contract maintained

Bound orders (`PAPER_SUBMITTED`, `PAPER_ACCEPTED`, `PARTIALLY_FILLED`, `CANCEL_REQUESTED`) and
positively observed identities are never resolved by absence — under any clock skew, in either
order of 404 and observation. Every scenario in both new suites asserts exactly one POST left the
process (or zero where the dispatch never sent), no cancel, no liquidation. Reconciliation of an
accepted order to `FILLED` is unchanged. Genuine negatives still resolve: two completed `NOT_FOUND`
rounds sixty broker-seconds apart → `REJECTED / NOT_FOUND_AT_BROKER` (positive controls in unit,
fresh-service PostgreSQL and after a failed-clock round).

## 6. Adversarial self-review — findings during this round

- **F-1 (found and fixed).** The first evaluation treated a `FOUND` round only as a run-breaker. A
  `FOUND` round whose observation write was lost, followed by two clean 404 rounds, would have
  resolved. A completed `FOUND` round now forbids resolution outright (`found_round_blocks_resolution`)
  with its own event; mutation family `found_round_forbids_absence_resolution`.
- **F-2 (test design).** A "leading clock" scenario with a constant offset on one host cannot
  manufacture an interval between that host's own rounds; the mutation "interval from the caller's
  wall time" survived it. Both leading-clock tests were restructured to two hosts (round 1 by A,
  round 2 by B whose clock leads by 120 s); the mutation is now detected.
- **F-3 (defence in depth vs. detection).** The handler's pre-check for positively observed
  identities is now redundant for the *decision* (the pure evaluation protects them too) and only
  selects the event. Its family survived until the `FOUND`-round anomaly received a distinct event
  name; the family now detects the lost event.
- **F-4 (test ordering).** A pure-evaluation test asserted the lower bound before resolvability, so
  the "missing evidence read as sufficient" mutation tripped the wrong assertion; reordered.
- **F-5 (found by R4 on the committed candidate).** The handler's `dispatch_may_be_live` branch
  became redundant for the decision (the pure evaluation refuses `SUBMISSION_IN_PROGRESS` too) and
  its mutation survived because the detecting test asserted only state and POSTs. The rule held; the
  detection did not. Follow-up `c4cc3d0` (test and family definition only) asserts the operator
  event `RECONCILE_NOT_FOUND_DISPATCH_MAY_BE_LIVE`; see verification §3.1. Pattern across F-3 and
  F-5: when a rule gains a second enforcement point, each point needs a test that fails when *it*
  alone is removed, or the campaign will rightly report a survivor.
- **Limitations kept.** The `FOR UPDATE` on the attempt row at finalisation is the same statement
  the identity-adoption transition uses; it occurs twice in the repository and is not mutated as a
  single family. `_record_lookup_failure` can still fail after the round is completed `FAILED`; the
  round is the durable trace, the event is operator convenience. Rounds for one attempt are
  serialised by the attempt lock (a throughput cost accepted for a per-attempt journal). S-1/S-2,
  the non-green historical full-PostgreSQL baseline (3 failed / 43 errors, not rerun) and V1's
  pending Owner ratification are unchanged.
