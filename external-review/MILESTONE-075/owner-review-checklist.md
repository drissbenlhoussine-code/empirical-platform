# M075 — Owner Review Checklist

1. **Is the gap real?** `grep -n "sum(\|total_notional" src/empirical_platform/usecases/build_daily_research_brief.py`
   on `master` returns nothing. Five plans at M060's own 25% cap commit 125% of equity.
2. **No new table or migration?** `git diff --name-status origin/master..HEAD -- migrations/`
   must be empty.
3. **No frozen milestone touched?** `changed-files.txt` must contain no M060/M062/M064/
   M065/M067/M068 source file.
4. **Additive only?** the new brief field and factory parameter both default, exactly as
   M074's did.
5. **Honest vocabulary?** M075 must never say `ALLOCATED`. A test enforces this.
6. **Regression is genuinely clean?** master `24 failed / 44 errors / 2138 passed`;
   branch `24 failed / 44 errors / 2168 passed`. Same failures, +30 tests.
7. **Are the remaining failures pre-existing?** yes — the M062/M064/M065 CRLF debt,
   untouched by this branch, invisible on the `windows-latest` CI runner.
8. **Does the brief still render on a session with no approved plans?** yes, as a distinct
   empty state, never as a pass.

Owner decision requested: **approve M075 for Owner Freeze, or return it with findings.**
