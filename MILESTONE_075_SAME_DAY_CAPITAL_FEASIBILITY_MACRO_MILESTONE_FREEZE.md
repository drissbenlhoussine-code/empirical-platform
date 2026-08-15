# MILESTONE-075 - Same-Day Capital Feasibility - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M075 baseline
`9b427594814e3eda9fb8b598aa7119349dcbd581` (the M074 Owner Freeze
hash-recording HEAD; M074 fully `APPROVED_AND_FROZEN`), independently
re-verified from git at mission start rather than taken from the mission
text. Delivered through pull request #5, owner-approved at head
`d4b41dc7fa2482f08cc3acbd4a53ff4c0e490f36` with the `foundation` workflow
green on that exact SHA, and merged into `master` as
`2b3069749bf44237d248ac5482f39b8839ae411f`.

Scope, capability matrix, five-candidate ranking, architecture, temporal
semantics, and the pre-implementation adversarial design review are recorded
in `MILESTONE_075_SAME_DAY_CAPITAL_FEASIBILITY_SCOPE_AND_DESIGN.md`.

## Why M075 Exists

A fresh, repository-grounded product inventory found a defect that is
arithmetic, not opinion. M060 sizes every `PositionPlan` independently
against the *same, full* `supplied_account_equity`, capped at
`maximum_notional_percent = 0.25`; `build_position_plan()` takes no argument
describing any other position. Five approved plans in one session therefore
commit up to **125%** of that equity, ten up to **250%** -- and the daily
brief said nothing about it. Confirmed directly against source: no `sum(`,
no total notional, and no capital policy anywhere in the daily path.

Meanwhile M067 already models concurrent capital correctly --
`max_concurrent_positions`, `max_capital_utilization_percent`, and a closed
rejection vocabulary for exactly this situation -- but only for *historical*
simulation. The platform knew how to reason about aggregate capital and had
never applied that reasoning to the one artefact a human acts on each
morning.

Four alternatives were ranked and rejected with specific reasons: durable
position state (M075 is its precondition -- a position book whose entries
were sized by a policy that never checked aggregate capital would encode the
same defect durably), M062/M064/M065 seal remediation (not a product
capability, and provably non-blocking here), scheduling (automating an
infeasible recommendation amplifies the defect), and observability.

## Delivered Capability

The daily research brief now carries a `SAME-DAY CAPITAL FEASIBILITY`
section, in both text and `--json`: the session's own approved position
plans, admitted in deterministic priority order (rank, then instrument
symbol) against one explicit capital policy, reporting exactly which plans
fit, which do not, and why. `--no-capital-feasibility` suppresses the
computation itself on both daily paths.

Zero new aggregate, **zero new PostgreSQL table, zero new migration**, zero
new repository, zero new I/O -- the inputs are rows the brief handler
already loads.

## Implementation Evidence

- **Source:** one new pure module,
  `decision_candidate/same_day_capital_feasibility.py`, plus an additive
  defaulted field on the M072 brief, rendering in both formats, and one CLI
  flag on each of the two daily entrypoints.
- **Reuse, not duplication:** M067's frozen `PortfolioCapitalPolicy` and
  `PortfolioRejectionReason` are imported. `PortfolioAllocationOutcome` is
  deliberately **not** reused -- its `ALLOCATED` member asserts capital *was
  allocated*, and M075 allocates nothing. M075 owns
  `FITS_WITHIN_CAPITAL` / `EXCEEDS_CAPITAL`, and a test enforces that
  `ALLOCATED` never appears in its vocabulary.
- **Tests:** 24 pure unit tests, 2 rendering tests, and 4 real-PostgreSQL
  integration tests that cross-check every verdict's notional, quantity and
  capital base against raw SQL with no repository helper in the path.

## Canonical Results

| Environment | Result |
|---|---|
| Full suite, PostgreSQL off | 1869 passed, 357 skipped |
| Full suite, PostgreSQL on | 2168 passed, 14 skipped |
| M075 unit + rendering | 26 passed |
| M075 PostgreSQL integration, pass 1 | 4 passed |
| M075 PostgreSQL integration, pass 2, new database | 4 passed |

**Regression measured against an identical baseline** -- same clone
semantics, same PostgreSQL instance, integration enabled:

| Head | Result |
|---|---|
| `master` `9b42759` | 24 failed, 2138 passed, 14 skipped, 44 errors |
| M075 branch | 24 failed, **2168 passed**, 14 skipped, 44 errors |

