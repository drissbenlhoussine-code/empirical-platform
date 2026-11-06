# M100 D1 — Trading limits enforced at the broker submission boundary

**Scope:** PAPER entries (BUY). Exits are never evaluated by this gate. No threshold is invented:
every number comes from the stored `OperatorTradingConfiguration` version the approved intent
names (`CFG-… vN`), the same record the M084 engine and the send-time policy already use.

## What was wrong

`prepare_v1_paper_candidate` passed the risk engine `realized_pnl_today=0`, `orders_submitted_today=0`
and a positions list containing at most the target symbol. The engine's daily-loss, daily-order and
position-count checks therefore always passed in the real PAPER path, and nothing re-checked them
when the order actually left the process.

## What is enforced now

`decision_candidate/trading_limit_gate.py::entry_limit_refusals` (pure) returns every reason an
entry must not be sent:

| Limit (configuration field) | Rule |
|---|---|
| `maximum_daily_loss` | loss = −min(realized P&L today, whole-day P&L); refuse when loss ≥ limit. Floating gains cannot hide a realized loss; floating losses count |
| `maximum_daily_order_count` | orders submitted today (any final state, incl. rejected) + this system's own unseen claims; refuse when ≥ limit |
| `maximum_simultaneous_positions` | distinct symbols held ∪ working BUY orders ∪ in-flight claims; refuse when the new symbol would exceed the limit |
| existing position / working order / in-flight entry in the same symbol | refuse |
| `maximum_position_quantity_shares`, `maximum_capital_per_trade`, `maximum_percent_per_trade` | refuse if the order exceeds them |
| `maximum_deployable_capital` | Σ cost basis of positions + working-BUY notional + in-flight notional + this order must not exceed it; an unpriced working/in-flight order makes exposure unprovable → refuse |
| any limit missing / non-positive | `TradingLimits` cannot be constructed → entries stay blocked until configured and approved |

Evidence comes from `PaperBrokerPort.fetch_portfolio_risk_evidence` (Alpaca: `/v2/account`
`equity − last_equity` minus Σ `unrealized_intraday_pl` from `/v2/positions` = realized P&L today;
`/v2/orders?status=all&after=<day start>`; a response that fills a 500-order page is rejected as
possibly truncated; shorts, missing fields and unknown shapes raise). "Today" starts at the earlier
of operator-local and New York midnight. An unknown broker order status counts as *working*.

## Where it runs

`SubmitAuthorizedPaperOrderHandler`:

1. **Before the claim** (so a doomed order does not spend the authorization).
2. **Inside `before_send`, after the claim is durable**, on fresh reads, before the send-capable
   boundary. Because the claim is already in PostgreSQL, a concurrent submitter in another process
   sees it as an in-flight entry (matched to the broker by `client_order_id`, never double counted);
   of two racing submitters at least one always sees the other. A refusal at this point is
   `NOT_SENT` and provably created nothing.

Anything that cannot be read or proven (exception, stale evidence, unreadable intent, invalid
limits) is a refusal. Retries re-enter the same checks; a retry of a sent intent returns the
existing attempt. Restart recovery needs no extra state: limits are derived from the broker and the
attempts table every time.

The candidate-preparation path now feeds the engine the same real evidence (whole account, worst of
realized/whole-day P&L, today's order count), so Prepare refuses early and consistently.

## Notes

* The loss measure is deliberately the *worse* of realized and whole-day P&L. It can block entries
  earlier than a pure-realized rule would. That is the fail-closed direction; the Owner can ask for a
  realized-only reading, which would be a new decision.
* `GET /v2/orders` can only be proven complete below 500 orders/day; above that the entry is blocked.
