# MILESTONE-085 — Alpaca Paper Execution with Exact Human Approval

> Current temporal correction: see [temporal-correction.md](temporal-correction.md).
> The ten-second lead workaround described below is superseded. Earlier test counts
> and market-open results below are historical evidence, not validation of this correction.
>
> **Superseded again:** the persisted broker time basis described there was neither
> simultaneous nor of the right provenance. See *"SUPERSEDED AGAIN"* in
> `temporal-correction.md`. Intents must now be issued with
> `empirical-platform-issue-paper-bound-order-intent` to be dispatchable, so the operator
> CLI is 13 console scripts, not 12. Counts below are historical.
>
> **Superseded a third time:** the intent-time basis translated deadlines written
> earlier, when the proposal was evaluated and approved. See *"SUPERSEDED A THIRD TIME"*
> in `temporal-correction.md`. Every deadline now carries the basis of the act that
> wrote it: proposals must be evaluated with
> `empirical-platform-prepare-paper-bound-trade-proposal` and approved with
> `empirical-platform-decide-paper-bound-trade-proposal` to be issuable for Paper, so the
> operator CLI is 15 console scripts. The affected mutation families are in
> `provenance-mutation-matrix.md`.
>
> **Corrected again (corrective pass):** send-time limits are no longer command
> arguments; they are the stored configuration's, bound into the authorization and
> re-derived at send. Uncertain broker answers are `SUBMISSION_UNKNOWN`, terminal
> attempts are immutable, the liquidation deadline is never extended by host skew,
> the database must be at exactly `9c4b2e7d5a18`, and `--dry-run` is refused. See
> [corrective-pass.md](corrective-pass.md). The run-3 matrix is kept as
> `mutation-matrix-run3.md`; every count and table below is historical.
>
> **Corrected again (identity safety, 2026-09-25):** the corrective pass became commit
> `b24c471` and was verified (PostgreSQL 430/430, 51/51 + 9/9 mutations). Its review found
> F1: Alpaca's duplicate-`client_order_id` 422 was a terminal REJECTED, losing awareness of
> an order the broker holds under our identity. Now: 422 is classified semantically, the
> identity is looked up before any send, an existing order is adopted only when it equals
> the authorized order field by field, a mismatch is a recorded collision, and nothing is
> ever sent again. The Owner ratified the post-freeze M084 commit `1127134` and the
> frozen-path guard now covers M084 as well as M083. See
> [identity-collision-correction.md](identity-collision-correction.md).
>
> **Final candidate `2726f6f` (2026-09-26):** published to PR #15; exact-SHA local
> verification, exact-head CI, the non-green full PostgreSQL baseline (5104 passed / 3 failed /
> 43 errors / 16 skipped, all documented non-M085), 134/134 mutations, environment findings
> A1–A5 and the focused pre-Paper review (A6 slow-identity-lookup defect — HIGH, blocks Paper
> acceptance; B adoption gap) are recorded in
> [final-candidate-2726f6f/README.md](final-candidate-2726f6f/README.md). Paper acceptance
> NOT_STARTED.
>
> **Send-boundary and identity-recovery correction (2026-09-26):** A6 is fixed — the identity
> lookup and every slow read complete before the kill switch is re-read, time is sampled after
> them, `final_send_refusal` re-validates on that evidence, and nothing sits between the
> decision and the POST (a *bounded application send boundary*, not control over the broker).
> One canonical order-terms contract (incl. `limit_price`, `time_in_force`, `extended_hours`,
> bound `broker_order_id`, verified account) serves acknowledgement, observation and
> reconciliation; observing an order under our identity is separated from attributing it
> (lineage required); an inconclusive pre-send lookup is recoverable uncertainty; refusal is a
> documented (status, code) pair. Defects were reproduced on `2726f6f` first. Code candidate
> `00716e4`; exact-SHA verification (661 focused, 253 PostgreSQL + 71 authority-contract,
> 4034 non-PostgreSQL / 80.37 %, 109/109 executed mutation families — 39 unchanged families not
> rerun with justification, all static gates) in
> [send-boundary-correction/verification.md](send-boundary-correction/verification.md); design and
> defect log in [send-boundary-correction/README.md](send-boundary-correction/README.md). Not
> pushed; Owner publication approval required. Paper acceptance NOT_STARTED.


**Status: corrected candidate pending Owner review. NOT approved, NOT frozen, NOT merged.**

The Owner-authorized market-open attempt on 2026-09-10 dispatched nothing: it found
FIND-P7-01, a product defect that refused every fresh quote in an open market. It is
corrected here and stops for review; the market-open exercise is outstanding. See
`validation-results.md`, pass 7.

## What this milestone establishes, in one sentence

A persisted MILESTONE-084 approved order intent may be dispatched to the Alpaca
**paper** environment **exactly once**, and only after a fresh, explicit, expiring,
single-use human authorization has been bound to the exact immutable order-intent
fingerprint, the exact paper account identity and the exact broker request.

