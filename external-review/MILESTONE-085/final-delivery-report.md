# MILESTONE-085 — Final Delivery Report

**Alpaca Paper Execution with Exact Human Approval**

Branch `feature/m085-alpaca-paper-human-approved-execution`, based on required
`master` `a224076754fb38909ee04c2464e50e51df12d7ad`.

**Terminal status**

| Milestone | Status |
|---|---|
| MILESTONE-083 | APPROVED_AND_FROZEN |
| MILESTONE-084 | APPROVED_AND_FROZEN |
| MILESTONE-085 | FINAL_EXHAUSTED_PAPER_EXECUTION_CANDIDATE_PENDING_OWNER_REVIEW |
| MILESTONE-086 | NOT_STARTED |
| Pull request | **OPEN / NOT MERGED** |

---

## A. What was asked, and what was delivered

The narrow product authority this milestone was permitted to establish, and the only
one it does establish:

> A persisted MILESTONE-084 approved order intent may be dispatched exactly once to
> the Alpaca Paper environment only after a fresh, explicit, expiring, single-use
> human authorization is bound to the exact immutable order-intent fingerprint, the
> exact Paper account identity and the exact broker request.

That sentence is stated once, machine-readably, in `current-authority.json` against
a closed generated schema, rendered deterministically to `current-authority.md`, and
proved bijective against the runtime and the domain by 51 contract tests.

## B. The flow, and where each refusal sits

```
 M084 intent (NOT_SUBMITTED, never rewritten)
      │
      ▼
 preview ──── refreshes account, clock, asset, position, quote, kill switch
      │       and freezes exactly what a human will be shown
      ▼
 human authorization ──── one fingerprint, one account, one client_order_id,
      │                   expiring, single-use, append-only
      ▼
 claim ──── consumed + attempt inserted in ONE transaction, BEFORE any network
      │
      ▼
 submit ──── one request, one derived client_order_id
      │
      ├── answered            → PAPER_SUBMITTED, then the broker's status
      ├── definitely not sent → REJECTED, no reconciliation needed
      └── maybe sent          → SUBMISSION_UNKNOWN, resolved only by asking
                                about the SAME client_order_id
```

## C. The three decisions that carry the milestone

**Exactly-once is a constraint, not a retry policy.** `client_order_id` is *derived*
from persisted identity by a pure function, so a retry, a crash, a second worker and
a reconciliation all compute the same value and address the same broker order. The
claim commits **before** the network — consumed authorization and inserted attempt in
one transaction, with the UPDATE conditional on `consumed_at IS NULL`. The loser of
that race receives the persisted **winner**, not an exception, because a caller
handed an error is a caller that may retry. Alpaca's own duplicate protection is
deliberately not relied on: its `client_order_id` uniqueness applies only while the
first order is ACTIVE, so the broker is not a durable exactly-once authority. The
database is.

**Ambiguity is a state, not an error.** `http.client` is used rather than an SDK or
`urllib` precisely because it separates connecting, sending and reading, and that
separation is what makes DEFINITELY-NOT-SENT and MAYBE-SENT *observable* rather than
guessed. A timeout after delivery becomes `SUBMISSION_UNKNOWN`, whose closed
transition table has edges to every real outcome and **no edge back into
submission**.

**The forbidden things are unrepresentable, not merely refused.**
`PaperOrderRequest` cannot express a sell, a fractional quantity, extended hours, or
a time in force other than DAY. `quantity` is an `int`, which removes Alpaca's
fractional-order rules from the reachable surface entirely — and that mattered,
because two official Alpaca pages **disagree** about whether fractional limit orders
are permitted. `PaperEnvironment` has exactly one member; a declared `LIVE` would be
a value code could branch on.

## D. Long-only is a property of this product, not of the account

The real paper account reports `multiplier=4` and `shorting_enabled=true`. It
**permits** leverage and short selling. Any design assuming the account would refuse
them would have rested on nothing. The refusals are therefore local: the request
type, and a `side = 'BUY'` CHECK in the migration.

## E. Two hosts, one of which can place an order

The trading adapter is pinned to `paper-api.alpaca.markets`; quotes come from a
separate read-only client pinned to `data.alpaca.markets`. The order path has exactly
one reachable hostname — the trading client refuses even the legitimate data host.
Redirects are refused, never followed: a followed cross-host redirect is exactly how
a paper-authorized request would arrive at a live endpoint carrying these
credentials.

## F. The credential boundary

