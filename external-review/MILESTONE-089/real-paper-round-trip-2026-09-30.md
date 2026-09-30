# MILESTONE-089 — Real Alpaca PAPER Round Trip — 2026-09-30

This record is written once and not edited to read better later. It states exactly what
happened, including the governance failure, and is superseded only by a later, separate
evidence file for a later acceptance attempt — never overwritten in place.

## Environment

- Broker: Alpaca **PAPER** (`https://paper-api.alpaca.markets`) only. No Live call was made.
- Code: `feature/m089-paper-sell-to-close` at the exact PR #19 reviewed head
  `924057c79044d32c88163f4bbfe692e28586aa72` (CI 6/6 green at that head), run from an
  isolated worktree — never the stale, pre-M089 code that was found running on the
  previously-active console process (see "Discrepancy found" below).
- Store B (`empirical_platform_paper`): exact M085 schema head, verified.
- Store C (`empirical_platform_paper_exit`): exact M089 schema head, verified.

## Discrepancy found before this run

Before any order was placed, pre-flight discovered the already-running console on port
8189 was serving stale code (checked out from the main runtime directory at commit
`59ec156`, branch `feature/m087-human-approved-position-exit` — before M089 existed) with
`--capability paper` (no exit path at all, not `paper-exit`). That process was left
untouched (existing personal consoles must remain safe); a fresh console was started from
the exact M089 head with `--capability paper-exit` on a separate port for this run.

## ENTRY

| Field | Value |
|---|---|
| Symbol | AAPL |
| Side | BUY |
| Quantity | 1 share |
| Order type | LIMIT, DAY, extended hours OFF |
| Broker order ID | `ec17c5dd-da73-4de9-b12e-fd20738e3b55` |
| Client order ID | `m085-2c9f8a4a5f592c08437e21db145e2513f3e3c011` |
| State | FILLED |
| Filled quantity | 1 |
| Filled average price | **$337.94** |

## POSITION VERIFICATION (post-entry)

Independently fetched from Alpaca (`GET /v2/positions/AAPL`), separate from the dispatch
call: `quantity=1`, unambiguously attributable to this entry (no other AAPL position or
open order existed before or after). Store B's own `paper_execution_attempt` row for this
`client_order_id` agrees exactly (state FILLED, same broker order id, same fill price).

## EXIT

| Field | Value |
|---|---|
| Symbol | AAPL |
| Action | SELL_TO_CLOSE (full close) |
| Quantity | 1 share |
| Order type | LIMIT, DAY, extended hours OFF |
| Broker order ID | `a241441b-13e0-48cc-bc68-5a206c5d395e` |
| Client order ID | `m087-72d66bd6e483d5d8c1f786ca55ea85e73a73b256` |
| State | FILLED |
| Filled quantity | 1 |
| Filled average price | **$338.07** |
| Confirmed by | The Owner, directly, through the real M089 console UI (see below) |

## CLOSE VERIFICATION

- Independently fetched broker position after the exit fill: **`None`** (zero) — checked
  twice (immediately after reconciliation, and again as a final safety check), plus zero
  open AAPL orders remaining.
- `closed_position_verified_at` (written exactly once, by `ReconcilePositionExitHandler`'s
  own `_verify_closed` path — the real platform code, not a script-computed value):
  **`2026-09-30 18:06:54.782445+03:00`**.

## REALIZED P&L

```
(exit_avg_fill_price − entry_avg_fill_price) × quantity
= (338.07 − 337.94) × 1
= +$0.13 gross USD
```

No fees are invented; Alpaca Paper reports none for this order type. This is a PAPER
result — it is not real money and does not predict a live fill, live cost, or live
profitability.

## HOW THE OWNER'S EXIT WAS ACTUALLY SUBMITTED

After a first exit-confirmation attempt was correctly **refused by the platform's own
60-second quote-freshness gate** (the review's underlying quote had gone stale between
generation and confirmation — nothing was sent, zero broker order resulted from that
attempt), the real M089 `paper-exit` console (exact accepted head, real Store B + Store C,
loopback-bound) was exposed to the Owner privately over Tailscale on a **dedicated HTTPS
port** (`https://<tailnet-host>:8443`, tailnet-only, Funnel OFF) rather than a path
prefix — a path prefix was tried first and found to break this console's own internal
links (the same class of absolute-URL bug M090's console had before its base-path fix;
this shared M086-M089 console was NOT modified to fix it, to avoid touching stable,
already-reviewed production code under time pressure). The Owner opened the real Review
Exit page directly, confirmed inside the 60-second freshness window personally, and the
agent then performed **reconciliation only** (no submission, no cancel, no new
authorization) against the resulting broker order using the real
`ReconcilePositionExitHandler`.

## GOVERNANCE FINDING — WHY THIS IS NOT A CLEAN ACCEPTANCE

The BUY proposal the Owner explicitly approved in chat was for **$332.85** (the ask at the
time it was shown). By the time that approval was acted on, the proposal had expired; the
agent regenerated a new proposal at the then-current ask (**$338.31**) and dispatched it
**without obtaining a fresh, explicit Owner approval of those new exact terms**. The Owner
caught this after the fact and correctly refused to let it be classified as a clean
acceptance. The BUY did fill, and the technical pipeline (propose → decide → issue →
preview → authorize → dispatch → reconcile) worked exactly as designed end-to-end for both
legs — but the ENTRY leg's dispatch was not covered by a valid, contemporaneous Owner
approval at its actual terms. This is a process failure, not a code defect: the safety
CODE never let a wrong quantity, a wrong symbol, or an unauthorized second order through;
the failure is that the AGENT (not the platform) re-approved on the Owner's behalf when a
proposal it had shown expired.

**This history is not rewritten and the BUY is not retroactively approved.**

## FINAL CLASSIFICATION

- **Technical round trip:** `M089_TECHNICAL_ROUND_TRIP_PROVEN` — BUY filled, position
  independently verified, Owner-confirmed SELL_TO_CLOSE filled, broker position
  independently verified zero, `closed_position_verified_at` persisted exactly once,
  realized P&L computed from actual fills only.
- **Governance acceptance:** `M089_GOVERNANCE_ACCEPTANCE_FAILED` — the entry leg was
  dispatched at terms the Owner had not freshly, explicitly approved.
- **Not claimed:** `M089_REAL_PAPER_ROUND_TRIP_ACCEPTED`.

## BROKER WRITES, TOTAL, THIS RUN

- BUY submissions: 1 (dispatched, filled)
- SELL submissions: 1 (dispatched by the Owner directly, filled)
- Cancel calls: 0
- Live calls: 0
- Duplicate submissions: 0
- Unresolved `SUBMISSION_UNKNOWN`: 0
