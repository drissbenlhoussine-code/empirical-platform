# M075 — FRESH SECOND VERIFICATION PASS

Same agent, so **not** an independent review. A genuinely fresh environment.

| Aspect | First pass | Second pass |
|---|---|---|
| Database | `empirical_platform` | **`m075_second_pass`**, created empty for this pass |
| Session governance ids | `RESEARCH-7501…7504` | same suite, new database, migrations applied from empty |
| Result | 4 passed | **4 passed** |

Every migration applied cleanly from an empty database, and the M075 suite reproduced
identically.

## Raw SQL, independent of repository helpers

The raw-SQL cross-check runs **inside** the tests, which is the only point at which the
seeded rows exist: the module-scoped fixture drops and recreates `public` on teardown, so
querying afterwards correctly returns nothing. Inside
`test_m075_assessment_is_computed_over_really_persisted_position_plans` the assessment's
every verdict is joined against

```sql
SELECT governance_id, supplied_account_equity, quantity, position_notional
FROM position_plan WHERE status = 'APPROVED_POSITION_PLAN' ORDER BY governance_id
```

and asserted field by field — notional, quantity, and the minimum equity — with no
repository helper in the path. This is what caught nothing new on the second pass, and
is what would have caught defect I-01 had `mypy` not caught it first.

## Attempt to disprove the central claim

The central claim is: *a session's approved plans are assessed against a capital policy,
and an infeasible set is reported as infeasible.* Attacked from four directions:

1. **Feed it real persisted rows and tighten only the ceiling** — the real set flips to
   `EXCEEDS_CAPITAL` with the correct per-plan reason.
   (`test_m075_exceeds_capital_is_reachable_from_real_persisted_rows`)
2. **Suppress it and check it does not read as a pass** — reports `computed: false`, not
   a feasible verdict.
3. **Build the same brief twice** — byte-identical assessments.
4. **Cross-check every number against raw SQL** — all match.

The claim held in every case.
