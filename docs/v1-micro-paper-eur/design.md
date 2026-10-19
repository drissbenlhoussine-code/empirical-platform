# V1 Micro PAPER Trading (10-20 EUR equivalent) — Design

Status: **DESIGN + PARTIAL IMPLEMENTATION**. Nothing in this document authorizes a Live
broker adapter, a real-money order, or any change to `CFG-089-PAPER`'s production risk
limits. Everything described here is PAPER-only, and only the narrow slice marked
"Implemented" below actually exists in code as of this document.

## 0. The fork-in-direction question (Owner decision required, not made here)

PR #27 (`feature/ibkr-helsinki-paper`, draft, base `release/v1-personal-paper`) already
implements a real, tested IBKR Paper adapter trading Nasdaq Helsinki (XHEL) equities, which
are EUR-native — it sidesteps the FX-conversion problem this document solves by using a
venue/account that is *already* denominated in EUR. It is mature engineering (a genuine
`ibapi`-based adapter, a durable at-most-once journal, ~1,400 lines of tests, an offline
protobuf-encoder verification harness, a dedicated architecture-boundary checker), but:

- it is sized for exactly **1 whole share, capped at EUR 500 notional / EUR 5 planned
  loss** — a fixed risk envelope, not a general small-notional (EUR 10-20) mechanism;
- it is hard-blocked on a **real-world, non-engineering gate**: the Owner's personal IBKR
  Paper account approval, reported as "pending, residential-address verification being
  processed" as of 2026-10-03 (16 days stale relative to today; current status unknown to
  this session);
- it has one real merge conflict against the current `release/v1-personal-paper`
  (`paper_operator_console_app.py::build_paper_application`, where a release security fix
  — the `/paper` base-path escape fix — and PR #27's `market_reviews` hook landed on the
  same function signature) plus two trivial import/`__init__`-body adjacency conflicts in
  `position_plan_manager.py`. All mechanical, not a design incompatibility.

This document deliberately does **not** choose between "wait for IBKR approval and build on
PR #27" and "build EUR-via-FX-conversion on the existing, already-working Alpaca PAPER
account" (which is what the rest of this document designs). **That choice belongs to the
Owner.** The two are not mutually exclusive — PR #27's own architecture audit shows the two
paths don't fight over core risk/trigger logic, only over the one composition-hook file
above — so building the Alpaca-fractional path now does not foreclose merging PR #27 later
once IBKR approval clears.

## 1. Alpaca fractional/notional trading — verified facts (not assumed)

Source: Alpaca's own docs — `docs/fractional-trading`, `docs/orders-at-alpaca`, the
`support/can-we-submit-orders-smaller-than-1-usd-in-notional-value` article, and
`docs/local-currency-trading-lct` — fetched live, not recalled from training data.

- **Order types supporting fractional/notional**: market, limit, stop, stop-limit.
- **Time-in-force**: **DAY only**. GTC/IOC/FOK/OPG/CLS are explicitly unsupported for a
  fractional (or notional) order. A fractional order is never a standing GTC order.
- **`qty` vs `notional`**: `POST /v2/orders` takes either a fractional `qty` (up to 9
  decimal places) or a dollar `notional` (also up to 9 decimal places) — never both in the
  same request (HTTP 400 if both are set). **`notional` is the right parameter for this
  mission**: convert the EUR target to a USD dollar amount and send that directly, rather
  than dividing by a live share price to compute `qty` yourself (strictly more work, more
  stale-price risk, and `notional` already makes the broker atomically size the order at
  its own, fresher quote at submission time).
- **Minimum order size**: a hard **$1.00 USD notional minimum** for buy entry orders. A
  EUR 10-20 target clears this floor by roughly 10-20x even at a pessimistic FX rate — the
  practical constraint is the *maximum*, not the minimum, side of sizing.
- **Extended hours**: fractional orders only run extended-hours as a **limit order with
  `time_in_force=day`** (the only TIF/order-type combination both the fractional-TIF rule
  and the general extended-hours rule permit simultaneously) — a fractional **market**
  order is regular-hours only.
- **Shorting**: fractional positions **cannot be shorted** — "all fractional sell orders
  are marked long." This is a broker-level backstop *in addition to* this platform's own
  BUY-only entry path; relied on but never the only control (see §4).