Credentials come only from `EMPIRICAL_ALPACA_PAPER_API_KEY`,
`EMPIRICAL_ALPACA_PAPER_SECRET_KEY` and `EMPIRICAL_ALPACA_PAPER_BASE_URL`, and are
read in exactly one module — `entrypoints/_paper_composition.py`. They are handed
straight to a type whose `repr` is redacted and never returned, logged, stored,
serialized, or passed to a domain type, repository or renderer.

- No credential is in source, a migration, a fixture, a snapshot, an exception, an
  HTTP recording, a generated report, a commit, PR text or CI configuration.
- Authentication headers are redacted before any diagnostic output.
- Nothing is persisted in PostgreSQL; nothing was copied into a project `.env`.
- `EMPIRICAL_ALPACA_PAPER_BASE_URL` is **parsed and proved**, not trusted: the
  variable's name contains the word PAPER, and this milestone does not treat a name
  as evidence about a value. Nine hostile values, including the live trading host,
  are refused by test.
- The endpoint contacted was the Paper endpoint only. **No live endpoint was ever
  contacted.**

The containment is asserted rather than described — including that a hostile server
echoing a request header into its response body does not get the key written into a
durable audit row, which was a **real defect found by writing that attack**
(FIND-P3-01).

## G. What was built

| Layer | Path |
|---|---|
| Domain | `decision_candidate/paper_execution.py` |
| Adapter | `shared/brokerage/alpaca_paper.py` |
| Persistence | `shared/persistence/postgres_repositories/paper_execution_repositories.py` |
| Schema | `migrations/versions/b1e9d47c30a5_...py` — 7 tables, 14 triggers, 5 pinned functions |
| Application | `usecases/paper_execution.py`, `usecases/paper_execution_io.py` |
| Composition | `entrypoints/_paper_composition.py` |
| Operator CLI | 12 console scripts |

Every rule is enforced twice on purpose: the domain refusal is the legible one a
developer meets first; the database refusal still applies to a `psql` session or a
repository written in a hurry. The transition table exists in the domain and in a
trigger, and a test walks **every ordered pair of states** comparing them so the
copies cannot drift.

## H. Referential integrity by trigger, not by foreign key

The link to M084's `approved_order_intent` is a BEFORE INSERT trigger. A foreign key
was the first choice and was **wrong**: PostgreSQL refuses to TRUNCATE a referenced
table, M084's fixture truncates exactly that table, and four foreign keys turned 97
M084 tests into errors (FIND-P2-01). The insert-time guarantee is identical; what is
given up — protection against the parent being TRUNCATEd afterwards, which requires
table ownership — is stated in the trigger's own comment and in the authority
limitations.

This is not hypothetical. The 43 pre-existing mode-2 errors on `master` are M083
suffering precisely this defect today. M084 had hit the same shape against M083 and
accepted it; repeating that would mean every milestone breaking the one before it.

## I. Campaign results

| Campaign | Result |
|---|---|
| Domain unit tests | 78 passed |
| PostgreSQL integration | 54 passed, raw-SQL attacks on the database layer |
| Concurrency | 49 passed — 16 races × 3 independently rebuilt schemas, barriers not sleeps |
| Hostile HTTP | 102 passed — real socket, real adapter, host pinning preserved |
| Authority contract | 51 passed — bijection of contract, runtime and domain |
| Mutation (anti-vacuity) | **40 of 40 families detected**, SHA-256 restoration verified |
| Installed-wheel walkthrough | 30 steps, **0 off their declared exit code** |
| Performance | measured plans; one index added because a measurement asked for it |
| Pass-6 closing tests | 210 added — handlers, 12 CLI surfaces, composition, base pin |

## J. The bounded external paper submission — MEASURED BLOCKED

**It was not completed, and nothing here pretends it was.** The market was closed;
the only available quote was 12,487 s old against a 60 s freshness tolerance; the
AAPL ask was `0`; limit/bid was `0.0133`.

**No safety control was relaxed to get past it.** The notional ceiling was not
raised, the order type was not changed to market, the freshness tolerance was **not
widened**, and no cheaper asset was substituted. The exhaustion table's item 12
passes only because the refusals are recorded; it verifies the words "was not
widened" and "not raised" appear, so "blocked" cannot hide a shortcut.

## K. Validation

Full detail in `validation-results.md`. Headline:

- **PostgreSQL OFF (what CI runs): 3468 passed, 0 failures, 0 errors, coverage 79.82 %** against
  the `fail_under = 79` floor, which was **not lowered**.
