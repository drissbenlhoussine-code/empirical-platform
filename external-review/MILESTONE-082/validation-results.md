# MILESTONE-082 — Validation Results (closure candidate)

Executed at the commit containing this file. Actual head and CI run ids are
recorded in the closure report and the PR body after push.

The active authority these gates defend is
[`current-authority.md`](current-authority.md), generated from
[`current-authority.json`](current-authority.json).

## Structural authority gates

| Gate | Result |
|---|---|
| canonical contract validates against the committed schema | pass |
| `proves` is exactly the approved 3-identifier set | pass |
| `does_not_prove` is exactly the approved 7-identifier set | pass |
| unknown claim identifier rejected by the closed schema | pass |
| `render_m082_authority.py --check` — document is byte-exact | pass |
| runtime text and JSON expose no authority beyond the contract | pass |
| runtime text and JSON mutually consistent | pass |
| manifest classifies every M082 document exactly once | pass |
| every historical file carries the historical-record notice | pass |
| no historical file imported by production or the renderer | pass |
| no active file contains a retired annotation token | pass |
| no active validation interprets English prose | pass |

## Test suites

Collection counts, not only pass counts.

| Suite | Collected | Result |
|---|---|---|
| M082 unit | 40 | 40 passed |
| M082 PostgreSQL lifecycle | see closure report | all passed |
| M082 fresh second pass | 4 | 4 passed |
| M082 authority contract suite | see closure report | all passed |
| M076–M082 compatibility chain | — | all passed |

## Repository gates

`compileall` · `ruff format --check` · `ruff check` · `mypy` · architecture
checker · negative architecture fixture · dependency audit · secret scan ·
wheel build · clean-environment wheel import · console entry point ·
`git diff --check` · migration up/down/up · changed-files exact comparison ·
clean tree.

Exact numbers, the PostgreSQL-on and PostgreSQL-off regression comparison and
the failing-ID differences are in
[`owner-final-closure-candidate.md`](owner-final-closure-candidate.md).

## Preservation

`migrations/` byte-identical. Production behaviour unchanged, proven by
docstring-stripped AST comparison and by evaluating the emitted runtime values.
`PROJECT_CHECKPOINT.md` unchanged; `LATEST_FROZEN_MILESTONE=MILESTONE-081`.
M076 production, M079, M080 and M081 untouched. No migration, no new table, no
new receipt authority, M083 not started.
