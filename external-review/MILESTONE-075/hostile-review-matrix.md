# M075 — PRIMARY-AGENT ADVERSARIAL IMPLEMENTATION REVIEW

This is my own attack on my own implementation. It is **not** an independent review.

Disposition: `PASS` held · `FIXED` genuine defect found and corrected here ·
`N/A_WITH_REASON` not applicable, with the reason stated.

## Genuine defects found and fixed

**I-01 — `PositionSizing` has no `account_equity`.** The first implementation read the
capital base from `sizing.account_equity`. That attribute belongs to
`PositionSizingContext`, not `PositionSizing`; the correct source is
`PositionPlan.supplied_account_equity`. Caught by `mypy` before any test ran. Every
capital base would have been wrong — in fact the module would not have run at all.
**FIXED**, and the correct field is now asserted against raw SQL in the integration test.

**I-02 — non-positive capital base crashed instead of reporting.** `capital_policy_for_session`
called `dataclasses.replace(..., initial_capital=0)`, and M067's `PortfolioCapitalPolicy`
correctly rejects a non-positive `initial_capital` with `ValueError`. Every
withheld-verdict path — no approved plans, zero equity, negative equity — raised instead
of returning an honest "not assessable". Found by my own tests, not by inspection.
**FIXED**: the template policy supplies reporting metadata when no valid capital base
exists, and no invalid policy object is ever constructed. Regression test:
`test_zero_capital_base_reports_policy_identity_without_constructing_it`.

**I-03 — the brief's JSON section inventory test.** Adding a section legitimately changed
the brief's section set. Updated to include `SAME_DAY_CAPITAL_FEASIBILITY`, exactly as
M074 did when it added its own section. **FIXED** (test truth updated, not weakened).

## Matrix

### Architecture and frozen-contract preservation

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 01 | M075 adds a new table | none | no migration file added; `changed-files.txt` | PASS |
| 02 | M075 adds a migration | none | `git diff --name-status … migrations/` empty | PASS |
| 03 | M075 mutates M067 source | zero bytes | import only; M067 not in changed files | PASS |
| 04 | M075 mutates M060 source | zero bytes | not in changed files | PASS |
| 05 | M075 mutates M064/M065 fixtures | zero bytes | not in changed files | PASS |
| 06 | Frozen brief factory signature broken | additive only | new param is keyword-only with default `None` | PASS |
| 07 | Frozen `DailyResearchBrief` field order broken | additive only | new field appended with default | PASS |
| 08 | `usecases` imports `shared.persistence` | forbidden | architecture checker exit 0 | PASS |
| 09 | Domain module imports persistence/sqlalchemy/psycopg/boto3 | forbidden | imports are stdlib + domain only | PASS |
| 10 | Domain module performs I/O | forbidden | no open/read/network/DB call in the module | PASS |
| 11 | Negative architecture fixture stops reporting | must still fail | checker exit 1 | PASS |
| 12 | A parallel sizing/risk/ranking engine is introduced | none | no new policy math; M060 output consumed verbatim | PASS |
| 13 | M067 logic duplicated | none | `PortfolioCapitalPolicy` + reason enum imported, not re-implemented | PASS |
| 14 | New repository or protocol added | none | none added | PASS |
| 15 | New I/O in the brief handler | none | assessment computed from already-fetched rows | PASS |

### Determinism and ordering

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 16 | `rank=None` crashes sorting | sorts last | `test_unranked_plans_sort_after_ranked_plans` | PASS |
| 17 | Duplicate ranks order arbitrarily | symbol tiebreak | `test_duplicate_ranks_are_broken_deterministically_by_symbol` | PASS |
| 18 | Result depends on input order | must not | `test_result_is_independent_of_input_order` | PASS |
| 19 | Result varies between runs | must not | `test_repeated_assessment_is_deterministic` | PASS |
| 20 | Dict insertion order leaks in | must not | requests built from `target.decisions`, not the dict | PASS |
| 21 | Set iteration order leaks in | must not | the only set is `{equities}`, consumed by `min()` and `sorted()` | PASS |
| 22 | Two independent brief builds differ | must not | integration `…deterministic_across_two_independent_builds` | PASS |
| 23 | Verdict order differs from admission order | must match | verdicts appended in the sorted loop | PASS |

