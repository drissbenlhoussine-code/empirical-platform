# MILESTONE-089 — Real Alpaca Paper SELL_TO_CLOSE: acceptance contract

Status: ENGINEERING IN PROGRESS. No real Paper BUY or SELL has been submitted for M089.
No schema migration has touched `empirical_platform_paper` (the M085 Paper database, pinned
exactly at `a7d3c9e14f26`).

## 1. Scope

Build and independently verify the real Alpaca Paper exit path:

```
PAPER BUY (already proven in M085/M088's domain, not re-submitted here)
  -> broker-confirmed filled long position
  -> Owner reviews exit
  -> SELL_TO_CLOSE
  -> exactly-once PAPER submission
  -> reconciliation
  -> broker position verified zero
  -> CLOSED
  -> realized P&L / history
```

This document is the canonical statement of what M089 authorizes and what it refuses. The
required truths below are not negotiable during engineering; a case this milestone cannot
satisfy is reported as BLOCKED, not worked around.

## 2. Required truths (verbatim from the Owner's mission, numbered for traceability)

 1. SELL_TO_CLOSE only.
 2. No generic SELL.
 3. No short selling.
 4. Full close only for the first Paper acceptance.
 5. Quantity must equal the verified attributable Paper long position.
 6. A position must exist at Alpaca Paper before an exit may be authorized.
 7. Broker position truth overrides local assumptions.
 8. Owner must explicitly approve the exact exit.
 9. Exactly one broker submission.
10. Ambiguous outcome = UNKNOWN.
11. Never blind-resend.
12. Reconciliation uses the SAME deterministic exit identity.
13. CLOSED is NOT reached merely because the SELL order is FILLED.
14. CLOSED only after a later broker position read proves quantity == 0.
15. Realized P&L must be derived only from broker-supported entry/exit evidence.
16. No overnight position may be deliberately left by an acceptance test.

## 3. What this milestone does NOT authorize

Mirroring the discipline of M085's own acceptance tool docstring, stated explicitly rather
than left implicit:

- No live trading, no live endpoint, no live credential path (none exists in this repository
  reachable from Paper or Simulation composition).
- No partial close. A verified long position with quantity Q is closed entirely (quantity Q)
  or the exit is refused; there is no "close half" path in this milestone.
- No short position can be created: the exit quantity is bounded to at most the verified
  broker-reported long quantity, and the request type this milestone constructs cannot
  express a sell exceeding it or a sell with no covering long.
- No inference of ownership from `AAPL quantity > 0` alone. A position is attributable only
  when it is linked, through durable identity, to an entry intent this platform itself
  dispatched and had acknowledged by the broker (see Phase 4 / attribution below). An
  unrelated or manually-opened Paper holding is never offered for exit.
- No migration of `empirical_platform_paper` past `a7d3c9e14f26`. M089's own durable state
  lives in an explicitly separate additive store (Store C; see the architecture document).
- No automatic repair of a stale review. If broker-verified quantity, the quote, or the
  position itself changes between Review Exit and Final Confirmation, the action is refused
  and the Owner must start over from a fresh read of broker truth — never silently adjusted.

## 4. PASS / BLOCKED framing

Following the same discipline `tools/m085_paper_acceptance.py` and its M089 counterpart use:
a blocked case is a measured result, not a failure to work around. `tools/m089_paper_sell_to_close.py`
(the real-broker acceptance harness, run only after Owner approval in a separate, later
mission) will report either:

- `RESULT: EXTERNAL PAPER EXIT COMPLETED` — SELL_TO_CLOSE dispatched, reconciled, broker
  position independently re-verified at exactly zero, CLOSED, realized P&L computed from
  broker-supported entry/exit evidence only; or
- `RESULT: EXTERNAL PAPER EXIT MEASURED BLOCKED` — any required truth above could not be
  satisfied (no attributable position, stale quote, ambiguous broker answer that never
  resolves, etc.), with the exact reason recorded and no safety bound relaxed to get past it.

Nothing in M089's engineering phase submits either the entry BUY or the exit SELL against the
real endpoint. That is explicitly deferred to a separate, later, Owner-approved acceptance
mission (see the mission's own "STOP BEFORE REAL PAPER ACCEPTANCE" section).
