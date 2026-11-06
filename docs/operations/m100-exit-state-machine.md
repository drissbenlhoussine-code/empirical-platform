# M100 D3 — Exit state machine (bounded, auditable, fail-closed)

**Scope:** PAPER only. No market orders, no LIVE, no change to the exit order terms
(SELL-TO-CLOSE, LIMIT, DAY, regular hours). Implemented in
`usecases/position_plan_manager.py` (`PositionPlanManager._resume_claimed` and helpers).

## What was wrong

A STOP / TARGET / MANDATORY_EXIT claim produced exactly one DAY limit sell at the trigger-time
bid. It was never cancelled or repriced, and a CANCELED / EXPIRED / REJECTED attempt was never
replaced: `_resume_claimed` kept re-running the same (already-consumed) identity, which returned
the existing attempt forever. In a falling market the protective exit could rest unfilled,
expire at the close, and leave the position unprotected with no visible escalation.

## The machine (all state is re-derived from durable data every tick)

| Latest attempt (from `for_entry`) | Action |
|---|---|
| none | dispatch generation 0 (unchanged behaviour) |
| `DISPATCH_CLAIMED`, `SUBMISSION_IN_PROGRESS`, `SUBMISSION_UNKNOWN` | **reconcile only** — never cancel, replace or duplicate an order whose existence is not established |
| `SUBMITTED` / `ACCEPTED` / `PARTIALLY_FILLED` | reconcile first (broker truth). If the broker status is not a recognised working status → **escalate** (no cancel). If it has rested `< EXIT_WORKING_REST_SECONDS` → wait. Else, if attempts remain and the market is open with ≥ `EXIT_MINIMUM_SECONDS_TO_CLOSE_FOR_REPRICE` to the close → request a **cancel** (state `CANCEL_REQUESTED`; *a request is not a cancellation*). Final attempt rested too long → **escalate** (the resting order is left in place — it is still protection) |
| `CANCEL_REQUESTED` | reconcile; only the broker's answer moves it. Unconfirmed for `EXIT_CANCEL_CONFIRMATION_SECONDS` → **escalate**; nothing is replaced |
| `FILLED` | reconcile verifies the broker position is flat (`position_closed`) |
| `CANCELED` / `EXPIRED` / `REJECTED` (broker-confirmed, terminal) | assess the position. Not safely re-exitable (closed/resized elsewhere, attribution ambiguous) → **escalate**. Attempts spent → **escalate**. Market closed → wait, then **escalate** after `EXIT_UNPROTECTED_ESCALATION_SECONDS`. Otherwise **re-arm**: new deterministic identity (digest of plan, trigger kind, generation), priced by the ordinary preview (fresh bid, same freshness/spread gates), quantity = the broker-verified remainder |

A cancel the broker refuses or errors on is retried and, after rest + confirmation time, escalated (`cancel-refused`). A re-arm whose prepared preview/authorization pair goes stale before it is claimed is superseded by a new deterministic identity (so a transient outage cannot latch a generation). The entry kill switch is engaged once, when a risk is first recorded; the manager never re-engages a switch the Owner released.

Overlap is impossible by construction: a re-arm requires the previous attempt to be terminal *as
recorded from the broker*, and the PostgreSQL single-active-exit index independently forbids two
active exits per entry. Quantity can never exceed the verified remainder (`entry filled − Σ exit
fills`, which must equal the broker position), so a partial fill followed by a re-arm sells only
what is left.

Each tick isolates failures per plan (`_guarded`): a broker outage or unexpected response for one
plan becomes a visible `NEEDS_ATTENTION` outcome, takes no exit action, and does not abort other
plans.

## Escalation ("unresolved risk")

`_escalate` is idempotent per (plan, attempt, kind of risk) and does three things:

1. appends a durable `EXIT_UNRESOLVED_RISK` event to Store C (`position_exit_event`);
2. engages the **entry** kill switch (`ExecutionKillSwitchRepository`) so no new exposure is
   taken — the exit handlers still use the always-disengaged stand-in, so exits are never blocked;
3. the plan outcome is `EXIT_UNRESOLVED_RISK` (WARNING-logged each tick) and the Active page shows
   **Needs attention** (it now reads the *latest* attempt, not only the active one).

The kill switch is released only by the Owner (Safety page). The manager never disengages it.

## Operational bounds — pending Owner approval

These are time/count bounds, **not** price or size thresholds. Defaults chosen by engineering:

| Constant | Value | Meaning |
|---|---|---|
| `EXIT_MAXIMUM_ATTEMPTS` | 3 | first dispatch + 2 re-arms per plan |
| `EXIT_WORKING_REST_SECONDS` | 90 | how long a working exit may rest before a cancel is requested |
| `EXIT_MINIMUM_SECONDS_TO_CLOSE_FOR_REPRICE` | 300 | no cancel-for-reprice nearer the close than this |
| `EXIT_CANCEL_CONFIRMATION_SECONDS` | 120 | unconfirmed cancel → escalate |
| `EXIT_UNPROTECTED_ESCALATION_SECONDS` | 120 | no working exit and cannot re-arm → escalate |

Repricing is **bounded and not discretionary**: each re-arm is priced by the same preview as the
first attempt (current fresh bid) and the number of attempts is capped. An Owner who wants a price
floor or a different cap must say so; none was invented.

## Owner runbook when `EXIT_UNRESOLVED_RISK` appears

1. Open the Alpaca paper dashboard: note position, open orders, last fills.
2. Cancel any stale exit order and close the position by hand if appropriate.
3. Record the closure in the console (external position closure) so the manager stops acting.
4. Only then release the kill switch on the Safety page.
