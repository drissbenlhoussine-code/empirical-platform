# M085 temporal correction — implementation evidence

Status: IMPLEMENTED_CANDIDATE — OWNER REVIEW REQUIRED. Not merged or frozen.
Head-specific CI conclusions are recorded on PR #15 against the full candidate SHA;
this document does not substitute for those checks or grant Owner approval.
M086 remains NOT_STARTED. No external Paper or Live submission was performed.

## Starting identity and reproduced defect

Base master: `a224076754fb38909ee04c2464e50e51df12d7ad`.
Starting PR #15 head: `6d011ae150b2b6f0810548f0bb6f77d63896a758`.
Fresh Linux checkout, clean tree, matching origin branch; no AGENTS.md or CLAUDE.md.

Before editing production, `test_authorization_expiring_during_fetch_never_submits`
failed at the expected refusal assertion: `DID NOT RAISE PaperExecutionRefusedError`.
The controlled clock advanced two seconds during quote fetching against a one-second
permission. The original handler still submitted to its in-memory broker because it
checked the pre-fetch command instant. No real broker was involved.

## Corrected temporal contract

- Command receipt timestamps are not evaluation authority. Preview creation and
  submission rechecks use an injected M085 time source after evidence/DB preparation.
- The source supplies aware UTC plus finite monotonic time. Each operation uses the
  later of sampled wall time and initial UTC plus elapsed monotonic time. A stalled
  wall clock cannot extend validity; a backward wall/monotonic reading refuses.
- Broker clock timestamps must fall inside the measured request interval. No fixed
  allowance is used for fetch latency or clock skew. The broker timestamp plus
  the full monotonic round-trip duration forms an additional conservative upper
  bound, propagated through subsequent elapsed time. Uncertain alignment refuses;
  clock synchronization/venue clock disagreement may therefore block an operator.
- Quotes later than evaluation time refuse. The ten-second lead constant is removed.
  Quote maximum age remains unchanged; the bounded acceptance requirement remains 60s.
- Production claiming supplies a guarded clock callback. PostgreSQL obtains the
  authorization row lock first, then samples time and checks expiry before the atomic
  consumption/update and attempt insertion. Existing raw persistence callers retain
  their explicit timestamp API; that API alone is not proof of current wall time.
- The final gate executes inside the pinned HTTPS transport, after connection/TLS
  preparation and immediately before `HTTPConnection.request`. It reads the kill
  switch before its time sample and checks authorization, intent/liquidation expiry,
  known open regular session and its closing deadline, and quote freshness again.
- A failure after claim is recorded as NOT_SENT/REJECTED, with the authorization
  consumed and the deterministic identity retained. Repeating submission returns the
  existing attempt; it cannot create another order. Unexpected guard errors are also
  classified definitely-not-sent by the transport. Database cleanup failure can leave
  an already-claimed attempt requiring recovery, but cannot permit a retry.
- This is an application send boundary, not a guarantee about broker receipt time.
  OS scheduling and network time after the final check remain outside that boundary.
  Broker evidence is a sampled observation, not a guarantee of future venue state.

## Verification

- Baseline defect reproduced before production edits; regression passes after repair.
- Targeted handlers, clock/transport, composition, authority and hostile HTTP:
  270 passed (before the final additional PostgreSQL regression file).
- Twelve selected mutation families detected, each green baseline -> intended failure ->
  SHA-256 restoration -> green rerun; see `temporal-mutation-matrix.md`.
- New real-PostgreSQL tests cover observed row-lock waiting, expiry during that wait,
  terminal refusal after a post-claim delay, and exactly one controlled submission.
- A dedicated PostgreSQL 16 CI job rebuilds the complete migration history and runs
  those tests plus existing M085 lifecycle/concurrency and M084 audit tests. It also
  runs the lock-time mutation separately, restoring the source afterward.
- Full repository checks and CI results are recorded below after completion.

## Preservation and access limits

No M083/M084 production behavior, frozen authority or PROJECT_CHECKPOINT.md changed.
Historical market-open reports and the historical 41-family mutation matrix remain
unchanged; neither is relabeled as successful external acceptance.

This is a different machine from the Windows operator. Its M063 stash and Windows
exclude backup are inaccessible and have not been verified or restored here. The
fresh checkout has no stash. Its own `.git/info/exclude` SHA-256 before work is
`6671fe83b7a07c8932ee89164d1f2793b2318058eb8b98dc5c06ee0a5a3b0ec1`.
PROJECT_CHECKPOINT.md SHA-256 is
`37dccb45b9c8dc67f4fee85a1c7798a66c7fbfe2bd5eac2b15e7f93eae6c311e`.

Local Python 3.13.15 was installed in a separate virtualenv. Local PostgreSQL package
installation was unavailable because this container cannot perform apt's required
UID/group transitions. Real PostgreSQL verification is performed in CI, not claimed
as a local result. No Alpaca credentials are needed or read for this correction.

Direct git push lacks an authenticated credential helper here. Publication uses the
connected GitHub Git-data API to create a normal single-parent commit and update the
existing branch with force=false, followed by fetch and local tree/SHA verification.
No amend, rebase, force update, second PR, merge or freeze is used.

## Local verification completed

- Full PostgreSQL-OFF on Linux: 3486 passed, 1109 skipped, 8 failed and 12 errors;
  coverage 79.75%, unchanged floor 79%.
- All 20 failing/error node IDs were reproduced unchanged on a detached worktree
  of the original `6d011ae` (targeted affected legacy modules: 50 passed, 8 failed,
  12 errors). They concern pre-existing M063/M064/M065 LF/CRLF byte-seal assumptions.
  No new failure/error node ID; the frozen fixtures and tests were not changed.
- mypy: 365 source files clean; ruff check/format, compileall and architecture clean.
- Secret scanner: zero findings after scanning staged source targets.
- Windows foundation CI and real PostgreSQL CI remain required, not inferred from
  this local comparison.

## Additional boundary verification

