# MILESTONE-085 — Alpaca Paper Execution with Exact Human Approval

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