Identical failure and error counts; **+30 passing tests, exactly the 30 M075
adds. Zero regressions.** The 24/44 are the pre-existing M062/M064/M065 CRLF
seal debt, untouched here and invisible on the `windows-latest` CI runner.

## Genuine Defects Found and Fixed

1. **Capital base read from a field that does not exist.** The first
   implementation read `sizing.account_equity`; that attribute belongs to
   `PositionSizingContext`, not `PositionSizing`. `mypy` caught it before any
   test ran. Correct source is `PositionPlan.supplied_account_equity`, now
   asserted against raw SQL in the integration suite.
2. **Every withheld-verdict path raised `ValueError`.** M067's
   `PortfolioCapitalPolicy` rightly rejects a non-positive `initial_capital`,
   and the code constructed one anyway -- so "no approved plans", "zero
   equity" and "negative equity" all crashed instead of reporting honestly.
   Found by its own tests. Regression test added.
3. The brief's JSON section-inventory test, updated for the new section
   exactly as M074 did when it added its own.

## Adversarial Review

A pre-implementation design review of 24 attacks corrected 15 defects before
any code was written -- `None` ranks, duplicate-rank ties, the strict-`>`
ceiling boundary, the honesty of the outcome vocabulary, and the requirement
that absence never render as a pass.

`external-review/MILESTONE-075/hostile-review-matrix.md` records the
implementation pass: **89 attacks** across architecture, frozen-contract
preservation, determinism, capital arithmetic, data authority, the temporal
firewall, empty and malformed states, CLI, claim honesty, security and
packaging. Three genuine defects found and fixed; the rest held.

## Fresh Second Verification Pass

Same agent, so not an independent review. A brand-new database
(`m075_second_pass`) created empty, all migrations applied from scratch, the
M075 suite reproduced 4/4, and the central claim attacked from four
directions -- tightening only the ceiling over genuinely persisted rows,
suppression, double-build determinism, and raw-SQL cross-checking. It held in
every case.

## Temporal and State Semantics

This repository has no durable position state, and M075 does not create one.
M075 introduces `RECOMMENDATION_SET_FEASIBILITY_AT(t)`: a pure function of
one session's own approved plans plus one policy. It is distinct from
`STATE_AT(t)`, from `EVENT_AFTER(t)`, and from M074's
`HISTORICAL_EVIDENCE_AVAILABLE_AT(t)`. There is no future-data channel, no
cross-day channel, and no portfolio-state channel, because no such input
exists in the rule at all.

## Frozen Preservation

No M060, M062, M064, M065, M067 or M068 source file is modified. No
migration is added or changed. M074 and the M063 exceptional byte-seal
reconciliation record are untouched. The brief factory's new parameter is
keyword-only with a default, exactly M074's own additive pattern.

## M062 / M064 / M065 Seal Debt - Not Repaired

M075 introduces no fixture, no dataset bundle and no byte seal; its tests
construct typed domain objects in memory and it reads no file whose bytes are
hashed. The debt therefore does not block M075's capability, tests, CI, or
reproducibility, and was deliberately left alone. It continues to warrant its
own authorization.

## Claim Honesty

M075 makes no claim of profitability, live-trading readiness, broker
readiness, realistic execution, market representativeness, survivorship-bias
elimination, or investment advice. It is a `DIAGNOSTIC` over a
`RECOMMENDATION_SET`. The rendered banner -- not merely a document --
disclaims current portfolio state, open positions, prior-day exposure,
allocation or reservation of capital, execution, and profitability, and
states that the capital base is the operator-supplied equity figure rather
than a verified account balance.

## Owner Approval

All phases of the M075 mission specification are complete: repository truth
independently verified; a fresh 30-dimension capability matrix built from
source rather than milestone prose; the selected gap proven arithmetically
rather than asserted; five candidates ranked against eight criteria with
specific rejection reasons; a design that survived a 24-attack review with 15
pre-implementation corrections; implementation with zero new schema and zero
new I/O; 30 tests including real-PostgreSQL integration with raw-SQL
cross-verification; an 89-attack implementation review with three genuine
defects found and fixed; a fresh second pass on a new database; and a full
regression proving zero new failures against a measured baseline.

**Freeze declaration:** `M075 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M075 APPROVED_AND_FROZEN`.

## Deferred / M075 Boundary

Explicitly out of scope and not built: durable position state; open-position
tracking; cross-day exposure; cash ledger; margin; leverage; fills;
execution simulation in the daily path; P&L continuity; paper trading; live
trading; broker integration; scheduling; any new PostgreSQL table; any repair
of the M062/M064/M065 seal debt. **MILESTONE-076 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-076 -- recommendation only; not started as part of M075.
