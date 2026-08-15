# M077 — Owner Review Correction Pass

Owner review of PR #7 at head `0678522546f8f01d0051b50f00a2a4a001cd2290` returned
one blocking correctness finding. **It was real.** This records what changed.

## Finding — capital-base authority was destroyed by the double-counting filter

`assess_portfolio_aware_capital_feasibility` removed already-acted plans from
`usable` **before** deriving the capital base from `usable`. Two different
questions were conflated:

- *which plans are new proposals?* — already-acted plans must be removed
- *what equity did this session size against?* — already-acted plans are still
  approved plans of this session and still carry its equity figure

Because the same list answered both, a session whose plans had **all** been
acted upon produced `capital_base = 0`, and therefore `capital_ceiling = 0`,
`remaining_capital_under_policy = 0` and `projected_utilization = null` — none
of which is what the session recorded. The held snapshot could not be judged
against anything.

### Correction

Validity is now checked first, then every valid approved plan enters
`capital_inputs`; already-acted plans are additionally kept out of `proposed`.

- already-acted plans **remain capital-authority inputs**
- already-acted plans **contribute zero new proposed notional**, because the
  exposure they produced is already in the held snapshot
- M075's minimum-equity rule is preserved and now applies across **every** valid
  approved plan, acted upon or not
- a plan with a non-positive equity is **not** a capital authority, acted upon
  or not — it is bad data first

### Ordering change worth naming

The already-acted check previously ran *before* notional/equity validation. It
now runs *after*, so an invalid plan is reported as bad data rather than as
"already acted upon". That is the more accurate of the two descriptions.

## Honesty of the all-acted wording — a second, related defect

With the capital base repaired, the outcome for a fully-acted session was still
`NO_APPROVED_POSITION_PLANS`. **That is a false statement about a session that
did approve plans**; the operator had simply already acted on all of them.

A new closed-vocabulary member, `ALL_PLANS_ALREADY_ACTED_UPON`, now carries that
case, and `NO_APPROVED_POSITION_PLANS` is reserved for a session that genuinely
approved none. Both directions are tested. The distinction reaches the human
rendering, not only the JSON.

The member is honest by the same standard as the rest of M077's vocabulary: it
asserts only that plans exist and are cited by open **operator-asserted**
positions. It claims no execution, no fill and no verification.

## Retraction

**Attack C02 of the hostile design review is retracted.** It asked whether the
lineage exclusion silently drops a plan and was dispositioned `FIXED` on the
grounds that excluded plans are "reported with an explicit reason, never
omitted". That was true of the *limitations text* and false of the *arithmetic*:
the plan was dropped from capital-base derivation as well, which no limitation
line disclosed. The reason a reader would not have caught it is that the review
checked the reporting and never checked the capital base — the attack was
narrower than the defect it was supposed to cover.

`hostile-design-review.md` and `hostile-implementation-review.md` are left
otherwise intact, with the retraction recorded in place rather than edited away.

## Tests added

| Test | Guards |
|---|---|
| `test_all_plans_already_acted_keeps_the_session_capital_base` | the finding itself |
| `test_all_plans_already_acted_is_not_reported_as_no_approved_plans` | wording honesty |
| `test_genuinely_no_plans_still_reports_no_approved_position_plans` | the distinction cuts both ways |
| `test_an_acted_plan_with_the_smaller_equity_still_sets_the_capital_base` | M075 minimum-equity semantics, acted side |
| `test_a_new_plan_with_the_smaller_equity_still_sets_the_capital_base` | M075 minimum-equity semantics, new side |
| `test_an_acted_plan_with_invalid_equity_is_not_a_capital_authority` | invalid equity is bad data first |
| `test_every_plan_invalid_remains_not_assessable` | withholding preserved |
| `test_acted_plans_contribute_zero_new_proposed_notional` | no second charge for one decision |
| `test_capital_base_derivation_is_deterministic_regardless_of_input_order` | determinism of the new path |
| `test_m077_all_plans_acted_keeps_capital_base_over_real_rows` | the finding, through PostgreSQL |
| `test_m077_all_plans_acted_text_and_json_agree` | text/JSON parity of the new outcome |

Each fails against the pre-correction implementation.