- **Baseline comparison: no new failure or error id**, in either mode, compared by
  test IDENTITY rather than by count.
- One baseline failure is **fixed**: the M084 file-audit test, i.e. FIND-F-01.
- Mode 2 retains 3 failures and 43 errors that are **pre-existing on `master`**,
  unchanged in count and identity, belonging to M082 and M083. M085 does not fix
  them and does not claim to.

## L. Findings

**Twenty-three numbered findings, every one found by executing something.** Passes 1–5 are in
`hostile-review.md`; the closing pass 6 is in `validation-results.md`. The four most
consequential:

- **FIND-P2-01** — four foreign keys broke M084's fixture (97 errors). Replaced with
  a trigger.
- **FIND-P3-01** — a header-echoing peer would have written the key into a durable
  audit row. Found by writing the attack, not by reading the code.
- **FIND-P6-01** — with PostgreSQL OFF, coverage was 76.22 % against the 79.0 floor:
  the entire operator-facing surface was unexercised in the environment that gates
  the merge. Closed with 210 real tests, floor untouched.
- **FIND-P6-02** — the exhaustion table's base-commit pin held a one-character
  transcription error, and the gate reported it indistinguishably from a genuinely
  wrong base. A gate that cannot tell "you are on the wrong base" from "I cannot read
  my own pin" is not a gate. Corrected and pinned by 13 tests.

**Two findings are recorded and deliberately NOT corrected**, because correcting them
would exceed the authorized surface: FIND-F-03 (`tools/m084_hostile_passes.py` does
not compare the file-audit matrix) and FIND-F-04
(`tools/m084_operator_walkthrough.sh` hardcodes a POSIX interpreter path).

## M. Owner-authorized M084 corrections, kept separate

Two narrowly bounded corrections were made inside one administrative commit
(`1127134`), under explicit Owner authorization, and are kept explicitly separate
from M085 in all validation evidence:

- **FIND-F-01** — the M084 file-audit matrix was computed against a *moving* HEAD, so
  moving HEAD changed the recorded matrix. Now pinned to the approved tree, with
  `EXIT_RANGE_UNAVAILABLE = 3` for an unavailable range.
- **FIND-F-02** — the M084 audit/exhaustion tooling hardcoded `.venv313/bin/python`
  and a POSIX-only PATH. Now uses `sys.executable`, refuses an incompatible
  interpreter **loudly** via `SUPPORTED_PYTHON`, and uses `os.pathsep`. Twenty tests,
  including positive and negative interpreter cases.

The four required properties were proved: the pinned approved-tree matrix is
byte-identical; moving HEAD no longer changes it; mutating a pinned-tree expectation
is detected; and the M084 audit checks run from Windows. **No recorded M084 claim,
result or product behaviour changed**, and no M084 production, migration, authority
or freeze-record file, no `PROJECT_CHECKPOINT.md`, and no M083 file was touched.

## N. Scope discipline

- **No M083-owned path changed.** Verified by the exhaustion table and by
  `tools/check_frozen_paths.py` (27 governed paths, by blob id and by diff).
- **No unauthorized M084 path changed.** Only the six paths the Owner authorized.
- **`PROJECT_CHECKPOINT.md` is not in the diff.**
- **No M086 path exists.** M086 was not started, scoped or designed.

## O. The preserved M063 work

An unrelated uncommitted M063 edit was preserved recoverably under the Owner's
instruction, before any M085 work began.

| Item | Value |
|---|---|
| Path | `MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md` |
| Stash name | `pre-m085-preserved-m063-uncommitted-work` |
| **Stash commit** | **`06c291ca93217d93477d42f8bf9c58e048dcac56`** |
| Patch verification | PATCH_MATCH=TRUE against the recorded diff |
| Content | 1 file changed, 21 insertions, 6 deletions |

It was never popped, dropped or rewritten; it does **not** appear in the PR diff
(verified against the base…HEAD diff); and it was neither committed nor modified. It
remains recoverable at the commit above.

## P. Forbidden actions — none taken

| Forbidden | Status |
|---|---|
| Merge the M085 PR | **not merged** — PR is open |
| Freeze M085 | not frozen |
| Modify `PROJECT_CHECKPOINT.md` | untouched, not in the diff |
| Start / scope / design M086 | not started; no M086 path exists |
| Create or request live credentials | none created or requested |
| Open or fund a live account | not done |
| Accept broker agreements or subscriptions | not done |
| Contact customer support or a broker representative | not done |
| Submit a live order | **no live order was submitted** |
| Use a live-data or live-order endpoint | **never contacted** |
| Enable unattended or scheduled execution | not enabled; every dispatch requires a fresh human authorization |
| Approval by default or automatic approval | impossible — refusal is the default; permission comes only from an `ExecutionAuthorization` a person created |