### Capital arithmetic

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 24 | Float creeps into money | never | `test_every_monetary_output_is_an_exact_decimal_string_not_a_float` | PASS |
| 25 | Exact-ceiling set wrongly rejected | must fit | `test_four_plans_landing_exactly_on_the_ceiling_are_feasible` | PASS |
| 26 | One cent over is admitted | must not | `test_one_cent_over_the_ceiling_does_not_fit` | PASS |
| 27 | The 5×25% defect is not detected | must be | `test_five_plans_each_at_the_m060_notional_cap_exceed_capital` | PASS |
| 28 | Concurrency cap ignored when capital remains | must reject | `test_concurrency_cap_rejects_the_eleventh_plan…` | PASS |
| 29 | Concurrency cap invented by M075 | must be M067's | `test_policy_reuses_the_frozen_m067_limits…` | PASS |
| 30 | Rejected plan consumes capital | must not | `test_cumulative_committed_notional_only_advances_on_admitted_plans` | PASS |
| 31 | A large plan starves later smaller plans | documented choice | `test_a_plan_that_does_not_fit_does_not_block_a_later_smaller_plan` | PASS |
| 32 | `rejection_reason` set on a fitting plan | never | `test_rejection_reason_is_set_if_and_only_if_a_plan_does_not_fit` | PASS |
| 33 | Rounding drift across many plans | none | Decimal accumulation, no intermediate rounding | PASS |
| 34 | Utilisation percent divides by zero | guarded | `ceiling > 0` guard, else `None` | PASS |
| 35 | REJECTED position plans consume capital | must not | only `APPROVED_POSITION_PLAN` produces a request | PASS |

### Data authority and lineage

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 36 | Notional invented rather than read | read verbatim | integration cross-checks every verdict against raw SQL | PASS |
| 37 | Quantity invented | read verbatim | same raw-SQL cross-check | PASS |
| 38 | Capital base invented | read verbatim | raw SQL `min(supplied_account_equity)` asserted | PASS |
| 39 | Wrong equity field used | correct field | I-01, fixed and asserted against raw SQL | FIXED |
| 40 | Plan attributed to the wrong position plan id | must not | verdict carries `position_plan_governance_id`, joined in raw SQL | PASS |
| 41 | Plans from another session leak in | must not | requests derive only from `target.decisions` | PASS |
| 42 | Inconsistent equity averaged | must not | `test_inconsistent_equity_uses_the_minimum_and_says_so` | PASS |
| 43 | Inconsistent equity silently hidden | must be named | same test asserts the limitation text | PASS |

### Temporal firewall

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 44 | Future bars influence the verdict | impossible | the rule takes no market data at all | PASS |
| 45 | Future universe membership leaks | impossible | no membership input | PASS |
| 46 | Future corporate actions leak | impossible | no corporate-action input | PASS |
| 47 | Prior-day positions silently assumed | must be disclosed | banner states it; `test_banner_disclaims…` | PASS |
| 48 | Cross-day contamination | impossible | no cross-session input | PASS |
| 49 | `as_of` misused | not used | the rule has no date input | N/A_WITH_REASON — no temporal input exists |
| 50 | Timezone assumption | none made | no datetime in the rule | N/A_WITH_REASON — no datetime input exists |
| 51 | Future portfolio state leaks | impossible | no portfolio-state input exists anywhere in the repo | PASS |