- **Per-symbol eligibility**: the Assets endpoint exposes `"fractionable": true/false`.
  An order against a non-fractionable symbol is rejected outright
  ("requested asset is not fractionable"). Must be checked before routing a notional order
  to a given symbol — the existing M085 submission-preview pipeline already carries an
  `asset_fractionable` field end-to-end (see `build_submission_preview`'s own parameter of
  that name, exercised by the existing M085/M089 Postgres integration tests), so this
  check-point already exists structurally; it is today's *consumer* of that field
  (`execution_policy_from_configuration`'s whole-share assumption) that does not yet act on
  it for a fractional order path.
- **Notional orders cannot be PATCH-replaced** — cancel and resubmit only. And since
  2021-10-27, certain same-security fractional order sequences outside market hours are
  rejected to prevent accidental net-short exposure.
- **No native EUR/FX support on a standard individual account.** Alpaca's Local Currency
  Trading (LCT) product does FX conversion, but it is a **Broker API** feature for
  business partners building apps for *their own* end customers, provisioned by Alpaca's
  business-development team — not a self-service feature of the individual Trading API
  key this project uses. Treat EUR support as **absent**: this platform must source,
  verify, and apply its own EUR→USD rate before ever calling the broker.

## 2. Why this must be an ISOLATED path, not a widening of the existing core

`quantity` is typed `int` throughout the existing M084-M089 entry/approval/exit pipeline —
confirmed by direct grep, not assumption: `TradeProposal.quantity`, `ApprovedOrderIntent`
(via `trade_approval.py`), `ApprovedPlan.approved_quantity`/`risk_based_quantity`/
`capital_based_quantity`, `PositionExitRequest.quantity` (whose own docstring says
*"quantity is whole and positive"*), `ExternalPositionClosure.quantity`, and
`entry_risk_contract.planned_loss(..., quantity: int)`. Widening all of these to `Decimal`
would touch the frozen M084 decision core and every handler built on it — exactly the kind
of blast radius the mission's "keep existing whole-share PAPER v1 behavior backward
compatible" instruction rules out, and exactly the shape of risk PR #27's own architecture
audit was designed to avoid for a second broker route.

One encouraging, concretely-verified fact narrows the real gap: the *broker-reported fill*
side of the model is **already `Decimal`** — `ExecutionAttempt.filled_quantity`,
`PositionExitAttempt.filled_quantity`, and `PaperAccountSnapshot`'s money fields are all
`Decimal` today. The int-vs-Decimal boundary is specifically in the *requested/approved*
quantity (what a human or the sizing logic decides to buy), not in how a fill is recorded.

**Design decision**: build micro/fractional trading as a second, isolated vertical slice —
new Decimal-quantity domain types, a new composition root, a new (versioned) configuration
— that calls the *existing* M085 Preview/Authorize/Submit and M087/M089
Preview/Authorize/Submit-exit machinery only where those handlers are already
quantity-type-agnostic (e.g. `filled_quantity` accounting, `position_closed`
verification, `claim_dispatch` exactly-once dispatch), and never where they assume `int`.
Where a shared handler's own type contract assumes `int` (e.g.
`PositionExitRequest.quantity`), the micro path needs its OWN sibling type
(`FractionalPositionExitRequest` or an widened/`Decimal`-typed variant used only by this
path's own handler), not a change to the existing type everything else depends on. This
mirrors PR #27's own enforced pattern (`tools/check_ibkr_architecture.py`'s import-boundary
checker) even though PR #27 itself is a separate venue/broker, not a separate
quantity-representation choice — the *architectural move* (isolate, don't widen the core)
is the same one, for the same reason.

## 3. What this document designs (full scope, Phase 5's own checklist)

| Requirement | Design | Status |
|---|---|---|
| Decimal fractional quantities / notional orders | `notional` (USD) computed from the EUR target via a verified FX quote; never `qty` | **Implemented** (sizing math only — see §6) |
| Precision/rounding rules | Round the USD notional to 2 decimal places (cents) using `ROUND_DOWN` — never round UP past the Owner's approved EUR amount, and Alpaca accepts up to 9 decimal places so 2 is always valid | **Implemented** |
| Minimum-order-notional enforcement | Refuse below Alpaca's $1.00 floor (practically never binding at EUR 10-20) | **Implemented** |
| Fractional eligibility verification | Must read `asset_fractionable` from the broker's Assets/submission-preview response before sizing; this document's sizing functions take it as an input and refuse if false | **Implemented** (as a precondition the caller must supply — no new broker call added) |
| No short selling | BUY-only entry path (existing invariant) + broker-level backstop (fractional sells are always marked long) | Designed; relies on existing entry-side BUY-only invariant, no new code needed |
| No leverage | Size from available cash only, never margin; portfolio exposure cap (below) is also a leverage backstop | Designed |
| No accidental whole-share rounding | Sizing never rounds a notional amount up/down to a whole-share boundary — it stays a dollar `notional`, which Alpaca fills at whatever fractional quantity that buys | **Implemented** by construction (never computes `qty`) |
| Explicit per-trade maximum notional | `maximum_usd_notional_per_trade` parameter, refusal when the computed notional would exceed it | **Implemented** |
| Portfolio-level exposure cap | `portfolio_exposure_refusal(existing_notional_sum, new_trade_notional, maximum_portfolio_notional)` | **Implemented** (pure function; wiring to a live "sum of open micro positions" read is deferred — see §7) |
| Portfolio-level loss limit | `portfolio_loss_limit_refusal(realized_and_unrealized_loss, maximum_portfolio_loss)` | **Implemented** (pure function; wiring to a live P&L read is deferred) |
| STOP/TARGET/MANDATORY_EXIT compatible with fractional quantities | `approved_plan.evaluate_exit_trigger` already compares *prices* (stop/target/deadline), never share counts — it is already fractional-safe. The exit *request* quantity is the one place needing a Decimal-typed sibling (see §2) | Designed; no code change needed to the trigger evaluator itself |
| Correct partial-fill accounting | Already `Decimal` end-to-end on the fill side (§2) — reused as-is | Designed; reuse, no new code |
| Broker-confirmed fractional position reconciliation | `ReconcilePositionExitHandler`'s own broker-position-at-zero check is already a `Decimal`/quantity-agnostic comparison (`position_closed`) | Designed; reuse, no new code |
| Exactly-once fractional SELL_TO_CLOSE | Reuse `PositionExitAttemptRepository.claim_dispatch`'s existing exactly-once primitive unchanged — it is quantity-type-agnostic | Designed; reuse, no new code |
| Price/spread/slippage/fee accounting | At EUR 10-20 notional, Alpaca's own bid/ask spread plus any $0 commission already dominates; no new fee model exists for Alpaca PAPER (it is commission-free) — flag that **real-money slippage at this notional on a thin spread could be a larger percentage of the trade than at normal size**, which Phase 6 (economic feasibility) must weigh explicitly, not this phase | Designed (flagged as a Phase-6-relevant risk, not solved here) |
| EUR→USD conversion, verified source, refusal on stale FX | `EurUsdFxQuote` (rate, source, as_of, fetched_at) + `fx_quote_refusal()` refuses when the quote is older than a caller-supplied `max_staleness_seconds` | **Implemented** (the *data structure and staleness gate* only — see §5 for the honest gap) |
| No Live broker adapter enabled by default | Not applicable yet — no broker adapter of any kind exists for this path; by construction, nothing here can submit an order | **N/A / trivially true** |
| Backward-compatible with whole-share PAPER v1 | Zero existing files modified by this phase's implementation slice (new module only) | **Implemented** (verified: `git diff --stat` for this phase touches only new files) |
| New, versioned, PAPER-only configuration, not touching CFG-089-PAPER | A new `configuration_governance_id` (e.g. `CFG-089-PAPER-MICRO-EUR-V1`), a new Postgres row, read the same way `CFG-089-PAPER` is read today (by id) — never edits the existing row | Designed; no config-loading code changes needed, only a new row + a new id constant when the broker-wiring phase is built |

## 4. What this document does NOT implement (honest gap, not a fabricated pass)

**No trustworthy FX rate source has been selected or vetted in this session.** The mission
instruction is explicit: *"If you cannot find or build a trustworthy FX source within
scope, say so plainly rather than fabricating one."* Saying so plainly: no EUR/USD rate
provider (free or paid, e.g. a central-bank reference rate, a commercial FX API, or
anything else) was researched, tested for uptime/latency, or integrated. `EurUsdFxQuote`
(§5/§6) defines the *shape* a verified rate must have — a `Decimal` rate, its `source`
name, and an `as_of` timestamp the staleness gate can check — but **no concrete adapter
that calls a real FX API exists**. Building and vetting one (reliability, rate-limit
behavior, a fallback/second-source comparison, and what "verified" should mean operationally)
is explicitly deferred to a follow-up phase, not quietly assumed away.

**Broker submission wiring does not exist.** There is no fractional-order composition root,
no `FractionalPositionExitRequest` sibling type, no new console capability flag, and no new
Postgres migration for the versioned micro configuration. Only the pure sizing/FX-staleness/
exposure-cap/loss-limit domain functions below exist, with full unit-test coverage. This is
a deliberate scope decision given the mission's own effort-budgeting guidance ("design it
rigorously even if you can't fully implement every sub-item") and the size of a correct,
safely-reviewed broker-wiring change (comparable in scope to the M085/M087/M089 milestones
themselves, each of which was its own multi-PR effort).

## 5. `EurUsdFxQuote` and the staleness gate

```python
@dataclass(frozen=True, slots=True)
class EurUsdFxQuote:
    rate: Decimal        # 1 EUR = `rate` USD
    source: str           # non-empty, identifies WHICH provider -- never silently blank
    as_of: datetime       # aware; when the provider says this rate was valid
    fetched_at: datetime  # aware; when THIS process retrieved it
```

`fx_quote_refusal(quote, *, now, max_staleness_seconds)` refuses (never guesses) when:
`as_of` is not timezone-aware, `as_of` is after `now` (a rate from the future is evidence
of a clock problem, not a usable quote), `rate` is not strictly positive, or
`now - as_of` exceeds `max_staleness_seconds`. This is the literal enforcement of "refusal
on stale FX (never assume 10 EUR = 10 USD)."

## 6. Implemented: `src/empirical_platform/decision_candidate/micro_fractional_trading.py`

A new, fully isolated module (zero existing files modified). Pure, `Decimal`-typed,
read-only domain functions — no broker call, no persistence, no side effect:

- `EurUsdFxQuote`, `fx_quote_refusal`
- `fractional_notional_for_eur_target(eur_amount, fx, *, minimum_usd_notional, maximum_usd_notional_per_trade, asset_fractionable)` → the rounded USD `notional` to submit, or a refusal string. Refuses on: a non-fractionable asset, a non-positive EUR amount, a computed notional below Alpaca's minimum, or above the caller's own per-trade cap.
- `portfolio_exposure_refusal(existing_open_notional, new_trade_notional, *, maximum_portfolio_notional)` → a refusal string when the sum would exceed the cap, else `None`.
- `portfolio_loss_limit_refusal(realized_and_unrealized_loss, *, maximum_portfolio_loss)` → a refusal string when the current loss (as a positive `Decimal`) has reached or passed the cap, else `None`.

See `tests/unit/test_v1_micro_fractional_trading.py` for the full behavioral contract
(every refusal path and every accept path is proven there).

## 7. Deferred, in priority order, for a follow-up phase

1. Select and integrate a real EUR/USD rate source; decide what "verified" means
   operationally (single source with a tight staleness window vs. two sources
   cross-checked).
2. `FractionalPositionExitRequest` (or a widened sibling) and the composition wiring to
   actually call Alpaca's `notional`-parameter order endpoint — net-new broker-adapter
   code, its own migration for the versioned configuration row, and its own Postgres
   integration test suite, mirroring M085/M089's own shape.
3. Wire `portfolio_exposure_refusal`/`portfolio_loss_limit_refusal` to a live read of this
   path's own open positions and running P&L (today they are pure functions the caller
   must feed; no such live read exists yet because no positions can exist yet).
4. Resolve the PR #27 fork-in-direction question with the Owner (§0) — if IBKR approval
   clears and the Owner prefers the EUR-native venue, decide whether this Alpaca-fractional
   path continues in parallel or is shelved.
5. Phase 6/7 work specific to this path once it can submit real PAPER orders: adversarial
   tests (10/20 EUR notional edge cases, stale/missing FX, fractional precision edge
   cases — items already on the Owner's Phase 7 list) and a small-notional economic
   feasibility pass (spread as a fraction of a EUR 10-20 trade is structurally larger than
   at normal size; Phase 6 must not treat a validated-at-scale edge, if one is ever found
   on Opportunity Engine-style notionals, as automatically validated at this notional too).
