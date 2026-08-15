# MILESTONE-077 — Portfolio-Aware Capital Feasibility — External Review Package

`M077 IMPLEMENTED_AND_REVIEWED_CANDIDATE_PENDING_OWNER_REVIEW`

**DO NOT MERGE WITHOUT OWNER APPROVAL.**

| Document | What it holds |
|---|---|
| `scope-and-design-snapshot.md` | Repository truth, the tested hypothesis, the eight-candidate ranking, architecture, semantics, non-goals |
| `hostile-design-review.md` | 71 pre-implementation attacks; 9 defects fixed before any code was written |
| `hostile-implementation-review.md` | 106 attacks against the real code; **4 genuine defects found by execution and fixed** |
| `validation-results.md` | Regression against a measured baseline, gates, PostgreSQL evidence |
| `known-limitations.md` | What this milestone does not claim |
| `reality-gate.md` | Questions newly answerable, and what remains unclaimed |
| `changed-files.txt` | Every file added or modified |

## The short version

M075 judged today's plans with the portfolio deliberately excluded. M076
recorded what the operator asserts they hold. **Nothing connected them**, so a
session could report "fits within capital" to an operator whose capital was
already fully deployed.

M077 is a new, additive, read-only artifact that charges already-asserted
exposure against today's proposals under the same explicit policy. It modifies
neither M075 nor M076, adds no table and no migration, and states plainly that
every held figure is an operator assertion rather than a broker fact.
