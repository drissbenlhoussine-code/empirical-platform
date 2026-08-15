# MILESTONE-078 — Research Decision Follow-Through Audit — External Review Package

`M078 IMPLEMENTED_AND_REVIEWED_CANDIDATE_PENDING_OWNER_REVIEW`

**DO NOT MERGE WITHOUT OWNER APPROVAL.**

| Document | What it holds |
|---|---|
| `scope-and-design-snapshot.md` | Repository truth, a documented contradiction in the frozen record, the proved gap, five ranked candidates, semantics, non-goals |
| `hostile-design-review.md` | 79 pre-implementation attacks; 22 defects fixed before any code |
| `hostile-implementation-review.md` | 104 attacks against the real code; **3 defects found by execution**, with R02's disposition retracted in place |
| `owner-correction-pass.md` | The owner finding on join-authority identity, why the first correction was insufficient, and what PostgreSQL actually permits |
| `validation-results.md` | Regression against a measured baseline, gates, PostgreSQL evidence |
| `known-limitations.md` | What this milestone cannot tell you |
| `reality-gate.md` | What it proves, what it does not, and how misreadings are prevented structurally |
| `changed-files.txt` | Every file added or modified |

## The short version

M076 records what the operator asserts they hold. M077 charges that exposure
against today's proposals. **Neither closes the loop back to the research.**
Plan lineage existed and was used for exactly one thing — suppressing double
counting, over open positions, for today's session only.

So no one could ask: *what became of what my research recommended, and what am
I holding that it never proposed?*

M078 answers that, and nothing more. It emits **no monetary value of any
kind**, so it cannot accidentally become a P&L, a valuation or a profitability
claim. Its most important word is `NO_ASSERTED_POSITION_RECORDED` — which means
nothing was written down, and explicitly **not** that the operator did nothing.

Two boundaries are worth reading before the rest:

- **The join authority is validated as an identity.** A blank plan id, or one
  id naming two instruments, withholds the entire audit as
  `SESSION_PLAN_REFERENCES_INCOHERENT`. No arbitrary winner is ever audited.
- **This is an EFFECTIVE-TIME audit, not a point-in-time one.** A later
  backfilled assertion can change the answer for an earlier `as_of`, so M078
  must not be used as calibration or forward-evaluation evidence without a
  `recorded_at` firewall. See `known-limitations.md` item 11.
