# MILESTONE-077 - Portfolio-Aware Capital Feasibility - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M077 baseline
`e05cb2fae0544bb7f427bb686e9a37522f3936ad` (the M076 Owner Freeze
hash-recording HEAD; M076 fully `APPROVED_AND_FROZEN`), independently
re-verified from git at mission start rather than taken from the mission
text. Delivered through pull request #7, owner-approved at head
`0559a20960c9b5fd6fa2009e0a94e44c76a03fae` with the `foundation` workflow
green on that exact SHA, and merged into `master` as
`525e3e30503833c02dc9c1436da5f9cb2b559fa9`.

The pull request was merged with a true merge commit. **Both commits are
preserved and neither was squashed away:** the implementation
`0678522546f8f01d0051b50f00a2a4a001cd2290` and the owner correction
`0559a20960c9b5fd6fa2009e0a94e44c76a03fae`.

Scope, the tested hypothesis, capability analysis, an eight-candidate ranking,
architecture, semantics, non-goals and the pre-implementation adversarial
design review are recorded in
`MILESTONE_077_PORTFOLIO_AWARE_CAPITAL_FEASIBILITY_SCOPE_AND_DESIGN.md`.

## Why M077 Exists

The mission proposed that after M076 the daily path still could not judge
today's proposals *after* accounting for already-held operator-asserted
exposure. **The hypothesis was attacked rather than accepted, and it survived
structurally.**

A search over `src/` for every M076 symbol returned consumers in exactly three
places: M076's own two usecases, its own two CLI entrypoints, and the
persistence runtime that constructs the repository. **No other module in the
repository imported the ledger.** `build_daily_research_brief.py` did not
reference it. `same_day_capital_feasibility.py` imported only M067.

So M075 could report **"fits within capital"** to an operator whose capital was
already fully deployed, and say nothing about why that was wrong.

## Why a New Artifact Rather Than Wiring M076 Into M075

M075's own **rendered banner** states it is "NOT current portfolio state; NOT
open positions; NOT prior-day exposure". Feeding held exposure into M075 would
have made its own banner false. **The additive design is forced by that, not
chosen for convenience.** M075 and M076 source are both untouched.

## Candidate Selection

Eight candidates were ranked against six criteria. Portfolio-aware capital
feasibility scored 26; session-to-position lineage 23; operational exposure
summary 21; decision-versus-outcome evaluation 21; data-freshness authority
20; forward/paper observation 18; realized/unrealized observation 16; an M068
concentration guard 13.

Decision-versus-outcome evaluation carries the highest scientific value of any
candidate and was rejected as **premature**: it requires an outcome, which
requires either market revaluation or realized proceeds, and M076 asserts
neither. Building it now would have forced a fabricated valuation. **M077 is
its precondition.** The M068 guard was rejected because it would convert
*historical* dependence evidence into an operational control.

## The Central Boundary

An approved `PositionPlan` is a recommendation, not an action. Held exposure
comes solely from explicit operator assertions, never from plans.

## Delivered Capability

A new, additive, read-only decision artifact. Given a completed session's
approved position plans **and** the positions the operator has asserted are
open as of that session's `as_of`, the daily brief reports which of today's
plans remain feasible once already-asserted exposure is charged against the
same explicit capital policy -- in both text and JSON, with
`--no-portfolio-aware-feasibility` on both daily paths.

## What the Held Figure Is

Held exposure is quantity times the operator's **asserted entry price**, taken
from M076's fold and **never revalued** -- not by a later reduction's cited
price, not by anything else.

It is **not** a market valuation, **not** a verified cost basis, **not** a
broker balance, and **not** a current value.

## Utilization, Not Depletion

Charging held notional against the capital base does not claim the operator's
cash went down. Buying an asset converts cash into that asset and leaves equity
unchanged. M067's model is **utilization** -- `max_capital_utilization_percent`
measures how much of the capital base is *deployed* -- and a held asserted
position is deployed capital. The distinction is stated because the figure is
otherwise easy to misread as a cash balance.

## Implementation Evidence

- **Source:** one new pure, I/O-free module,
  `decision_candidate/portfolio_aware_capital_feasibility.py`, plus an additive
  keyword-defaulted field on the M072 brief, rendering in both formats, an
  optional repository and suppression flag on the handler, and one CLI flag on
  each of the two daily entrypoints.
- **Zero new PostgreSQL table, zero new migration, zero new repository.**
- **Read-only with respect to M076:** the ledger is read through its existing
  contract and the pure `derive_position_state()`; nothing is appended.