That sentence is the whole authority. It is stated machine-readably in
`current-authority.json` against a closed schema, and everything else in this
package either explains it or measures it.

## What it does NOT establish

Stated first, because this is the part a reviewer is most likely to be told
implicitly by an enthusiastic report:

- **Not** that a paper acknowledgement is a real-market execution.
- **Not** that a paper fill predicts a live fill.
- **Not** profitability, expected return, fillability or execution quality.
- **Not** eligibility for, or readiness for, a live Alpaca account.
- **Not** Owner approval of anything. This package requests review; it does not
  record a decision.
- **Not** a completed external submission. Both attempts were **measured BLOCKED**
  with zero orders — the second by a defect this candidate corrects — and
  `paper-acceptance-results.md` records the open-market one.

## Reading order

A reviewer wanting to disbelieve this milestone efficiently should read in this
order:

| # | Document | What it is for |
|---|---|---|
| 1 | `exhaustion-table.md` | 31 required items, each **derived** from re-read evidence rather than asserted. Start here: it is the only document that cannot be edited into passing. |
| 2 | `validation-results.md` | Every gate, its exit code, the four-mode regression, and the findings that were corrected during the milestone. |
| 3 | `current-authority.md` | The authority contract, rendered from `current-authority.json`. `--check` proves the two agree. |
| 4 | `scope-and-design.md` | Why each refusal sits where it does. The design decisions, including the ones that were wrong first. |
| 5 | `hostile-review.md` | Five independent adversarial passes over the candidate, and what each found. |
| 6 | `paper-acceptance-results.md` | The bounded external run against the real paper endpoint, and its BLOCKED outcome. |
| 7 | `mutation-matrix.md` | 41 mutation families, each proved to be DETECTED by a test. Anti-vacuity for the whole suite. |
| 8 | `hostile-http-results.md` | 102 attacks through the real adapter over a real socket. |
| 9 | `concurrency-results.md` | 16 races on three independently rebuilt schemas. |
| 10 | `operator-walkthrough.md` | 30 steps against an **installed wheel**, against declared exit codes. |
| 11 | `performance-results.md` | Measured query plans, and the one index a measurement asked for. |
| 12 | `alpaca-contract-evidence.md` | What the broker's own documentation does and does not establish, classified. |
| 13 | `changed-files.txt` | The exact diff surface, generated from the real diff. |

## The three claims worth checking hardest

If review time is limited, these are where a serious defect would hide.

**1. Exactly-once is a constraint, not a retry policy.** `client_order_id` is
*derived* from persisted identity by a pure function, and the dispatch claim —
consuming the authorization and inserting the attempt — commits in one transaction
**before** any network request, with the UPDATE conditional on `consumed_at IS
NULL`. The loser of that race receives the persisted winner rather than an
exception, because a caller handed an error is a caller that may retry. Alpaca's
own duplicate protection is deliberately **not** relied on: its `client_order_id`
uniqueness applies only while an order is ACTIVE.

**2. Ambiguity is a state, not an error.** A timeout after the request may have
been delivered becomes `SUBMISSION_UNKNOWN`, whose closed transition table has
edges to every real outcome and **no edge back into submission**. A 404 from
reconciliation is not treated as proof that nothing was sent; the bounded policy
requiring two consecutive not-found observations and 60 seconds is a stated,
reviewable *choice*, not a proof.

**3. The credential boundary.** Credentials are read in exactly one module,
`entrypoints/_paper_composition.py`, handed straight to a type whose `repr` is
redacted, and never returned, logged, stored, or passed to a domain type,
repository or renderer. `tests/unit/test_m085_paper_composition.py` asserts that
containment rather than describing it, including that a hostile server echoing an
auth header into its response body does not get the key written into an audit row —
which was a **real defect found by writing that attack**.

## Where the evidence lives in the repository

| Layer | Path |
|---|---|
| Domain | `src/empirical_platform/decision_candidate/paper_execution.py` |
| Adapter | `src/empirical_platform/shared/brokerage/alpaca_paper.py` |
| Persistence | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` |
| Schema | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` |
| Application | `src/empirical_platform/usecases/paper_execution.py`, `paper_execution_io.py` |
| Composition | `src/empirical_platform/entrypoints/_paper_composition.py` |
| Operator CLI | 12 console scripts, listed in `pyproject.toml` |

Tests: `tests/unit/test_m085_*.py`, `tests/integration/test_m085_*.py`.
Campaign tools: `tools/m085_*.py`, `tools/render_m085_*.py`.

## Regenerating this package

Every generated document has a `--check` mode that fails if the document and its
source disagree. Nothing here is hand-maintained prose claiming a number.

```
python tools/render_m085_authority.py --check
python tools/render_m085_exhaustion_table.py --check
```