## Q. Claims NOT made

Stated as flatly as possible, because these are the claims a reader is most likely to
infer from an enthusiastic report:

- **No** Owner approval is claimed. This package requests review; it records no
  decision.
- **No** profitability, expected return, fillability or execution-quality claim.
- **No** claim that a Paper fill predicts a live fill.
- **No** claim that a paper acknowledgement is a real-market execution.
- **No** claim of live-trading readiness or eligibility for a live account.
- **No** claim that Alpaca behaves as the local hostile server did — those 102
  attacks establish what the *adapter* does when a peer misbehaves.
- **No** claim of TLS certificate validation (the transport is redirected to a plain
  local socket in those tests).
- **No** claim about behaviour under production load; 16 races with 2–4 threads is
  not a load test.

## R. Stated limitations

- Row-level refusals do not cover TRUNCATE, DROP, a disabled trigger or a superuser.
  Two tests **execute** those holes rather than describing them.
- The quote feed is IEX only, not the consolidated tape.
- The request fingerprint is a change detector, not a cryptographic seal.
- A rejected or expired dispatch cannot be retried in this milestone: exactly one
  attempt may exist per intent, so a new attempt needs a new M084 intent. Deliberate,
  and the safe direction to err in.
- An unmapped broker status leaves the state unchanged and requires an operator to
  look. Five real Alpaca statuses are deliberately unmapped.
- The 404-based reconciliation policy (two consecutive not-found observations and 60
  seconds) is a stated, reviewable **choice**, not a proof.

## S. Deliverable

**Exactly one pull request** to `master`, titled
`M085 - Alpaca Paper Execution with Exact Human Approval`, whose body ends with
`DO NOT MERGE WITHOUT OWNER APPROVAL.`

Thirteen commits, each coherent. The final row carries no abbreviated hash because it is the commit that contains this report, and a report cannot state its own commit's identity without invalidating it:

| Commit | Subject |
|---|---|
| `1127134` | `fix(m084): pin the derived audit to the approved tree, and let it run anywhere` |
| `a4e4074` | `feat(m085): the paper-execution core -- one authorization, one dispatch` |
| `99392e4` | `fix(m085): link to M084 by trigger, not by foreign key, so M084 still truncates` |
| `ab5e780` | `feat(m085): the application layer, twelve operator commands, and the hostile peer` |
| `47a7103` | `test(m085): the concurrency campaign -- barriers, not sleeps, three rebuilt schemas` |
| `e715163` | `feat(m085): the bounded paper acceptance harness, and its measured blocker` |
| `d14275d` | `feat(m085): the closed authority contract, its renderer, and the bijection tests` |
| `662884f` | `test(m085): the mutation campaign -- 40 of 40 families detected, and 3 real gaps closed` |
| `c9be6d2` | `fix(m085): the walkthrough found two defects; the wheel run is 30/30 on expectation` |
| `0c6455c` | `fix(m085): clear the secret-scan gate without adding an exemption` |
| `3fbea05` | `fix(m085): the CI failure, and an index the measurement asked for` |
| `e44d78d` | `test(m085): close the PostgreSQL-OFF coverage gap, and two gates that could not fail` |
| *(this one)* | `docs(m085): the review package, and the evidence each document is derived from` |

`git log --oneline a224076754fb..HEAD` on the branch gives the exact sequence.

## T. How to review this efficiently

`external-review/MILESTONE-085/README.md` gives the full reading order. The short
version: start with `exhaustion-table.md`, because it is the only document that
cannot be edited into passing — every row re-reads the artefact it describes or
re-runs the gate. Then `validation-results.md` for the gates and the findings.

## U. Recommendation

M085 is submitted as a **candidate for Owner review**. It is not approved, not
frozen, and must not be merged without Owner approval.

The one thing a reviewer should weigh most carefully is **section J**: the bounded
external submission was measured BLOCKED, so the end-to-end dispatch path has been
proved against a real hostile socket, a real database and a real installed wheel —
but not against a real accepted Paper order. That gap is real, it is stated in every
document that touches it, and the correct response to it is a re-run when the market
is open, not a widened tolerance.