- Propagation of broker round-trip time uncertainty has its own deterministic test
  and detected mutation; it cannot extend the permission beyond a conservative time.
- Actual preview/submit entrypoint functions are exercised through a supplied runtime
  context and prove that the injected source is used by both handlers.
- Updated temporal/handler/composition suites: 119 passed.
- First real PostgreSQL CI at `bc5894f52c4ae5c3b003dbfcf8874a86d6116f34`:
  119 passed, 10 skipped (shallow-history M084 audit checks), plus lock-time mutation
  1/1 detected. The dedicated workflow now fetches complete history so those checks
  can execute on the next candidate. https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/34689222158
- Wheel and source distribution built successfully locally after installing the
  declared build backend into the isolated virtualenv.

## Exact correction paths relative to starting head

- `.github/workflows/m085-temporal.yml`
- `external-review/MILESTONE-085/README.md`
- `external-review/MILESTONE-085/changed-files.txt`
- `external-review/MILESTONE-085/final-delivery-report.md`
- `external-review/MILESTONE-085/scope-and-design.md`
- `external-review/MILESTONE-085/temporal-correction.md`
- `external-review/MILESTONE-085/temporal-mutation-matrix.md`
- `external-review/MILESTONE-085/validation-results.md`
- `src/empirical_platform/decision_candidate/paper_execution.py`
- `src/empirical_platform/decision_candidate/paper_execution_repositories.py`
- `src/empirical_platform/entrypoints/_paper_composition.py`
- `src/empirical_platform/entrypoints/preview_paper_submission.py`
- `src/empirical_platform/entrypoints/submit_authorized_paper_order.py`
- `src/empirical_platform/shared/brokerage/alpaca_paper.py`
- `src/empirical_platform/shared/brokerage/paper_time.py`
- `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py`
- `src/empirical_platform/usecases/paper_execution.py`
- `tests/integration/test_m085_temporal_postgres.py`
- `tests/unit/_m085_fakes.py`
- `tests/unit/test_m085_paper_composition.py`
- `tests/unit/test_m085_paper_execution_domain.py`
- `tests/unit/test_m085_paper_execution_handlers.py`
- `tests/unit/test_m085_paper_time.py`
- `tools/m085_mutation_campaign.py`

## CI evidence and final verification location

The first implementation commit `bc5894f52c4ae5c3b003dbfcf8874a86d6116f34`
passed Windows foundation push CI: 3486 passed, 1129 skipped, coverage 79.86%
against the unchanged 79% floor; lint, types, architecture, security and build passed.
Run: https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/34689222122

The additional clock-bound and composition changes are in
`7f7e9c44849430335cd770bd8303a3834ac8957f`; production changes stop at that commit.
Later commits in this correction record evidence only. The final candidate's
Windows and full-history PostgreSQL CI must be checked independently, rather than
inheriting the preceding commit's result. Their exact run URLs, test counts and
conclusions are recorded in the updated PR description after completion:
https://github.com/drissbenlhoussine-code/empirical-platform/pull/15

The `changed-files.txt` name-status contract was verified against the pinned base:
70 PR paths, exact match. The focused correction changes the 24 paths listed above.
Both the checkpoint and this checkout's exclude file retain their original hashes.
External Paper acceptance remains outstanding; no order/merge/freeze is authorized.

---

# SUPERSEDED — the model above was replaced, and why

Everything above this line is PRESERVED as the record of what was implemented,
reviewed and believed at `2e5c38c0af6c3a6a115b668615fb81f42870af9c`. Two of its
conclusions did not survive measurement. They are corrected here rather than
edited above, so a reader can see what changed and on what evidence.

## Defect 1 — the alignment rule required apparent agreement, not certainty

The contract above states: *"Broker clock timestamps must fall inside the measured
request interval ... Uncertain alignment refuses."*

That condition is `requested_at <= timestamp <= received_at`, which is exactly
"zero host/broker offset is still plausible". It is not a test of whether time is
known well enough to act.

MEASURED, on the Owner's Windows 11 host synchronising against `time.windows.com`:

| Host offset vs NTP | `verify_broker` accepted |
|---|---|
| +0.019 s (immediately after a sync that stepped the clock) | 7/7 |
| +0.090 s (eight minutes later) | 1/12 |
| +0.110 s (after `w32tm /resync` and `/resync /rediscover`) | 0/12 |

The refusals were accurate about the host clock and useless as a gate: the ordinary
Windows time service settles around 0.10 s on this hardware, and repeated resyncs did
not reduce it. A bounded polling experiment (`MinPollInterval`, `MaxPollInterval`,
`SpecialPollInterval`) was run and then fully reverted with restoration verified; it
did not hold the clock inside the roughly 0.03 s of headroom the rule left. The host
configuration is not the defect corrected here — the rule is.

### The replacement, derived

Request leaves at monotonic `m0`, response is read at `m1`, the broker reports
`timestamp` sampled at an unknown `s` with `m0 <= s <= m1`. Then

    broker_clock(m1)  in  [ timestamp , timestamp + (m1 - m0) ]

Width is the measured round trip. Later instants add `(m - m1)` to both ends, so it
never widens.

WHAT THE INTERVAL IS: a bound on THE BROKER'S OWN CLOCK READING, on the broker's
timeline. WHAT IT IS NOT, stated because each was previously blurred:

1. it does **not** bound this host's clock skew — host and broker time are never
   differenced, so host error is neither measured nor needed;
2. it does **not** bound the broker's error against true time — if Alpaca's clock is
   wrong, every deadline derived from it is wrong by the same amount;
3. it does **not** bound the difference between the market-data host's clock and the
   trading host's — quote freshness rides the broker timeline under the STATED
   assumption that the two Alpaca hosts share a time base, which cannot be verified
   from one observation;
4. it does **not** detect replay from a SINGLE observation. `observe_broker_clock`
   compares each observation against the previous one. **MEASURED BOUNDARY:** the
   preview and dispatch paths observe the broker clock exactly ONCE per operation, so
   within one operation that check cannot fire. It is unit-tested directly against
   multiple observations and is not evidence that a forged single timestamp would be
   caught.

