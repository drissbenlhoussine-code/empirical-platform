# MILESTONE-079 — Operator Evidence Availability Snapshot — External Review Package

`M079 IMPLEMENTED_AND_REVIEWED_CANDIDATE_PENDING_OWNER_REVIEW`

**DO NOT MERGE WITHOUT OWNER APPROVAL.**

| Document | What it holds |
|---|---|
| `scope-and-design-snapshot.md` | Repository authority, the proved gap, six ranked candidates, the two-dimension temporal model, non-goals |
| `hostile-design-review.md` | 81 pre-implementation attacks; 25 defects fixed before any code |
| `hostile-implementation-review.md` | 126 attacks against the real code; **2 defects found by execution** |
| `focused-re-review.md` | Both corrections re-attacked in their changed area |
| `fresh-second-verification-pass.md` | Empty database, different inputs, reversed insertion order |
| `validation-results.md` | Regression against a measured baseline, gates, PostgreSQL evidence |
| `known-limitations.md` | What this milestone cannot tell you |
| `reality-gate.md` | Which question it answers, and how misreadings are prevented structurally |
| `owner-review-checklist.md` | Repository-checkable items for the owner |
| `changed-files.txt` | Every file added or modified |

## The short version

M076 persists **two** timestamps on every operator assertion: `event_timestamp`
(when the operator says it happened) and `recorded_at` (when it was written
down). Only the first drives the fold. **`recorded_at` is never filtered on,
ordered on, or read by any derivation anywhere in the repository.**

So M078's frozen limitation was exact: the platform is effective-time only, and
must not be used for calibration or forward evaluation "without a `recorded_at`
/ evidence-availability firewall". **That firewall did not exist.**

M079 is it. Given an effective cutoff `E` and a knowledge cutoff `K`, it reports
the position state derivable from exactly those assertions that were effective
by `E` **and recorded by `K`**.

Two things are worth reading before the rest:

- **M079 applies only the knowledge filter** and hands the survivors to M076's
  own fold, which applies the effective filter. It adds one dimension and
  delegates the other; M076 is not modified and not re-implemented.
- **An incomplete knowledge prefix is not corruption.** A close whose opening
  was recorded later makes the fold refuse — and calling that corrupt data
  would be a false diagnosis. The two are told apart by re-folding the key
  unfiltered, not by wording.
