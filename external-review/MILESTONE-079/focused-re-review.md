# M079 — Focused Re-Review After Corrections

Both corrections were re-attacked in their changed area only.

## R01 — silent position drop

| Re-attack | Result |
|---|---|
| Does every visible key still appear exactly once? | Yes — asserted for three keys by name |
| Can the new `AssertionError` fire on a legitimate input? | No — reachability re-analysed: `visible` is effective-filtered before grouping, so a grouped key always holds ≥1 eligible event |
| Did removing the branch change any existing result? | No — full unit suite re-run, 41 passed; all pre-existing assertions unchanged |
| Does the invariant failure now surface loudly? | Yes — it raises with the invariant named, instead of dropping a position |
| Did the entry ordering change? | No — sorting is unchanged and the determinism test still holds |
| Did counts drift? | No — the counts-agree-with-entries test still passes |

## R02 — design-review count overstated

| Re-attack | Result |
|---|---|
| Is the header count now computed from the file? | Yes — 81 attacks, 25 fixed, both counted programmatically |
| Were the added attacks padding? | No — sections I–K cover persistence/SQL, frozen-chain compatibility and test quality, none of which the original matrix touched, and four of them are marked FIXED with design consequences |
| Do any other M079 evidence documents overstate a count? | Checked: the implementation review's category totals sum to its stated 126 |

## Whole-suite confirmation after both corrections

| Suite | Result |
|---|---|
| M079 unit | 41 passed |
| M079 PostgreSQL | 11 passed |
| M079 second pass | 3 passed |
| M076–M079 chain | 69 passed |
| Full regression | identical failing-ID set to baseline |