Deadlines are evaluated across the WHOLE interval and permitted only when they hold
at both ends. A quote age bounded by `[59 s, 61 s]` fails a 60 s ceiling. A session
close anywhere inside the interval counts as passed, so the market is treated as
closed and nothing is sent; the boundary is inclusive — `latest == close` refuses.

The ten-second `MAXIMUM_QUOTE_LEAD_SECONDS` constant is **not** reintroduced in any
form. The allowance for a quote arriving during the fetches is the MEASURED round
trip itself. Evidence too uncertain to decide is refused against the caller's own
freshness ceiling, not against a new constant.

## Defect 2 — persisted deadlines did not survive a host clock step across processes

The model above protected deadlines with operation-local monotonic time. That holds
**only within one process**. `ApprovedOrderIntent.expires_at`,
`mandatory_liquidation_at` and `ExecutionAuthorization.expires_at` are absolute UTC
instants written by the approving host's wall clock. Once that process exits, a host
clock that steps BACKWARD makes every stored deadline look further away, and a fresh
dispatch process has no monotonic memory to contradict it.

REPRODUCED DETERMINISTICALLY, before any fix
(`test_a_backward_host_clock_step_between_processes_cannot_extend_an_approval`): an
hour of real broker time passes, the host clock steps back an hour, and a 300-second
approval **dispatched** — `DID NOT RAISE`. The earlier claim in this document that
host-clock error is irrelevant was wrong.

### The correction: a persisted broker time basis

Authorizing now also reads `GET /v2/clock` — read-only; the command still sends no
order — and stores two readings taken at the SAME moment: `basis_host_at` and
`basis_broker_earliest_at` (migration `c7a41f0b52de`, both nullable, with a CHECK
constraint that they are set together). Their difference is a measured host-to-broker
mapping.

It is used ONLY to place a stored host deadline on the broker timeline, always using
the earliest broker reading, which makes every mapped deadline the soonest it could
be. It is enforced at three points: the pre-claim check, under the database row lock
(so a lock wait ages both timelines), and at the final pre-send guard.

MILESTONE-084 IS NOT REINTERPRETED. Its stored values are frozen, still rendered and
still enforced on the host timeline exactly as M084 wrote them. The broker-timeline
check is an ADDITIONAL M085 bound. A row with no basis cannot be mapped and is refused
rather than backfilled with a plausible value.

## What the tests now say, and what was deliberately removed

Collection reconciled mechanically against `2e5c38c`: **4617 baseline nodes, exactly
6 removed, 4611 still collected, 56 added, 4667 total.** The six removals, each an
intentional contract change:

| Removed node | Why |
|---|---|
| `test_uncertain_absolute_alignment_refuses[1]` and `[-1]` | asserted the defect itself — that a one-second host/broker difference must refuse |
| `test_broker_clock_uncertainty_refuses_before_claim` | contract deliberately inverted; replaced by `test_a_host_broker_clock_difference_alone_does_not_refuse` |
| `test_a_quote_further_ahead_than_the_lead_bound_is_refused` | renamed to `test_a_quote_after_the_latest_possible_broker_instant_is_refused`; the lead bound no longer exists |
| `test_each_condition_produces_its_own_refusal[override14-dated after this preview]` | refusal message changed |
| `test_broker_round_trip_uncertainty_cannot_extend_a_permission` | property preserved by `test_elapsed_processing_ages_the_broker_instant` and `test_a_stalled_host_wall_clock_still_ages_the_broker_instant` |

Preserved regressions: expired authorization during fetch, expiry during a database
lock wait, expiry during connection preparation, stale quote, market close crossed,
host clock stepped backward and forward across processes, process restart with a
correct clock, and **zero broker submissions on every uncertain or expired path**.

## Mutation campaign

**57 of 57 families detected, 0 blockers**, run sequentially with PostgreSQL on and no
concurrent writes to its targets. Restoration verified by SHA-256 over 731 files: all
identical.

An earlier run was treated as CONTAMINATED and discarded: a `post_fetch_time` target
was edited while it was running, and a run killed mid-campaign had left
`current-authority.schema.json` mutated (`minItems 13 -> 1`, `maxItems 13 -> 99`),
which an incomplete residue check — `.py` files only — had missed.

Four families needed correcting rather than the product:

- `broker_basis_authorization_expiry` initially survived because the new M084
  broker-deadline rule caught the same scenario; the test was narrowed so only the
  approval can expire.
- `broker_basis_required` failed by `AttributeError`; the guard was restructured so
  removing it falls through instead of crashing.
- `post_fetch_time` survived because freshness moved to the broker timeline; a new
  test isolates the post-fetch instant via an intent expiring during the fetch.
- `final_intent_expiry` and `claim_time_after_lock` survived because their host and
  broker checks are LOGICALLY EQUIVALENT while one process runs — the mapping offset
  cancels. Removing either copy leaves the rule standing. That is defence in depth,
  not a missing test, so both families now mutate the RULE: both enforcement points
  together. For `claim_time_after_lock` the post-lock re-reads cannot be removed at
  all — the claim is then left with no broker instant and the basis guard refuses —
  so that exact refusal is named as the expected fragment rather than accepting any
  assertion error as proof.

## External Paper acceptance: still PENDING

Unchanged by all of the above, and not closed by any of it. No Paper or Live order has
been submitted, no Owner approval exists, nothing is merged or frozen. Item 12 of the
exhaustion table still records the 2026-09-10 run as BLOCKED; that record stands as
history and is not evidence that the corrected product has been accepted by the
broker. A green internal checklist does not complete external acceptance.

---

# SUPERSEDED AGAIN — the persisted basis had one pairing and one provenance, and both were wrong

