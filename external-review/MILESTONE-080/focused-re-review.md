# M080 — Focused Re-Review After Corrections

The single correction was re-attacked in its changed area only.

## R01 — the result line's coverage

| Re-attack | Result |
|---|---|
| Do the three statuses now produce three distinct lines? | Yes — asserted by `test_the_three_coverage_phrasings_are_distinct` |
| Does the fully-exited line still read cleanly? | Yes — `on all 10 exited unit(s)` |
| Does the partial line name what it excludes? | Yes — `6 still open and NOT covered` |
| Does the unreconciled line deny being the whole result? | Yes — `NOT the whole position's result` |
| Did the change alter any computed value? | No — rendering only; every arithmetic assertion unchanged |
| Did the change alter the JSON? | No — JSON already carried the structured quantities beside the result |
| Does the renderer still import cleanly under `mypy`? | Yes — one added import of `RoundTripStatus` |
| Do the four regression tests fail against the pre-fix renderer? | Yes — that is what makes them regression tests |
| Did any existing test change meaning to accommodate the fix? | No — the four are additions |

## The test correction

| Re-attack | Result |
|---|---|
| Was the original assertion wrong, or the renderer? | The assertion — it matched the report title line |
| Is the corrected assertion now anchored? | Yes — `line.startswith("      ASSERTED ROUND-TRIP RESULT")` |
| Could it match the title again? | No — the title is not indented |
| Are there other unanchored substring assertions in the suite? | Audited; the remaining `in` assertions target phrases that appear in exactly one place, and the two forbidden-token tests deliberately scan every surface |

## Whole-suite confirmation after the correction

| Suite | Result |
|---|---|
| M080 unit | 58 passed |
| M080 PostgreSQL integration | 12 passed |
| M080 second pass | 4 passed |
| M076–M080 chain | 364 passed |
| Full regression | failing-ID set identical to the `0e73e0b` baseline |