- **M076 is not modified to expose lineage.** `DerivedPosition` does not carry
  `source_position_plan_governance_id`, and rather than change a frozen
  structure, M077 projects the lineage from the same event tuple it already
  read. It does not re-implement M076's fold, which remains the sole authority
  on what is open.
- **Tests:** 53 pure unit tests and 17 real-PostgreSQL integration tests.

## Double Counting

An operator may assert a position **citing one of today's own plans**. Counting
both the held position and the same plan as proposed would charge one decision
twice. A plan cited by an open asserted position is therefore excluded from the
proposed set exactly once and named in `plans_already_acted_upon`. A plan cited
by a **closed** position is *not* excluded, because that position released its
exposure and re-entering is legitimate.

## Owner Review Correction

Owner review of `0678522` returned **one blocking correctness finding. It was
real.** The detailed record is
`external-review/MILESTONE-077/owner-correction-pass.md`.

### Capital-base authority was destroyed by the double-counting filter

The filter removed already-acted plans from `usable` **before** the capital base
was derived from `usable`, so one list answered two different questions:

- which plans are *new proposals*? -- already-acted plans must be removed
- what equity did this session *size against*? -- already-acted plans are still
  approved plans of this session and still carry its equity figure

A session whose plans had **all** been acted upon therefore reported a capital
base of zero, and with it a zero ceiling, zero remaining capital and a null
utilisation. None of that is what the session recorded, and the held snapshot
could not be judged against anything.

**Corrected:** `capital_inputs` is now separate from `proposed`. Validity is
checked **first**, so a plan with a non-positive equity is bad data and is never
a capital authority, acted upon or not. Every valid approved plan enters
`capital_inputs`; already-acted valid plans **remain capital-authority inputs**
and **contribute zero new proposed notional**, because the exposure they
produced is already in the held snapshot. M075's minimum-equity rule is
preserved and now spans every valid approved plan.

The already-acted check now runs *after* validation rather than before, so an
invalid plan is reported as bad data rather than as "already acted upon" -- the
more accurate of the two descriptions.

### A second, related defect: the wording

With the capital base repaired, a fully-acted session still reported
`NO_APPROVED_POSITION_PLANS`. **That is a false statement about a session that
did approve plans**; the operator had simply already acted on all of them. The
new closed-vocabulary member `ALL_PLANS_ALREADY_ACTED_UPON` carries that case,
and `NO_APPROVED_POSITION_PLANS` is reserved for a session that approved none.
Both directions are tested, and the distinction reaches the human rendering
rather than only the JSON.

### Retraction

**Design-review attack C02 is retracted in place.** It asked whether the lineage
exclusion silently drops a plan and was dispositioned `FIXED` because excluded
plans are "reported with an explicit reason, never omitted". That was true of
the limitations *text* and false of the *arithmetic*: the plan was dropped from
capital-base derivation as well, which no limitation line disclosed. The attack
checked the reporting and never checked the capital base, so it was narrower
than the defect it was meant to cover. It is struck through in the matrix rather
than edited away.

## Canonical Results

| Environment | Result |
|---|---|
| M077 unit | 53 passed |
| M077 PostgreSQL integration | 17 passed |
| M077 focused total | 70 passed |
| M077 PostgreSQL, fresh second pass, new database | 4 passed |

**Regression measured against an identical baseline** -- same working tree, same
PostgreSQL instance, integration enabled:

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `e05cb2f` | 8 failed, 1922 passed, 12 errors | 24 failed, 2237 passed, 44 errors |
| M077 branch | 8 failed, **1975** passed, 12 errors | 24 failed, **2311** passed, 44 errors |

Identical failure and error counts, and **zero regressions**. The claim does not
rest on the counts: the sorted failing-test-id lists were **diffed and are
identical**, so no test that passed on the baseline fails here and no failure was
swapped for another. No M075, M076 or M077 test appears in the failing set. The
8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF seal
debt, untouched here and invisible on the `windows-latest` CI runner.

**No gate was suppressed to go green.** The module carries zero `type: ignore`
and zero `noqa`. An early draft carried both; both were removed by restructuring
the code rather than by silencing the checker.

## Adversarial Review

A pre-implementation hostile design review of **71 attacks** corrected nine
defects before a line of code was written, including the sharpest: charging held
notional against equity reads as double counting unless utilisation is
distinguished from depletion. It also rejected a first design that would have
added a field to M076's frozen `DerivedPosition`.