Everything above is PRESERVED as the record of what was implemented and believed at
`ddce3c83ad3a1941c1b6e9ccc38009af5ab1a473`. Direct source review found two concrete
defects in the persisted broker time basis described under *"The correction: a
persisted broker time basis"*. Both were reproduced deterministically on that commit
BEFORE any production change; the output is quoted below.

## What is superseded, precisely

- *"stores two readings taken at the SAME moment: `basis_host_at` and
  `basis_broker_earliest_at`"* — **false.** `basis_host_at` was the entrypoint's
  `authorized_at`, stamped before `GET /v2/clock` was sent; `basis_broker_earliest_at`
  was the broker's reply. They were never simultaneous, and nothing recorded the
  interval between them.
- *"It is used ONLY to place a stored host deadline on the broker timeline"* and the
  claim that M084's `expires_at` and `mandatory_liquidation_at` are enforced on the
  broker timeline through that basis — **unsound.** A basis measured when a human
  authorized cannot translate deadlines written when the intent was issued.
- *"A row with no basis cannot be mapped and is refused rather than backfilled"* —
  **half true.** It could not be mapped, but the dispatch path did not refuse it:
  `_refuse_expired_m084_deadlines_on_broker_time` returned early and
  `refusal_against` skipped every broker check when no basis existed. Found while
  reproducing Defect 1, reproduced, and corrected with the rest.
- The mutation families `broker_basis_recorded`, `broker_basis_required`,
  `broker_basis_authorization_expiry` and `m084_deadline_on_broker_time`, and the
  **57 of 57** result, describe rules that no longer exist in that form. They are
  replaced by the families listed under *Mutation campaign* below.

## Defect 1 — the authorization basis was not simultaneous

REPRODUCED at `ddce3c8`, before any production edit (controlled clock; 120 s
`GET /v2/clock` round trip; broker clock truthful, stamped as it replied):

    basis_host_at             2026-09-10 14:00:00+00:00
    basis_broker_earliest_at  2026-09-10 14:02:00+00:00
    effective broker deadline 2026-09-10 14:07:00+00:00 vs allowed 2026-09-10 14:05:00+00:00
    ... dispatch 350 s later, host clock an hour behind: Failed: DID NOT RAISE

The fetch latency was added to the host-to-broker offset, and every mapped expiry
moved later by exactly that latency.

### The repair: an interval, and the pairing it justifies

`PaperTimeWindow.measure_broker_basis` records four readings around the ONE clock
request: this host's conservative reading as the request leaves
(`basis_host_requested_at`), the broker's reported timestamp
(`basis_broker_earliest_at`), this host's conservative reading once the response is
read (`basis_host_at`), and the timestamp plus the measured monotonic round trip
(`basis_broker_latest_at`).

The mapping pairs the broker timestamp with the host reading taken AFTER the
response. The broker sampled its clock at an unknown instant `s` inside the round
trip; this host's clock at `s` read no later than `basis_host_at`, so the true offset
at `s` is at least `basis_broker_earliest_at - basis_host_at`. That smallest offset
places every mapped deadline at the soonest broker instant the evidence allows. The
readings are NOT described as simultaneous anywhere; the interval is stored.

`authorized_at` keeps its audit meaning — the instant the human act was recorded —
and is not the mapping basis. It may not postdate `basis_host_at` (domain and a
database CHECK), because the expiry is `authorized_at + validity` and a later
`authorized_at` would push the mapped expiry later.

ASSUMED, NOT MEASURED: that this host's wall clock does not step backward and forward
again inside the round trip (a net backward step between the two readings refuses),
and that the offset when a deadline was written equals the offset measured for it.

## Defect 2 — an authorization-time basis cannot translate an older M084 intent

REPRODUCED at `ddce3c8`, before any production edit, in exactly the requested sequence:
(1) intent issued with host and broker agreeing; (2) host clock moved back one hour;
(3) authorization taken; (4) a new dispatch process 20 minutes after the real M084
deadline, host clock still behind:

    M084 expires_at (host A)       2026-09-10 14:10:00+00:00
    mapped via authorization basis 2026-09-10 15:10:00+00:00
    ... Failed: DID NOT RAISE

### The repair: distinct provenance

- **Authorization deadlines** use only the basis measured for that authorization.
  `ExecutionAuthorization.on_broker_timeline` is documented, and tested, as
  translating that authorization's own expiry only.
- **M084 intent and liquidation deadlines** use only `paper_intent_time_basis`, an
  M085-owned, append-only evidence row per intent. `m084_deadline_refusal_on_broker_time`
  takes no authorization at all.
- **Binding to issuance.** `empirical-platform-issue-paper-bound-order-intent`
  (`IssuePaperBoundOrderIntentHandler`) measures the basis first, then calls
  MILESTONE-084's own `IssueApprovedOrderIntentHandler`, unchanged, with that exact
  host reading as `created_at`, then records the evidence. `intent_created_at` must
  equal `basis_host_at` (domain and database CHECK), so a basis measured later cannot
  describe an intent that already exists; the handler also refuses an existing intent.
- **Binding to the exact intent.** The fingerprint and the three M084 instants are
  copied into the evidence and compared on every use; a database insert guard
  compares them against the stored `approved_order_intent` row.
- **No backfill, no reinterpretation.** No migration writes a basis into an existing
  row. An intent issued through M084 alone, a legacy authorization carrying only the
  pair, and evidence describing another intent are all refused at preview and at
  dispatch; the intent check runs before any broker call.
- **M084 untouched.** No M084 file, table, column, constraint or trigger changed;
  M084's `issue-order-intent` still works and still issues M084 intents — they are
  simply not dispatchable by M085. The frozen-path gate is green.

A crash between issuing the intent and recording its evidence leaves an intent with no
evidence: refused, never repaired.

## Residual limits, stated

- M084 derives `expires_at` and `mandatory_liquidation_at` when the PROPOSAL is
  evaluated, before issuance. A host clock that moved between proposal evaluation and
  intent issuance is not measured by the intent-time basis; that interval is bounded
  only by M084's own approval expiry.
