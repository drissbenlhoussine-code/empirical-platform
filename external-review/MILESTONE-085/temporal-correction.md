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