The implementation pass catalogued **106 attacks** and found **four genuine
defects, each confirmed by executing the code rather than reading it**:
input-order-dependent assessments (twice, from one root cause); a quantised
ceiling that made a boundary plan feasible under M075 and infeasible under M077
over identical inputs; and a blank persisted plan citation treated as an
identifier. Each is fixed with a regression test that fails against the pre-fix
code.

One of those is worth recording plainly: the existing determinism test passed
only because it had no already-acted plans -- **the test was weaker than the
claim it defended.**

## Fresh Second Verification Pass

Same agent, so not an independent review. A brand-new database created empty,
the full migration chain applied from scratch, and deliberately different inputs
throughout -- different governance ids, different symbols, a shifted breakout
fixture placing the event on a different day, a different `as_of`, different
quantities, prices carrying six decimal places, and a different capital base:
4/4.

## Concurrency

M077 reads while M076 may be writing. `list_all()` is a single `SELECT` inside
one transaction, so under PostgreSQL's default `READ COMMITTED` it observes one
consistent snapshot taken at statement start; M076 commits each position's event
atomically under a per-position advisory lock. **No additional locking is
required, and adding any would be unjustified.** This is proven by a real
barrier-synchronised writer/reader race, not asserted.

## Temporal Semantics

M077 introduces `PORTFOLIO_AWARE_FEASIBILITY_AT(t)`: a pure function of this
session's approved plans, the operator ledger folded at `t`, and one capital
policy. Inclusive `as_of` is inherited from M076 unchanged; events after `as_of`
are excluded by M076's own filter and their count is surfaced; `recorded_at`
never participates. Distinct from `STATE_AT(t)`, `EVENT_AFTER(t)`, M074's
`HISTORICAL_EVIDENCE_AVAILABLE_AT(t)`, M075's
`RECOMMENDATION_SET_FEASIBILITY_AT(t)` and M076's
`OPERATOR_ASSERTED_POSITION_STATE_AT(t)`.

## Frozen Preservation

No M057-M076 source file's semantics change. MILESTONE-075 and MILESTONE-076 are
neither modified nor re-interpreted -- M077 reads M076 only through its existing
contract. MILESTONE-074 and the M063 exceptional byte-seal reconciliation record
are untouched. No migration is added or changed.

## M062 / M064 / M065 Seal Debt - Not Repaired

M077 introduces no fixture, no dataset bundle and no byte seal; its tests
construct typed domain objects in memory and it reads no file whose bytes are
hashed. The debt therefore does not block M077's capability, tests, CI, or
reproducibility, and was deliberately left alone. It continues to warrant its
own authorization.

## Claim Honesty

M077 makes no claim of profitability, live-trading readiness, broker readiness,
order execution, fills, market valuation, realized or unrealized P&L, or
investment advice. Held exposure is what the operator **asserted**, not what a
broker confirmed: there is no broker, no confirmation and no reconciliation.
Vocabulary is restricted to `ASSERTED` / `PROPOSED` / `FITS` / `EXCEEDS` /
`WITHHELD`, and a parametrised test asserts that `EXECUTED`, `FILLED`,
`VERIFIED`, `ALLOCATED` and `MARKET_VALUE` appear nowhere in the vocabulary. The
rendered banner -- not merely a document -- denies broker verification, current
market pricing, execution evidence, a verified account balance, market
valuation, P&L, allocation or reservation of capital, profitability and advice.

## Owner Approval

All phases of the M077 mission specification are complete: repository truth
independently verified; the proposed gap attacked rather than assumed and proved
structurally; eight candidates ranked with specific rejection reasons; a design
that survived 71 attacks with nine pre-implementation corrections; a minimal
additive implementation with zero new schema; 70 focused tests including real
PostgreSQL evidence cross-checked against raw SQL; a 106-attack implementation
review that found four real defects by execution; a fresh second pass on a new
database with deliberately different inputs; a full regression proving zero new
failures against a measured baseline; and **one owner review pass that found a
real capital-base-authority defect, corrected architecturally and recorded
rather than tidied away.**

**Freeze declaration:** `M077 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M077 APPROVED_AND_FROZEN`.

## Deferred / M077 Boundary

Explicitly out of scope and not built: market revaluation; realized or
unrealized P&L; decision-versus-outcome evaluation; broker integration or
reconciliation; execution or fills; paper trading; cash ledger; margin;
leverage; per-instrument concentration control; operational use of M067/M068
historical evidence; cross-day trend reporting; modification of M075 or M076;
any new PostgreSQL table or migration; any repair of the M062/M064/M065 seal
debt. **MILESTONE-078 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-078 -- recommendation only; not started as part of M077.
