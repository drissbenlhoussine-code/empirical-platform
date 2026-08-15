# MILESTONE-074 - Historical Portfolio Evidence in the Daily Research Brief - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M074
baseline `328e8b014541107165932ddcf19c14f7b0f56cdc` (the merge of PR #3
carrying the M073 checkpoint next-action correction; M073 fully
`APPROVED_AND_FROZEN`). Delivered through pull request #4, owner-approved
at head `822451376ab2ec1594df0d056b0e0ba740e69928` with the `foundation`
workflow green on that exact SHA, and merged into `master` as
`5e9e0b61d19870a3f1686e7f9b1c4ee8c8b54e24`.

**Documented deviation from M070-M073 precedent.** M074 has no separate
`MILESTONE_074_..._SCOPE_AND_DESIGN.md` document. Its scope, design
rationale, compatibility rules, and candidate ranking are recorded in the
module docstring of
`src/empirical_platform/decision_candidate/historical_portfolio_evidence.py`,
in pull request #4's own description, and in `.validation-proof-m074/`.
This is recorded here as a real gap rather than papered over; it does not
affect the delivered capability or its evidence.

## Delivered Capability

The M072 daily research brief now surfaces separately persisted,
structurally compatible historical research evidence -- an M064
survivorship-aware robustness study and its companion M067 portfolio
evidence report -- under a strict honesty banner, in both the text and
`--json` renderings. A read-only, M074-owned query boundary loads the
persisted candidates; a pure, I/O-free compatibility rule (H1-H4 policy
identity, W window count, C classification, U1/U2 universe coverage, L
lineage integrity, T coverage timestamp, F future-evidence rejection, S
staleness) annotates each candidate with exactly one closed status and
deterministically selects at most one. `--no-historical-evidence`
suppresses the lookup itself on both daily paths.

Zero new domain aggregate, zero new PostgreSQL table, zero new migration,
zero new business logic, zero M068 dependence surface, and no paper,
live, current-position, or profitability semantics anywhere.

## M063 Exceptional Byte-Seal Reconciliation

M074 could not reach a green `foundation` workflow on any branch, because
a defect inherited from frozen MILESTONE-063 failed 14 M063 unit tests on
every clean checkout. The M063 dataset bundle's tamper-detection seal
recorded `ca98478c...`, the digest of a Windows working-tree (CRLF)
materialization -- a byte sequence that has never existed in the git
object database. It validated only under `core.autocrlf=true`.

Under narrow, explicit owner authorization, that seal was reconciled to
the committed blob's own digest `76560196...` (blob `800ecb19`, unchanged
since M063 was implemented in `1937594b`), together with a `-text`
`.gitattributes` pin scoped to that single fixture path so every platform
materializes those exact bytes. **Zero fixture bytes changed. The entire
repair is four lines, one seal constant per file.**

Semantic equivalence, canonical-result equivalence across every M063
metric, window, and derived backtest run, and M064/M065 non-interference
were each proven independently. The full record is
`MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md`.

**MILESTONE-063 remains `APPROVED_AND_FROZEN`. Its original freeze
document is untouched and remains historical truth, including the seal
value it recorded.** This freeze does not reopen, amend, or reinterpret
M063; it records that a non-semantic byte-seal repair was authorized and
applied, and where that repair is documented.

## Implementation Evidence

- **Source:** three new modules -- `decision_candidate/historical_portfolio_evidence.py`
  (pure compatibility rule and read-only value objects),
  `decision_candidate/historical_portfolio_evidence_query_repository.py`
  (Protocol), and
  `shared/persistence/postgres_repositories/historical_portfolio_evidence_query_repository.py`
  (SELECT-only adapter) -- plus `usecases/discover_historical_portfolio_evidence.py`
  and read-only extensions to the M072 brief model, brief IO, brief
  handler, runtime composition, and both daily entrypoints.
- **Tests:** 29 pure unit tests plus 6 real-PostgreSQL integration tests
  across a lifecycle suite and an independent second-pass suite.
- **Regression:** `1863 passed, 357 skipped`, coverage **80.01%** against
  an unchanged 79% floor with PostgreSQL off; `2206 passed, 14 skipped`,
  coverage 91.93% with PostgreSQL on.

## Canonical Results

Verified on fresh clones against a PostgreSQL 16 instance created for the
purpose, after the original closure run was interrupted and its container
lost. Nothing was carried over from the interrupted run.

| Environment | Result |
|---|---|
| Clean clone, `core.autocrlf=true`, PostgreSQL off | 1863 passed, 357 skipped, coverage 80.01% |
| Clean clone, `core.autocrlf=true`, PostgreSQL on | 2206 passed, 14 skipped, coverage 91.93% |
| M070-M074 integration, pass 1 | 24 passed, 5 skipped |
| M070-M074 integration, pass 2, brand-new database | 24 passed, 5 skipped |

Clean-clone seal reproduction: two clones of the same commit differing
only in `core.autocrlf` both materialize the M063 fixture to
`76560196...`, which is what the `-text` pin exists to guarantee and what
the pre-repair seal could not do on both platforms at once.

## Hostile Review

