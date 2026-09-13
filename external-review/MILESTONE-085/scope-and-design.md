# MILESTONE-085 — Scope and Design

> Current temporal correction: see [temporal-correction.md](temporal-correction.md).
> The ten-second lead workaround described below is superseded. Earlier test counts
> and market-open results below are historical evidence, not validation of this correction.


## What this milestone establishes, and nothing more

A persisted MILESTONE-084 approved order intent may be dispatched to the Alpaca
**paper** environment **exactly once**, and only after a fresh, explicit, expiring,
single-use human authorization has been bound to the exact immutable order-intent
fingerprint, the exact paper account identity and the exact broker request.

The full authority is stated once, machine-readably, in `current-authority.json`
against a closed schema, and rendered to `current-authority.md`. This document
explains **why each refusal sits where it does**; it is not a second statement of
authority and deliberately makes no claim the contract does not.

## The shape of the flow

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
      ├── answered        → PAPER_SUBMITTED, then the broker's status
      ├── definitely not sent → REJECTED, no reconciliation needed
      └── maybe sent      → SUBMISSION_UNKNOWN, resolved only by asking about
                            the SAME client_order_id
```

## The decisions that matter, and why

### The M084 intent is read, never rewritten

M084 fixes `submission_state` at `NOT_SUBMITTED`, provides no transition away from
it, and enforces that with a CHECK, an append-only trigger and a package-wide import
deny-list. M085 does not add a transition. Execution state lives in M085's own tables
keyed by the intent's governance identity, so the row a human approved is unchanged
after a dispatch — proved by
`test_the_approved_intent_is_still_not_submitted_after_a_dispatch`.

**`account_mode_required` stays `PREPARATION`, and that is not permission.** M084 pins
that field precisely so an intent cannot declare itself ready for an account. Reading
it as a green light would be reading M084's refusal as its opposite. Permission comes
from one place only: an `ExecutionAuthorization` a person created.

### No broker SDK, and therefore no weakening of M084's gate

M084 forbade every module of the package from importing a client that can place,
modify or cancel an order. M085 adds the paper-order capability and that rule is
**unchanged** — because the adapter imports no SDK. It uses `http.client`.

`http.client` rather than `urllib.request` because it separates connecting, sending
and reading into three calls, and that separation is what makes the
DEFINITELY-NOT-SENT / MAYBE-SENT distinction **observable** rather than guessed. An
SDK would decide for us what a base URL means, whether to follow a redirect, how long
to wait and what to retry — four decisions a milestone about reaching one host once
cannot delegate.

### Exactly-once is a constraint, not a retry policy

`client_order_id` is **derived** from persisted identity by a pure function, so a
retry, a crash, a second worker and a reconciliation all compute the same value and
address the same broker order. A random id would make a retry after an ambiguous
timeout create a SECOND order, which is the single worst failure this milestone
exists to prevent.

The claim is committed **before** the network: consumed authorization and inserted
attempt in one transaction, with the UPDATE conditional on `consumed_at IS NULL`. The
loser of that race receives the persisted **winner**, not an exception, because a
caller handed an error is a caller that may retry.

**Alpaca's own duplicate protection is deliberately not relied on.** Its
`client_order_id` uniqueness applies only while the first order is ACTIVE, so once an
order reaches a terminal state the id could be reused. The broker is therefore not a
durable exactly-once authority. The database is.

### Ambiguity is a state, not an error

A timeout after the request may have been delivered becomes `SUBMISSION_UNKNOWN`, a
state whose closed transition table has edges to every real outcome and **no edge back
into submission**. It can be resolved; it can never be retried into a second order.

A 404 from the reconciliation lookup is not proof that nothing was sent — a request
that timed out may still be in flight. The measured fact is that an unknown
`client_order_id` really does return HTTP 404 with body code `40410000`, and
`RECONCILIATION_UNKNOWN_POLICY` therefore requires at least two consecutive
not-found observations AND at least 60 seconds since dispatch before resolving,
writing an operator-visible event when it does. That policy is a stated, reviewable
CHOICE, not a proof.

### The forbidden things are unrepresentable, not merely refused

`PaperOrderRequest` cannot express a sell, a fractional quantity, extended hours or a
time in force other than DAY. `quantity` is an `int`, which removes Alpaca's
fractional-order rules from the reachable surface entirely — and that mattered,
because the two official Alpaca pages **disagree** about whether fractional limit
orders are permitted. Rather than pick one reading, the product cannot ask.

`PaperEnvironment` has exactly one member. A declared `LIVE` would be a value code
could branch on and reviewers would have to prove unreachable.

### Long-only is a property of this product, not of the account

The real paper account reports `multiplier=4` and `shorting_enabled=true`. It
PERMITS leverage and short selling. Any design assuming the account would refuse them
would have rested on nothing. So the refusals are here: the request type, and a
`side = 'BUY'` CHECK in the migration.

### Two hosts, and only one of them can place an order

The trading adapter is pinned to `paper-api.alpaca.markets` and can only place,
reconcile and cancel. Quotes come from a separate, read-only client pinned to
`data.alpaca.markets`. Splitting them means the order path has exactly one reachable
hostname — the trading client refuses even the legitimate data host.

Redirects are refused, never followed. A followed cross-host redirect is exactly how
a paper-authorized request would arrive at a live endpoint carrying these
credentials, and no documentation was found establishing whether Alpaca redirects at
all — which is a reason to refuse, not a reason to allow.

### Referential integrity by trigger, not by foreign key

The link to M084's `approved_order_intent` is a BEFORE INSERT trigger. A foreign key
was the first choice and was wrong: PostgreSQL refuses to TRUNCATE a referenced
table, and M084's own test fixture truncates exactly that table, so four foreign keys
turned 97 M084 tests into errors. M084 had hit the same shape against M083 and
accepted it; repeating that would mean every milestone breaking the one before it.

The insert-time guarantee is identical. What is given up — protection against the
parent being TRUNCATEd afterwards, which requires table ownership — is stated in the
trigger's own comment and in the authority limitations rather than left to be
discovered.

### Every rule is enforced twice, on purpose

The domain refusal is the legible one a developer meets first. The database refusal is
the one that still applies to a `psql` session, a future repository written in a
hurry, or a direct SQL writer who never imported the package. Neither alone would be
enough, and `test_m085_paper_execution_postgres.py` attacks the database layer with
RAW SQL precisely so that the second one is proved rather than assumed.

The transition table exists in two places — the domain and a trigger — and a test walks
**every ordered pair of states** comparing them, so the copies cannot drift.

## What was built

| Layer | Files |
|---|---|
| Domain | `decision_candidate/paper_execution.py`, `paper_execution_repositories.py` |
| Adapter | `shared/brokerage/alpaca_paper.py` |
| Persistence | `shared/persistence/postgres_repositories/paper_execution_repositories.py` |
| Schema | `migrations/versions/b1e9d47c30a5_...py` — 7 tables, 14 triggers, 5 pinned functions |
| Application | `usecases/paper_execution.py`, `paper_execution_io.py` |
| Composition | `entrypoints/_paper_composition.py` — the only place a credential is read |
| Operator CLI | 12 console scripts |

## The limits, stated here as well as in the contract

- Row-level refusals do not cover TRUNCATE, DROP, a disabled trigger or a superuser.
  Two tests EXECUTE those holes rather than describing them.
- The quote feed is IEX only, not the consolidated tape.
- The request fingerprint is a change detector, not a cryptographic seal.
- A rejected or expired dispatch cannot be retried in this milestone: exactly one
  attempt may exist per intent, so a new attempt needs a new M084 intent. Deliberate,
  and the safe direction to err in.
- An unmapped broker status leaves the state unchanged and requires an operator to
  look. Five real Alpaca statuses are deliberately unmapped.
- **The bounded external paper submission was measured BLOCKED twice, not completed.**
  First with the market closed on a three-hour-old quote; then at the open, by
  FIND-P7-01 — the preview instant is stamped before the evidence is fetched, and the
  first rule refused every quote newer than it. Corrected with a 10 s lead bound
  (`MAXIMUM_QUOTE_LEAD_SECONDS`); the staleness tolerance was not widened either time.
- **The operator's clock must not lag the broker's by more than the lead bound.** A
  quote is judged against the caller-supplied instant; a machine whose clock is more
  than 10 s behind will refuse every fresh quote, correctly, until it is synchronized.
