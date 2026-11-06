# M100 — LIVE readiness assessment (separate from PAPER launch)

> Update (final cloud closure): gaps 1 and 2 below are closed **for PAPER** and proven on simulated broker responses only. Neither has met a real broker, so this is still **LIVE_READY = FAIL / not yet tested**.

**Verdict: LIVE_READY = FAIL / not yet tested.** A successful PAPER launch proves plumbing, not profitability
or LIVE safety. Nothing in this repository enables LIVE: the Alpaca client pins `paper-api.alpaca.markets`,
refuses redirects, and has no LIVE configuration variable. Enabling LIVE would need new code and review.

## Gaps that must be closed before any LIVE discussion

1. ~~Daily loss / daily order-count / simultaneous-position limits are not enforced~~ — **CLOSED for PAPER by D1** (`m100-trading-limits.md`); original gap: not enforced in the PAPER path
   (`realized_pnl_today=0`, `orders_submitted_today=0` hardcoded in `paper_operator_console.py`; position count
   only sees the single target symbol). Must be wired to broker truth with fail-closed behavior on missing data.
2. ~~Exit protection is a single DAY limit sell~~ — **CLOSED for PAPER by D3** (`m100-exit-state-machine.md`); original gap: a single DAY limit sell at the trigger-time bid.** No cancel/reprice/escalation; an
   unfilled or expired exit attempt is never re-armed, so STOP and MANDATORY exits can be defeated in a falling
   market. Needs cancel-and-reprice (or marketable exits with slippage bounds) and re-arming.
3. **No cross-process single-instance lock** for the PAPER console (duplicate exits are blocked by DB claims,
   duplicate entries are now guarded by the submit-time working-order check, but a lock is still missing).
4. **Windows listener reuse:** `allow_reuse_address=True` on the console server; verify on the host that a second
   process cannot bind the same port.
5. Slippage/fee/liquidity model has only been validated on historical research; no real-fill evidence exists.

## Requirements to define and sign off (Owner decisions, none made here)

Broker environment isolation (separate credentials and host config, LIVE never shares PAPER env), written
real-money order authorization, maximum total exposure, per-position and per-day limits, daily loss stop,
slippage and fee assumptions, liquidity floors, market-hours rules, emergency stop procedure, monitoring and
alerting, incident response, a limited initial rollout (smallest size, one symbol, supervised), and an explicit
written financial risk acceptance.
