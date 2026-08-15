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

---

# Owner review correction — focused re-review

The correction was re-attacked in its changed area only.

## Removing the discriminator

| Re-attack | Result |
|---|---|
| Can any code path still read an event with `recorded_at > K`? | No — `_snapshot_from_known_evidence` is not given the unfiltered tuple, and a test asserts its signature and source |
| Does `build_operator_evidence_snapshot` read `events` more than once? | No — exactly once, through `events_known_by` |
| Did any surviving field keep a dependence on the full ledger? | No — `total_event_count` and `excluded_by_knowledge_cutoff` were the only two and both are gone |
| Is `excluded_by_effective_cutoff` still safe? | Yes — computed as `len(known) - len(visible)`, both derived from the filtered set |
| Does `rejection_reason` leak? | No — taken only from the filtered fold; the unfiltered attempt no longer exists |
| Does the ordering depend on anything post-cutoff? | No — entries come from `visible` only; asserted by a test with a future row that would sort first |
| Do the limitations depend on anything post-cutoff? | No — the hidden-assertion count is gone; asserted by a test |

## Not over-correcting

| Re-attack | Result |
|---|---|
| Was a legitimate distinction thrown away? | The `INCOMPLETE` vs `INCOHERENT` distinction was never knowable at `K`. What *is* knowable — which frozen rule the visible evidence broke — is still reported as `rejection_reason`, and a test asserts two differently-broken keys keep distinct reasons under the shared status |
| Did the fix break the healthy path? | No — `KNOWN_OPEN` / `KNOWN_CLOSED` behaviour is unchanged; the full unit suite still passes |
| Did temporal evolution break? | No — advancing `K` past a backfill still folds normally, and a test asserts the earlier answer is not retroactively strengthened |
| Can a sequence stay unresolved forever? | Yes, legitimately — named test |
| Is M076 affected? | No — zero frozen files touched; a test asserts M076 still sees what M079 hides |

## Whole-suite confirmation after the correction

| Suite | Result |
|---|---|
| M079 unit | **57 passed** (41 before, 16 added for this correction) |
| M079 PostgreSQL integration | **14 passed** (11 before, 3 added, including the two-database proof) |
| M079 fresh second pass | **4 passed** (3 before, 1 added) |
| M076–M079 focused compatibility chain | **290 passed** |
| Full regression | failing-ID set identical to the `5945e4e` baseline |
