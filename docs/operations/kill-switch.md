# Kill switch semantics (v1 Personal Paper release)

## What changed, and why

Before the v1 release, `KillSwitchState.ENGAGED` blocked both new entries AND every
exit action (authorize, submit, and the console's confirm step), across all three
check sites in `usecases/position_exit.py` and the console's
`usecases/operator_console_exits.py::confirm`.

The v1 release changes this deliberately, per the release mission's own explicit
instruction ("Kill switch MUST block: new entries. It must NOT silently trap an
already-open position"): **the kill switch now blocks new entries only.** It no
longer blocks any position-reducing exit.

## Exact current behavior

- **Entries**: `KillSwitchState.ENGAGED` still blocks proposal approval/confirmation
  and entry preview/authorize/submit, unchanged, in `usecases/paper_execution.py`.
- **Exits**: `KillSwitchState.ENGAGED` no longer blocks exit preview, authorize,
  submit, or the console's confirm action, in `usecases/position_exit.py` and
  `usecases/operator_console_exits.py`. This applies identically to a manual
  Owner-confirmed exit and an automatic stop/target/mandatory-liquidation exit
  (Release Blocker 4) — both reuse the same `AuthorizePositionExitHandler` /
  `SubmitAuthorizedPositionExitHandler` chain.
- The kill switch's engaged/disengaged state is still **displayed** on exit review
  pages and the Safety page (`kill_switch_engaged` field) — only its ENFORCEMENT
  against exits was removed, not its visibility.

## Why this is safe (bounded-risk-reduction doctrine)

The kill switch exists to stop the system from taking on MORE risk, not to stop it
from reducing risk it already took on. An engaged kill switch that also freezes an
open position would force an unattended position to ride through its stop, its
target, and its mandatory liquidation deadline with no exit path — the opposite of
"bounded risk." Resolving the ambiguity in favor of risk reduction (per the release
mission's own instruction) means: the kill switch can always be engaged to stop
anything NEW from happening, and it can never be used, intentionally or
accidentally, to trap an existing position past its approved exit terms.

The kill switch still cannot be used to authorize anything broader than what was
already approved — it has no code path that increases quantity, widens a stop,
moves a target, or creates a short; disengaging it does not relax any of those
bounds either. It is purely a new-entry gate.

## Tests

- `tests/unit/test_m087_position_exit_service.py::test_the_kill_switch_engaged_after_the_review_does_not_block_the_confirmation`
  — the engaged kill switch does not block confirming a manual exit.
- `tests/unit/test_v1_kill_switch_semantics.py` — entry-blocked / exit-not-blocked
  matrix, including the automatic position-plan manager.
