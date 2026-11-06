# M100 -- Cloud launch closure: acceptance report (FINAL)

Consolidated PR: #49 (`claude/empirical-m100-launch-c492oz` -> `release/v1-personal-paper`), draft, not merged.
It contains PR #47's two commits unchanged (`205e906`, `ac5e649`) plus the follow-up work. PR #46 is untouched
(its tree is identical to the release branch). Nothing here was run on the Windows host or against any broker.

## Defect register (all independent-review findings; no P0 was ever found)

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| D1 | P1 | Daily loss / order count / position count / exposure never enforced | **FIXED**: enforced pre-claim and inside `before_send`, fail-closed, atomic (day advisory lock + durable admission marker); whole-account broker read taken INSIDE the lock; exits never blocked |
| D2 | P1 | Duplicate entry (two Prepares) | **FIXED**: submit-time working-order guard + D1 ledger |
| D3 | P1 | Exit one-shot DAY limit, never repriced/re-armed | **FIXED**: bounded cancel/replace (LIMIT only, <=50 bps concession, <=5 attempts/session, 30 s / 15 s spacing), partial fills, cancel races, ambiguity reconciled never resent, market closed, restart-safe; unknown/non-terminal statuses (`suspended`...) fail closed |
| D4 | P1 | No Host check (DNS rebinding) | **FIXED** (421) |
| D5 | P1 | Deploy resume skipped gates 1/2/3/6 | **FIXED** |
| D6 | P1 | Autostart wrapper restarts console after deliberate stop; no single-instance lock; Windows port reuse | **FIXED**: OS lock, maintenance hold, exit-code contract, bounded backoff + circuit breaker, `SO_EXCLUSIVEADDRUSE`, importable Task XML. **Needs Windows-host verification** |
| D7 | P1 | MANDATORY_EXIT ack/round ids collided (found by the E2E matrix) | **FIXED** |
| D8 | P1 | Partial entry: filled shares unprotected; EXPIRED-with-fills entry unattributable | **FIXED**: entry remainder protector (cancel after 120 s, at STOP/TARGET trigger or mandatory deadline; <=5 cancels, 15 s apart); EXPIRED-with-fills is a stable holding state, also shown in the Owner console |
| D9 | P1 | One plan's exception aborted the whole manager tick; entry `suspended` mapped to REJECTED | **FIXED** (per-plan isolation with durable event; `UNMAPPED_BROKER_STATUS`, fail closed) |

## Known residual items (P2 / operational, none release-blocking for a supervised PAPER run)

- Blocked `/confirm-approval` shows no outcome flash and still creates the ApprovedPlan for an entry never sent (inert: no position).
- A refused Prepare followed by another within the same second raises a raw persistence error (fails closed).
- Wording: a working BUY is reported as "a position of N already exists".
- `ReconcilePaperOrderHandler` adds a round row per tick while a partial entry waits (slow growth).
- Admission is keyed by the ET day of "now" but counted by `claimed_at` (irrelevant in market hours); correctness relies on READ COMMITTED (server default).
- Alpaca specifics untested against the real service: `pending_cancel` latency, DAY-expiry status naming, real `last_equity` semantics (daily P&L proxy = equity - last_equity includes unrealized).

## Verification record

See the "Final report" delivered with PR #49 for exact SHA, commands and counts. Evidence of the 24-step matrix:
`docs/operations/m100-acceptance-evidence.md` (+ `.json`), produced by a real run against throwaway PostgreSQL 16.
Not-truly-end-to-end: the broker/market data is a scripted local exchange (real HTTP client, real hosts pinned), time is virtual,
the WSGI app is called in-process and the plan-manager thread is driven by `evaluate_once`.