### Empty, malformed and failure states

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 52 | Zero approved plans renders as feasible | must not | `test_no_approved_plans_is_its_own_outcome_not_a_pass` | PASS |
| 53 | Incomplete session gets a confident verdict | withheld | `test_incomplete_session_withholds_a_verdict` | PASS |
| 54 | Zero equity yields nonsense | withheld | `test_non_positive_equity_withholds_a_verdict[0]` | PASS |
| 55 | Negative equity yields nonsense | withheld | `…[-1]` | PASS |
| 56 | Zero notional silently dropped | named | `test_non_positive_notional_is_excluded_and_named[0]` | PASS |
| 57 | Negative notional silently dropped | named | `…[-100]` | PASS |
| 58 | Approved plan without sizing crashes | excluded | `_capital_request_from` returns `None` | PASS |
| 59 | Withheld verdict loses policy identity | must report it | I-02 regression test | FIXED |
| 60 | Suppressed assessment reads as feasible | must not | `test_m075_suppressed_assessment_is_not_reported_as_feasible` | PASS |
| 61 | Suppression indistinguishable from empty | distinct | `None` vs `NO_APPROVED_POSITION_PLANS`; both tested | PASS |
| 62 | Exception in the rule breaks the whole brief | rule is total | no raise path; all branches return | PASS |

### CLI and rendering

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 63 | JSON and text disagree | must agree | both render one computed object; parity test | PASS |
| 64 | `--no-capital-feasibility` ignored | honoured | integration suppression test | PASS |
| 65 | Flag suppresses rendering only, not the work | suppresses the work | handler skips `assess_…` entirely | PASS |
| 66 | Flag leaks into positional args | filtered | positional filter excludes it | PASS |
| 67 | Unknown flag silently accepted | rejected | workflow parser raises `SystemExit(_USAGE)` | PASS |
| 68 | Usage strings not updated | updated | both entrypoints' `_USAGE` name the flag | PASS |
| 69 | JSON section missing from inventory | present | inventory test updated and passing | FIXED |
| 70 | Text section missing | present | `SAME-DAY CAPITAL FEASIBILITY` asserted | PASS |
| 71 | Money rendered as float in JSON | strings only | every monetary field is `str` | PASS |
| 72 | Banner omitted from either rendering | present in both | both include `CAPITAL_FEASIBILITY_BANNER` | PASS |

### Claim honesty

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 73 | Vocabulary implies capital was allocated | must not | `test_outcome_vocabulary_never_claims_an_allocation_occurred` | PASS |
| 74 | Reads as current portfolio state | disclaimed | banner test | PASS |
| 75 | Reads as open positions | disclaimed | banner test | PASS |
| 76 | Reads as execution | disclaimed | banner test | PASS |
| 77 | Reads as a profitability claim | disclaimed | banner test | PASS |
| 78 | Capital base implied to be a real balance | disclaimed | banner test asserts the exact clause | PASS |
| 79 | Forbidden vocabulary appears | none | `claim-honesty.md`; grep of the module | PASS |

### Security, packaging, portability

| # | Attack | Expected | Evidence | Disposition |
|---|---|---|---|---|
| 80 | Secret introduced | none | secret scan 0 findings | PASS |
| 81 | SQL injection via new query | no new SQL | M075 issues no SQL of its own | N/A_WITH_REASON — no query added |
| 82 | Dependency added | none | `pyproject.toml` unchanged | PASS |
| 83 | Vulnerable dependency pulled in | none | `pip-audit` clean | PASS |
| 84 | Build breaks | must not | `python -m build` produces sdist + wheel | PASS |
| 85 | Installed package cannot import the module | must import | wheel smoke import | PASS |
| 86 | M075 introduces a byte seal / CRLF exposure | none | no fixture, no hashed file | PASS |
| 87 | M075 depends on worktree-dependent bytes | none | inputs are typed objects from PostgreSQL | PASS |
| 88 | New failures introduced anywhere | none | master 24F/44E vs branch 24F/44E, +30 passed | PASS |
| 89 | Coverage floor lowered to pass | not lowered | 79% floor unchanged in `pyproject.toml` | PASS |