Three independent passes are recorded in `.validation-proof-m074/`:
`HOSTILE_REVIEW.md` (100 checks), `HOSTILE_RE_REVIEW.md`, and
`HOSTILE_REVIEW_RECOVERY.md` (89 checks, run fresh after the
interruption rather than inherited).

The recovery pass found one genuine defect, fixed inline with two
regression tests: `_evaluate_compatibility` returned a naive
`datetime.min` as the `coverage_end` sentinel for candidates rejected
before coverage could be derived, while every candidate reaching rule T
carried a timezone-aware timestamp. Sorting both kinds through one
datetime key raised `TypeError: can't compare offset-naive and
offset-aware datetimes` whenever one candidate was rejected early and
another late in the same call. The brief handler caught it, so the brief
still rendered -- but it rendered the "discovery failed ... not a
confirmed absence of compatible evidence" warning and zero candidates,
when the lookup had succeeded and both candidates had already been
correctly classified INCOMPATIBLE with reasons. The sentinel is now the
named, timezone-aware `NO_COVERAGE_DERIVED`.

Two findings were recorded for the owner rather than changed: the
`absence_reason` JSON key is present only in the empty-evidence branch,
and discovery issues one portfolio lookup per M064 study.

## Canonical Validation

`ruff format --check` (557 files), `ruff check`, `mypy` (280 source
files), the architecture checker, the negative architecture fixture,
`pip-audit`, the secret scan (975 targets, 0 findings), and
`python -m build` all pass. GitHub Actions `foundation` run
`31874225648` completed `success` on head
`822451376ab2ec1594df0d056b0e0ba740e69928`, with all fourteen steps
green.

Two genuine CI-harness defects were found and corrected during closure,
both pre-existing and neither in product code. The `Negative architecture
fixture` step inherited the checker's deliberate non-zero exit through
GitHub's `pwsh` wrapper, so the gate reported broken every time it
actually worked. And a plain-text evidence file of bare `label: <64 hex>`
lines tripped detect-secrets; it was rewritten as markdown rather than
widening `_BENIGN_HIGH_ENTROPY_LINE_PATTERNS`, because loosening a
security gate to accommodate an evidence file is the wrong direction.

## Logically Independent Second Pass

`tests/integration/test_m074_historical_portfolio_evidence_second_pass.py`
re-establishes M074's central claim independently. It was additionally
re-run during closure against a database created fresh for that pass
rather than a truncated reuse of the first, with identical results.

## Freeze-Impact on Earlier Milestones

Every pre-M074 Python file this milestone touches was verified
**AST-identical** to its `master` counterpart -- the M067 migration
`a3f7c81e4b96`, the M067 portfolio-study lifecycle test, and both M068
usecase modules changed by `ruff format` reflow only, with zero semantic
change. M064 and M065 fixture blob OIDs are identical to `master`, no
M064/M065 test file was touched, and `git check-attr text` reports
`unspecified` for every M064/M065 fixture -- git's untouched default.

## Known Remaining Defect, Explicitly Not Repaired

M062, M064 and M065 carry the same seal-authoring defect M063 carried:
digests recorded from Windows working-tree materializations rather than
committed blobs. On a clean LF checkout this milestone's head fails 8
tests with 12 errors; `master` before it failed 22 with 12 on the same
clone. The 14-test improvement is exactly the M063 repair, and nothing
regressed. CI runs on `windows-latest`, so none of it surfaces there.

This was deliberately left unrepaired: the owner's authorization covered
M063 only. It is recorded in section 8 of
`MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md` so the exposure is
documented rather than discovered later. **Each of M062, M064 and M065
warrants its own authorization.**

## No Duplicated Business Logic / No New Schema / No Broker / No LLM

No new table, no new migration revision, no `create_table` statement, no
new domain aggregate. The M064 domain, protocol and concrete repository
are untouched; so are M067's and M070's `ResearchSession` domain and
schema. The persistence adapter issues `SELECT` only, with every
parameter bound. No broker, no paper account, no live risk, no order
path, no network dependency in the compatibility rule, and no LLM
anywhere in this milestone.

## Owner Approval

The owner independently verified PR #4's head, open state, base branch,
and the fully green `foundation` workflow on GitHub, then required the
owner-verification script to be executed from the project root
unmodified before granting approval. It returned **21 passed, 0 failed**,
proving from Git objects rather than narrative that the M063 fixture blob
is unchanged and identical to `master`, that the new seal is the sha256
of that committed blob, that the entire M063 change is four seal-constant
lines, that every M064/M065 fixture blob is identical to `master`, that
the touched pre-M074 files are AST-identical, that no migration was
added, and that PR #4 was not yet merged.

**Freeze declaration:** `M074 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M074 APPROVED_AND_FROZEN`.

## Deferred / M074 Boundary

Explicitly out of scope and not built: any M068 dependence surface in the
daily brief, any write path over M064/M067 evidence, concurrent-position
handling, persistent operator configuration beyond existing CLI defaults,
paper trading, live trading, and any LLM-based decision or rendering
path. The M062/M064/M065 seal exposure above was deliberately not
repaired. **MILESTONE-075 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-075 -- recommendation only; not started as part of M074.