- The database enforces the SHAPE of both bases and binds evidence to the exact
  stored intent. It cannot know a measurement happened: a writer with INSERT authority
  could copy an intent's own `created_at` into a fabricated evidence row. The
  application has no such path; this is the same boundary as a disabled trigger or a
  superuser.
- Every bound is relative to the broker's clock. The four non-guarantees listed under
  *"WHAT IT IS NOT"* above still apply unchanged.
- Direct-SQL immutability gap closed in passing: before `d4f18a6c2e97` the
  authorization guard did not freeze the basis columns, so the single permitted
  consuming UPDATE could have rewritten them. The replaced guard freezes all four;
  the downgrade restores the exact prior function.

## Migration

`d4f18a6c2e97` (down revision `c7a41f0b52de`), additive: two nullable interval
columns with a pairing CHECK and a shape CHECK on `paper_execution_authorization`; the
authorization guard replaced to freeze all four basis columns; table
`paper_intent_time_basis` with fingerprint, endpoint, interval and issuance-binding
CHECKs, an insert guard against the stored M084 intent, and the M085 append-only
trigger. Downgrade removes exactly those objects and restores the prior guard text.

## Proof

Every row below is deterministic: controlled clocks, fake or controlled brokers, no
network, no real broker. PostgreSQL rows ran locally against PostgreSQL 16.13 in the
disposable database `m085_pgon_c7a41f0`, rebuilt from the complete migration history.

