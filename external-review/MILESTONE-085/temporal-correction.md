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