| Required proof | Where |
|---|---|
| broker-fetch latency cannot extend authorization validity | `test_broker_fetch_latency_cannot_extend_the_authorization_deadline` (unit, reproduces the defect's exact scenario); `TestBrokerFetchLatencyCannotExtendAnAuthorization` (PostgreSQL, separate processes, host clock behind) |
| host and broker bases conservatively associated | `test_a_basis_pairs_the_broker_timestamp_with_the_host_reading_after_the_response`; `test_the_mapping_never_places_a_host_instant_later_than_the_broker_really_was` (15 cases: stamp early/mid/late in the round trip, host ahead/behind/exact); `test_the_interval_is_recorded_rather_than_a_single_moment`; stored interval asserted through PostgreSQL |
| host offset changes between M084 intent issuance and M085 authorization | `test_a_host_clock_moved_between_intent_and_authorization_cannot_extend_the_m084_deadline` (unit, the requested 4-step sequence) and `TestAnIntentsDeadlinesUseTheBasisOfItsOwnIssuance` (PostgreSQL); negative halves that still dispatch inside both real deadlines |
| restart between intent, authorization and dispatch | `test_issue_authorize_and_dispatch_as_three_processes_dispatch_exactly_once` and every PostgreSQL scenario: each command is its own service and time window |
| missing or mismatched intent-time basis | M084-only intent refused at preview and at dispatch before any broker call; mismatched fingerprint / created_at / expires_at / liquidation refused in domain, handler and database; backfill refused by the issuance handler, the domain and the database CHECK; crash between issue and record leaves the intent undispatchable |
| authorization expiry and M084 deadlines independent | `test_authorization_expiry_and_intent_deadlines_do_not_borrow_each_others_basis`; `test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization`; legacy pair-only and basis-less authorizations refused |
| expiry during fetch, lock wait and connection preparation | existing `test_elapsed_work_cannot_extend_a_deadline` (now with matching evidence), `test_real_row_lock_wait_cannot_consume_expired_permission`; new `test_an_m084_deadline_passing_only_on_the_broker_clock_never_submits[fetch/claim/prepare/connect]` and the PostgreSQL deadline-inside-the-claim case |
| zero broker submissions on every refusal | asserted in every refusal test above (`broker.submitted == []`, no attempt, authorization unconsumed where refused before claim) |
| migration up/down/up | `test_the_migration_goes_down_and_up_again`: head -> `c7a41f0b52de` (table, columns, constraints and insert guard gone; prior guard text restored) -> head, catalog identical |
| direct-SQL pair and integrity constraints | half interval, interval without pair, inverted host/broker interval, authorized_at after basis, half pair, basis columns rewritten by the consuming UPDATE, evidence mismatch, unknown intent, not bound to issuance, inverted evidence intervals, append-only, one row per intent -- each with an accepted control |

| Gate (final tree, before commit) | Result |
|---|---|
| Full suite, PostgreSQL OFF, Windows 11, Python 3.13.14 | **3619 passed, 1142 skipped, 0 failed**; coverage **80.06%** against the unchanged 79% floor |
| PostgreSQL ON: time-basis, temporal, lifecycle, concurrency, M084 file audit | **162 passed, 0 failed** |
| M085 authority contract, hostile HTTP, architecture tests | 196 passed |
| `ruff format --check` / `ruff check` / `mypy` (366 files) / `compileall` | clean |
| `tools/check_architecture.py` / negative fixture | clean / correctly refused |
| `tools/check_frozen_paths.py` | 27 governed paths unmodified since `707161a1e8ed` |
| secret scan and dependency audit (`scripts/security.ps1`) | clean: 1317 targets scanned, no secret; pip-audit found no known vulnerability (the unpublished package itself is skipped as not on PyPI). First attempt used a system Python without pip-audit and did not run; a second run reported one high-entropy revision literal in the new PostgreSQL test, which was re-spelled |
| `python -m build` | sdist and wheel built |

## Mutation campaign

Families are listed by the basis they protect, each with its detecting test named first
(`tools/m085_mutation_campaign.py`). Authorization-time basis:
`authorization_basis_pairs_the_post_response_host_reading`,
`authorization_basis_interval_required`, `broker_basis_required`,
`broker_basis_authorization_expiry`, `authorization_not_future_dated_against_its_basis`,
`database_basis_interval_shape`, `database_basis_immutable`. Intent-time basis:
`m084_deadline_on_intent_time_basis`, `intent_basis_required`,
`intent_basis_matches_the_exact_intent`, `intent_basis_bound_to_issuance`,
`issuance_uses_the_measured_host_reading`, `database_intent_basis_matches_intent`,
`database_intent_basis_bound_to_issuance`. All run sequentially with PostgreSQL on
(disposable database `m085_pgon_c7a41f0`), nothing else writing to the tree.
Restoration was checked per family by SHA-256 and, around every run, over EVERY
tracked and untracked file (1317, including JSON, schema and migrations).

| Run | Scope | Result | Tree-wide restoration |
|---|---|---|---|
| 1 | all 67 families | **64 of 67 detected, 3 blockers** | 1317 files, 0 changed / removed / added |
| 2 | the 3 blockers + 3 families sharing the tightened test | 6 of 6 | 1317 files, 0 changed |
| 3 | all 67 families, final tree | **67 of 67 detected, 0 blockers** | 1317 files, 0 changed / removed / added |

The three run-1 blockers, each corrected in the TEST OR TARGET, never in the rule:

- `post_fetch_time` survived. The preview's new broker-timeline check on the intent's
  own basis refuses the same expired intent when host and broker agree, so freezing
  the preview's host instant before the fetch still produced a refusal. Defence in
  depth, but the named test no longer isolated the post-fetch HOST instant. It now
  issues the intent with the host an hour behind the broker, so only the host check
  can refuse, and asserts the refusal is not the broker-clock one.
- `final_intent_expiry` survived because of a defect THIS correction introduced in the
  test suite: `test_elapsed_work_cannot_extend_a_deadline[intent-*]` replaced the
  intent after authorization but kept evidence for the original, so dispatch was
  refused up front for mismatched evidence and the `except ValueError: pass` accepted
  it. Every `[intent-*]` case was vacuous. The evidence is now replaced with the intent,
  and a refusal about basis evidence fails the test.
- `database_single_use_trigger` survived because `d4f18a6c2e97` replaces the
  authorization guard, so the guard enforced at head is that migration's copy; the
  family still mutated the original text in `b1e9d47c30a5`. It now targets the enforced
  copy. The authority contract test still reads its enforcement fragments from
  `b1e9d47c30a5`, where they also remain -- a limit of that check, recorded here.

`mutation-matrix.md` is run 3. The previous **57 of 57** result is superseded.

## Collection reconciliation

Collected with PostgreSQL off. Baseline collected in a detached worktree at
`ddce3c8` with that commit's own `src` first on the path (a first collection that
imported the working tree's source gave the identical list).

| | Nodes |
|---|---|
| baseline `ddce3c8` | 4667 |
| retained | 4666 |
| removed | 1 |
| added | 95 |
| head | 4761 |

Removed: `test_m085_entrypoints.py::TestTheTableCoversEveryConsoleScript::test_there_are_exactly_twelve`,
renamed `test_there_are_exactly_thirteen` because the Paper-bound issuance command is a
thirteenth M085 console script. Added: 32 in `test_m085_time_basis_postgres.py`, 19 in
`test_m085_paper_execution_domain.py`, 19 in `test_m085_paper_time.py`, 16 in
`test_m085_paper_execution_handlers.py`, 8 in `test_m085_entrypoints.py` (the new
command across the parametrized CLI properties, and the renamed count), 1 in
`test_m085_paper_execution_postgres.py` (the new append-only table).

## External Paper acceptance: still PENDING

Unchanged by this correction and not closed by it. No Paper or Live order was
submitted; no Owner approval, merge, freeze, checkpoint change or M086 work occurred.
The only broker calls this correction adds are read-only `GET /v2/clock` requests, and
none was made against the real broker: every test uses controlled clocks.

---

# SUPERSEDED A THIRD TIME — a deadline was translated through a basis measured after it was written

Everything above is PRESERVED as the record of what was implemented and believed at
`73a2f968b61909f3ae97c2d957fb85ae975e461c`. An independent review traced one concrete
path through it that reaches the broker with an expired proposal and approval. It was
reproduced deterministically on that commit, through real PostgreSQL and real
MILESTONE-084 code, BEFORE any production change.

## What is superseded, precisely

- *"M084 intent and liquidation deadlines use only `paper_intent_time_basis`"* and
  *"Only an issuance basis can translate them"* — **unsound.** `expires_at` and
  `mandatory_liquidation_at` are written when the PROPOSAL is evaluated and copied
  unchanged into the intent. A basis measured at issuance maps them by whatever the host
  clock did between evaluation and issuance.
- The residual limit *"that interval is bounded only by M084's own approval expiry"* —
  **false.** The approval expiry is written on the same host timeline and checked again
  by M084 on the host clock at issuance, so a backward host step defeats it too.
- The mutation family `m084_deadline_on_intent_time_basis` in `mutation-matrix.md`
  (run 3, **67 of 67**) protected the rule that WAS the defect. It is replaced by
  `m084_deadline_on_proposal_time_basis` and the families listed under *Mutation
  campaign* below. The other 66 rows of run 3 are unaffected and were not re-run.
- *"The authority contract test still reads its enforcement fragments from
  `b1e9d47c30a5`, where they also remain -- a limit of that check, recorded here."* —
  **no longer a limit.** The contract now checks the SQL installed at migration head.

## The defect, reproduced at `73a2f96`

The requested sequence, each step its own process against PostgreSQL 16.13
(`m085_pgon_c7a41f0`, rebuilt from the complete migration history):

1. Proposal evaluated and approved with host and broker agreeing: proposal expiry
   +300 s, approval expiry +120 s from the decision.
2. Real broker time advances one hour; this host's clock falls back to just after the
   evaluation.
3. `IssuePaperBoundOrderIntentHandler` measures its basis. Every M084 host-clock check
   passes; the issuance basis maps the proposal expiry an hour late;
   `m084_deadline_refusal_on_broker_time` returns None.
4. Preview, authorization and dispatch follow.

    FAILED tests/integration/test_m085_time_basis_postgres.py::TestAStaleProposalAndApprovalCannotReachTheBroker::test_the_chain_is_refused_somewhere_and_nothing_is_sent
    E   AssertionError: a proposal and approval that expired an hour ago on the broker's clock reached the broker: 1 submission(s)
    E    +  where True = PaperSubmissionResult(... dispatched=True, http_status=200, broker_status='accepted', ...).dispatched

The broker fake received one submission.

## The repair: each deadline carries the provenance of the act that wrote it

| Deadline | Written when | Translated ONLY through |
|---|---|---|
| proposal `expires_at` (= intent `expires_at`) | proposal evaluation | `paper_proposal_time_basis` |
| proposal `mandatory_liquidation_at` (= intent's) | proposal evaluation | `paper_proposal_time_basis` |
| approval `expires_at` | human decision | `paper_decision_time_basis` |
| authorization `expires_at` | human authorization | the authorization's own interval (unchanged) |

- **Measured in the act.** `empirical-platform-prepare-paper-bound-trade-proposal`
  (`PreparePaperBoundTradeProposalHandler`) reads `GET /v2/clock`, then runs
  MILESTONE-084's own `PrepareTradeProposalHandler`, unchanged, with the post-response
  host reading as `evaluated_at`, then records the evidence.
  `empirical-platform-decide-paper-bound-trade-proposal`
  (`DecidePaperBoundTradeProposalHandler`) does the same for M084's
  `DecideTradeProposalHandler` with `decided_at`. Neither command accepts an instant.
- **Bound to the act.** `proposal_created_at` and `decided_at` must equal the basis host
  reading (domain `ValueError` and database CHECK), so a basis measured later cannot
  describe a record that already exists; both handlers also refuse an existing record.
- **Bound to the exact record.** Proposal evidence copies the version, fingerprint,
  `expires_at` and `mandatory_liquidation_at`; decision evidence the decision,
  proposal, version, fingerprint, `decided_at` and approval expiry. They are compared on
  every use and, at insert, by database guards against the stored M084 rows.
- **Chronology, each deadline through its own basis.** An approval is refused when the
  proposal may have expired on the broker's clock at the decision. Issuance is refused
  — BEFORE M084 writes an intent — when the issuance interval may be at or after the
  proposal expiry, the liquidation deadline, or the approval expiry. Every act's own
  broker interval is used; an interval that might reach a deadline counts as after it.
- **The issuance basis translates no deadline.** It records WHEN the intent was issued,
  so the chronology can be checked again at preview and dispatch.
- **At preview, pre-claim and the final send boundary** the intent deadlines are mapped
  through the proposal-time basis only, and all three provenance rows plus the
  chronology are re-verified.
- **No backfill.** No migration writes evidence. A proposal or approval created through
  MILESTONE-084 alone has none; it is refused at approval, at issuance, at preview and
  at dispatch, and none is derived later.
- **Unchanged:** deterministic `client_order_id`, the atomic single-use claim, and the
  separate final human execution authorization. No M084 file changed; M084's own
  commands still work and still write M084 records — they are simply not usable for
  Paper.

## Migration

`e61b3f9a4c27` (down revision `d4f18a6c2e97`), additive: tables
`paper_proposal_time_basis` and `paper_decision_time_basis`, each with endpoint, host
and broker interval, fingerprint, act-binding and expiry-follows CHECKs, a
`SET search_path` insert guard against the stored M084 row, and the M085 append-only
trigger. M084's `trade_proposal` and `trade_approval_decision` gain nothing. Downgrade
removes exactly those objects.

## The authority contract now reads the SQL installed at head

`test_m085_authority_contract.py` read only `b1e9d47c30a5`, while `d4f18a6c2e97`
replaces the authorization guard with `CREATE OR REPLACE FUNCTION`. The contract now
renders the whole M085 chain's upgrade SQL with Alembic offline, takes each function's
LAST definition (a later DROP removes it), and checks every enforcement claim against
that installed state. It pins that the chain is exactly the four M085 revisions ending
at head, that every function definition was parsed, that the installed authorization
guard is `d4f18a6c2e97`'s and the original is superseded, and — with a synthetic chain —
that a rule surviving only in a replaced or dropped definition is not installed.

New claims, each checked mechanically: `proves`
`each_m084_deadline_is_translated_only_through_the_basis_of_the_act_that_wrote_it`
(parsed: the receivers of `on_broker_timeline` in the two deadline rules);
`database_enforcement` `time_basis_evidence_describes_the_exact_proposal_approval_or_intent_by_trigger`,
`time_basis_evidence_is_bound_to_the_instant_of_its_own_act_by_check_constraint`,
`time_basis_evidence_is_append_only_and_never_backfilled`; `structural_limitations`
`an_m084_only_proposal_approval_or_intent_has_no_time_basis_and_is_never_dispatchable`,
`a_writer_with_insert_privilege_can_store_correctly_shaped_evidence_nobody_measured`.

## Residual limits, stated

- ASSUMED, NOT MEASURED: that the host-to-broker offset while M084 computed a deadline
  equals the offset measured in the same command around that computation.
- The database binds evidence to the exact record and the instant of its act. It cannot
  know that a broker clock was read: a writer with INSERT privilege could store
  correctly shaped evidence nobody measured. The application has no such path.
- Every bound is relative to the broker's clock, as before.

## Proof

Deterministic throughout: controlled clocks, fake or controlled brokers, no network.
PostgreSQL rows ran against PostgreSQL 16.13 in `m085_pgon_c7a41f0`, rebuilt from the
complete migration history.

| Required proof | Where |
|---|---|
| the reviewed path, end to end, zero submissions | `TestAStaleProposalAndApprovalCannotReachTheBroker::test_the_chain_is_refused_somewhere_and_nothing_is_sent` (PostgreSQL, separate processes): refused at issuance with *"the proposal had expired on the broker's clock when the intent was issued"*, `broker.submitted == []`, no M084 intent and no intent evidence written. FAILED at `73a2f96` with one submission |
| a proposal and approval created through M084 alone | `test_a_native_m084_proposal_and_approval_cannot_be_issued_for_paper` (PostgreSQL): refused *"no proposal-time broker basis"*, zero submissions, no intent; `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` (handler, both rows, no clock read); an M084-only intent refused at preview and dispatch |
| a proposal that expired on the broker's clock cannot be approved | `test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved` (handler and PostgreSQL): nothing written |
| proposal deadlines through the evaluation basis only | `test_the_intent_deadline_is_mapped_through_the_proposal_basis`, `test_the_mandatory_liquidation_deadline_is_mapped_too`, `test_an_issuance_basis_cannot_rescue_deadlines_written_at_evaluation` |
| approval expiry through the decision basis only | `test_an_approval_that_expired_before_issuance_is_refused`, `test_an_approval_recorded_after_the_proposal_expired_is_refused` |
| each basis bound to its own act and exact record | domain `ValueError` on a basis not at the act's instant; handler tests that `evaluated_at` / `decided_at` / `created_at` are the post-response host reading; mismatched proposal and decision evidence refused at preview; database: exact copies accepted, another fingerprint / expiry / liquidation / instant refused by the insert guards, a later basis refused by `ck_paper_proposal_time_basis_bound_to_evaluation` and `ck_paper_decision_time_basis_bound_to_decision`, unknown records refused, append-only and one row per record |
| migration up/down/up | `test_the_provenance_migration_goes_down_and_up_again` (head -> `d4f18a6c2e97` -> head; the intent-time table untouched); the existing `test_the_migration_goes_down_and_up_again` crosses it; every new guard function pins `search_path` |
| deterministic `client_order_id`, atomic single-use claim, final human authorization | unchanged; their existing unit, PostgreSQL and concurrency tests pass unmodified in intent |
| authority contract tests the SQL installed at head | `TestTheContractReadsTheSqlInstalledAtHead`, `TestTheTemporalProvenanceRulesAreInstalled`, and every enforcement claim checked against installed SQL |

## Mutation campaign

Only the affected families were run: `provenance-mutation-matrix.md`, **24 of 24**
detected on the final source over two sequential runs (run 1: 23 of 24, one blocker whose
expected failure reason was corrected in the campaign; run 2: 1 of 1), each bracketed by
a SHA-256 digest of every tracked and untracked file (1320, 0 changed). The same
authority-family mutation SURVIVED the replaced contract at `73a2f96` (15 passed).
Performance, hostile-review and external acceptance campaigns were not repeated: this
correction does not change them.

## Collection reconciliation

Collected with PostgreSQL off. Baseline in a detached worktree at `73a2f96` with that
commit's own `src` first on the path.

| | Nodes |
|---|---|
| baseline `73a2f96` | 4761 |
| retained | 4742 |
| removed | 19 |
| added | 87 |
| head | 4829 |

Removed, each replaced: 15 parametrized cases and one test of
`test_every_database_enforcement_claim_names_something_in_the_migration` /
`test_the_migration_declares_no_foreign_key_into_the_m084_intent`, renamed to
`..._names_sql_installed_at_head` (now 24 cases) and
`test_the_installed_schema_declares_no_foreign_key_into_the_m084_intent` because they no
longer read one migration file; `test_there_are_exactly_thirteen`, renamed
`test_there_are_exactly_fifteen` for the two new console scripts;
`test_missing_intent_evidence_refuses_the_preview`, replaced by the parametrized
`test_missing_evidence_for_any_act_refuses_the_preview` over all three acts; and
`test_the_intent_deadline_is_mapped_through_the_intent_basis`, which asserted the
superseded rule and is replaced by `test_the_intent_deadline_is_mapped_through_the_proposal_basis`.
Added: 36 in `test_m085_authority_contract.py`, 16 in `test_m085_time_basis_postgres.py`,
15 in `test_m085_entrypoints.py`, 9 in `test_m085_paper_execution_domain.py`, 9 in
`test_m085_paper_execution_handlers.py`, 2 in `test_m085_paper_execution_postgres.py`.

## Gates

| Gate (final tree, before commit) | Result |
|---|---|
| Reproduction at `73a2f96`, before any production change | the reviewed path reached the broker fake: 1 submission, `dispatched=True` |
| Full suite, PostgreSQL OFF, Windows 11, Python 3.13 | **3669 passed, 1160 skipped, 0 failed**; coverage **80.10%** against the unchanged 79% floor |
| PostgreSQL ON (`m085_pgon_c7a41f0`, head `e61b3f9a4c27`): temporal, time-basis, lifecycle, concurrency, M084 file audit | **180 passed, 0 failed** |
| M085 authority contract | 71 passed (offline Alembic rendering, no database) |
| Affected mutation families, sequential, PostgreSQL ON | **24 of 24** over two runs; tree-wide restoration 1320 files, 0 changed, after each |
| Test collection vs `73a2f96` | 4761 baseline, 19 removed (each replaced, listed above), 4742 retained, 87 added, 4829 total |
| `ruff format --check` / `ruff check` / `mypy` (368 files) / `compileall` | clean |
| `tools/check_architecture.py` / negative fixture | clean / correctly refused |
| `tools/check_frozen_paths.py` | 27 governed paths unmodified since `707161a1e8ed`; no M083 or M084 file changed |
| `tools/render_m085_authority.py --check` | the document is the rendering of the contract |
| secret scan and dependency audit (`scripts/security.ps1`, venv on PATH) | clean: 1320 targets scanned, no secret; pip-audit found no known vulnerability (the unpublished package itself is skipped as not on PyPI) |
| `python -m build` | sdist and wheel built |

## External Paper acceptance: still PENDING

Unchanged by this correction and not closed by it. No Paper or Live order was
submitted; no Paper authorization, Owner approval, merge, freeze, checkpoint change or
M086 work occurred. The broker calls this correction adds are read-only
`GET /v2/clock` requests in the two new commands, and none was made against the real
broker: every test uses controlled clocks. `tools/m085_paper_acceptance.py` and
`tools/m085_operator_walkthrough.py` now evaluate and approve through the Paper-bound
commands; neither was run.
