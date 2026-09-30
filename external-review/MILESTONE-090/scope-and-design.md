# MILESTONE-090 — Opportunity Engine V1: scope, architecture, and reuse decisions

Status: ENGINEERING. RESEARCH + ENGINEERING ONLY. No real Paper BUY, SELL, cancel, or Live
call is authorized or performed by this milestone. Branch `feature/m090-opportunity-engine-v1`,
created from PR #19's accepted head `924057c79044d32c88163f4bbfe692e28586aa72`
(`feature/m089-paper-sell-to-close`), in an isolated worktree
(`C:\Users\LuxSy\trading-worktrees\m090-work`). Not merged.

## 1. What already exists, and what does not (Phase 1 discovery, verbatim conclusions)

The repository has two largely independent tracks:

- **Track A** (M057–M073, offline/research): `strategy.py` → `scan.py`/`ranking.py` →
  `trade_plan.py` → `position_plan.py` → `historical_backtest.py`, orchestrated by
  `research_session.py`/`daily_research_brief.py`. Real, tested, daily-bar-only, ONE
  hardcoded strategy (`PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION`), not pluggable, not
  intraday, batch/offline cadence.
- **Track B** (M084–M089, live/paper): `operator_trading_configuration.py` →
  `trade_proposal.py` → human approval → `paper_execution.py`/`alpaca_paper.py` → (M087/M089)
  `position_exit.py`. Live quote-based, single-symbol evaluation, no ranking/scanning, no bars
  anywhere.

M090 sits between them: it needs Track B's live/intraday, human-approval, durable-decision
discipline, but Track A's ranking/candidate vocabulary — and neither track's existing code can
be extended in place to get it (Track A's strategy function isn't pluggable and is daily-bar;
Track B's `evaluate_trade_proposal` is single-symbol with no ranking). **M090 is therefore a
new, parallel module family**, reusing specific existing pieces documented below, never
duplicating what already exists.

**Confirmed gaps this milestone must fill (narrowest read-only addition, per Phase 1):**
- No minute-bar (or any OHLCV) fetch exists anywhere. `AlpacaPaperMarketDataClient` is
  quote-only; the only real historical adapter (`YahooFinanceChartMarketDataSource`)
  explicitly refuses anything but `BarInterval.ONE_DAY`. → M090 adds ONE new read-only method,
  `AlpacaPaperMarketDataClient.fetch_minute_bars`, and a new port `IntradayBarsPort` (see §3).
- No opportunity/candidate/ranking type spans both tracks. → M090 defines its own, in a new
  module, described in §2.

**Confirmed reuse (nothing below is rebuilt):**
- `decision_candidate/market_data.py`: `Instrument`, `BarInterval` (`ONE_MINUTE` already a
  member, never previously produced by any real source), `Bar`, `ObservationWindow` — reused
  verbatim for intraday bar sequences and as M090's look-ahead-bias defense (`evaluation_bar`
  vs. `reference_bars`, exactly Track A's own anti-leakage type).
- `decision_candidate/operator_trading_configuration.py`: `OperatorTradingConfiguration`,
  specifically `watchlist` — reused AS the bounded, configurable universe (Phase 3). It is
  already versioned, validated (sorted, deduped, upper-case, disjoint from
  `prohibited_instruments`), and is the SAME source of truth M084/M085 already use for symbol
  eligibility — not a second universe concept. `prohibited_instruments`, `minimum_price`,
  `maximum_price`, `minimum_liquidity_shares`, `maximum_spread_percent`,
  `maximum_market_data_age_seconds`, `permitted_markets`, `permitted_session`,
  `earliest_entry_time`, `latest_entry_time`, `mandatory_liquidation_time`,
  `operator_timezone`, `maximum_capital_per_trade`, `maximum_percent_per_trade` are ALL reused
  directly rather than re-specified (Phase 5's instruction: "place it in a versioned M090
  policy/configuration" is satisfied by reusing the configuration ALREADY versioned this way,
  not creating a parallel one, wherever a field already exists for the purpose).
- `decision_candidate/paper_execution.py`: `ExecutionPolicy`, `execution_policy_from_configuration`,
  `quote_refusal` (freshness/spread/crossed-book gate) — reused unchanged for the quote leg of
  M090's data-quality gate (Phase 5), exactly the pattern M089 already reused for the exit
  path.
- `decision_candidate/product_market_inputs.py`: `QuoteSnapshot`, `InstrumentMetadata` — reused
  for representing quote/asset evidence inside an opportunity, rather than inventing parallel
  types.
- `AlpacaPaperClient.fetch_clock`/`fetch_asset`/`fetch_account` (M085, unchanged) — reused for
  the session gate and asset-eligibility checks.
- Ranking pattern (not the formula): M058's `RANKING_MODEL_ID`/`RANKING_MODEL_VERSION`
  constants + a pure scoring function + a `rank_sort_key` tiebreak — the SHAPE is copied
  (versioned model id, pure deterministic function, explicit tiebreak), the M058 FORMULA
  (`breakout_strength + volume_strength`, tied to one specific strategy) is not, since it does
  not apply to M090's different evidence set.
- Testing convention: `EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`-gated live-network test pattern
  (M069's `test_m069_market_data_acquisition_live_network.py`) — reused verbatim for the new
  Alpaca bars adapter's own live smoke test.
- `usecases/run_historical_backtest.py` (M061) shape (decide at bar close, hypothetical fill
  at next bar, stop/target/time-exit resolution, bps-slippage cost model) — the SHAPE is the
  model for M090's replay harness (Phase 19); the concrete implementation is new because M061
  is wired to the single M057 strategy and to whatever `HistoricalDataset` daily bars produced.

**Deliberately NOT reused:**
- M064's `UniverseAuthority`/`MembershipManifest` — designed for point-in-time historical
  survivorship studies, used only by offline studies today; heavier than "a bounded,
  configurable universe" (Phase 3) requires. `OperatorTradingConfiguration.watchlist` already
  does the job.
- Track A's `strategy.py`/`scan.py`/`ranking.py` — single hardcoded strategy, daily cadence,
  not pluggable; extending in place would either break Track A's own contract or require
  generalizing it far beyond this milestone's scope.
- `TradeProposal` as M090's own opportunity type — it is a single fixed-shape, ALREADY-DECIDED
  BUY order (no ranking score, no candidate/rejected vocabulary, stop/target are simple
  percentage offsets of entry, not structural). M090 defines its own richer type (§2) and, at
  the Owner-approval boundary only (Phase 17), is *compatible with* constructing a
  `TradeProposal`-shaped hand-off for the existing pipeline — never a replacement of it, and
  this milestone does not perform that hand-off end-to-end (Phase 17 stops it explicitly
  before any broker call).

## 2. Domain: `decision_candidate/opportunity_engine.py` (new)

One new, self-contained domain module, `decision_candidate` layer per `tools/check_architecture.py`'s
existing boundary rules (already permits `decision_candidate` → `shared`, no change needed
there).

### 2.1 Policy (Phase 5's "versioned M090 policy/configuration")

```
@dataclass(frozen=True, slots=True)
class OpportunityEnginePolicy:
    policy_version: str                        # e.g. "M090-V1"
    maximum_quote_age_seconds: int              # reuses the SAME idea as quote_maximum_age_seconds
    maximum_spread_percent: Decimal             # (ask-bid)/midpoint * 100
    minimum_price: Decimal
    maximum_price: Decimal | None
    minimum_recent_share_volume: int            # Phase 6 liquidity floor, from bars actually fetched
    structure_lookback_bars: int                # Phase 7 window size (swing high/low, breakout range)
    minimum_reward_risk_ratio: Decimal          # Phase 10 hard gate
    maximum_capital_per_trade: Decimal | None   # falls back to OperatorTradingConfiguration's own
    maximum_loss_per_trade: Decimal             # Phase 11 sizing input
    top_n: int                                  # Phase 14 — how many opportunities reach Today
    entry_tolerance_percent: Decimal            # Phase 8 — allowable slippage from evidence to entry
    opportunity_validity_seconds: int           # Phase 8 — expiry of a CANDIDATE/ACTIONABLE row
```

Every numeric default is documented at its definition with the reasoning (never a bare magic
number), and the WHOLE object's `fingerprint` (SHA-256 of its canonical field values, same
pattern as `ExecutionPolicy.fingerprint`) is carried on every opportunity so a policy change is
always visible and auditable, exactly as M085's `ExecutionPolicy.fingerprint` already works.

### 2.2 Market session gate (Phase 4)

```
class MarketSessionState(StrEnum):
    PREMARKET_RESEARCH = "PREMARKET_RESEARCH"
    REGULAR_SESSION = "REGULAR_SESSION"
    ENTRY_WINDOW_CLOSED = "ENTRY_WINDOW_CLOSED"
    MARKET_CLOSED = "MARKET_CLOSED"

def market_session_state(*, clock: BrokerClockView, policy_earliest_entry: time,
                          policy_latest_entry: time, operator_timezone: str) -> MarketSessionState: ...
```

Built from `AlpacaPaperClient.fetch_clock()` (`is_open`, `next_open`, `next_close` — reused,
unchanged) plus the SAME `earliest_entry_time`/`latest_entry_time` fields
`OperatorTradingConfiguration` and `ExecutionPolicy` already carry — not a new time-window
concept. Research/display is permitted in every state; only `REGULAR_SESSION` (and, within it,
inside the entry window) may produce an `ACTIONABLE` opportunity — every other state forces
`CANDIDATE` at most, matching Phase 4's "actionable Owner approval must fail closed outside the
permitted window."

### 2.3 Data quality and liquidity gates (Phase 5, 6)

Reuses `quote_refusal` (unchanged, M085) for the quote leg. Adds bar-evidence checks over an
`ObservationWindow` (reused type): bars present, count >= `structure_lookback_bars`,
chronological, no zero/negative OHLC (already enforced by `Bar.__post_init__`, reused not
re-implemented), `evaluation_bar` age within `maximum_quote_age_seconds`-equivalent bound for
bars. Liquidity: recent bar volume vs `minimum_recent_share_volume` — the actual measured
evidence (Alpaca bars' own `volume` field), never a fabricated average-daily-volume figure; a
symbol whose only available evidence is too thin is marked `INSUFFICIENT_EVIDENCE`, a distinct
rejection reason, never silently treated as liquid.

### 2.4 Structure/signal (Phase 7)

The smallest deterministic, auditable rule set: a bounded-range breakout (close breaks above
the high of the prior `structure_lookback_bars` bars) confirmed by higher-low structure over
the same window and recent volume participation above the window's own average (all computed
from the SAME bars already fetched for liquidity — no second data pull). Every signal is a pure
function over `ObservationWindow` returning a typed, inspectable evidence object (never a bare
boolean) so the "why this trade" evidence points (Phase 8, Phase 15) are the SAME values the
gate itself computed, not reconstructed after the fact.

### 2.5 Entry / stop / target / size / mandatory exit (Phase 8–12)

- Entry: the evaluation bar's close, with `entry_tolerance_percent` as the allowable slippage
  window re-checked at Review (Phase 16) — never a vague "buy AAPL."
- Stop: the structural swing low over `structure_lookback_bars` (a deterministic,
  price-structure method, per Phase 9's own examples) — refused outright if `stop >= entry`.
- Target: entry + `minimum_reward_risk_ratio` × (entry − stop) at minimum (the SAME reward/risk
  gate IS the target's own floor, not a separate arbitrary number) — never described as a
  probability.
- Quantity: `floor(maximum_loss_per_trade / (entry − stop))`, then capped by the SAME
  `maximum_capital_per_trade`/`maximum_percent_per_trade`/`minimum_cash_reserve` fields
  `OperatorTradingConfiguration` already enforces for entries — the FINAL quantity is the
  minimum of every applicable cap, never leveraged, never short (a short is structurally
  impossible: this engine only evaluates long breakouts). `quantity < 1` → reject.
- Mandatory exit: `mandatory_liquidation_time` (the SAME field M084/M085 already use) applied
  to the current session date — reused, not re-derived.

### 2.6 The Opportunity object and its statuses (Phase 13)

`TradingOpportunity` (frozen dataclass) carries every field Phase 13 lists, keyed to a durable
`opportunity_id`, `policy_version` (the policy fingerprint), and a closed `OpportunityStatus`
enum: `CANDIDATE, ACTIONABLE, EXPIRED, INVALIDATED, REJECTED, OWNER_APPROVED, OWNER_IGNORED`. An
opportunity is `ACTIONABLE` only when every hard gate (session, data quality, liquidity,
signal, stop validity, reward/risk floor, quantity >= 1) passed — never assigned by the ranking
step, which only orders already-actionable survivors (Phase 14: "hard fail first, rank second").

### 2.7 Ranking (Phase 14)

`opportunity_quality(...)` is a pure function over already-computed, already-gated evidence
(spread quality, liquidity, trend/structure consistency, reward/risk, evidence freshness,
distance from the stop) producing a `Decimal` "Opportunity Quality" score plus a formula
version id — never called a probability or a win chance. `rank_sort_key` breaks ties by symbol,
mirroring M058's own tiebreak pattern. Only the top `policy.top_n` survivors are returned to
Today.

## 3. Ports and the new Alpaca capability

`decision_candidate/opportunity_engine_repositories.py` (new): `IntradayBarsPort` Protocol —

```
class IntradayBarsPort(Protocol):
    endpoint_host: str
    def fetch_minute_bars(
        self, symbol: str, *, start: datetime, end: datetime, limit: int
    ) -> tuple[BrokerBarView, ...]: ...
```

A SEPARATE Protocol from `PaperMarketDataPort` (never widened) — widening `PaperMarketDataPort`
itself would force every existing M085–M089 implementer and test fake
(`SimulatedMarketData`, `tests/unit/_m085_fakes.py`'s `FakeMarketData`) to grow a method they
never use, for zero benefit and real blast radius on already-reviewed code. `AlpacaPaperClient`
implements BOTH `PaperMarketDataPort` (unchanged) and `IntradayBarsPort` (new
`fetch_minute_bars` method) — one concrete class satisfying two Protocols is ordinary duck
typing, not a widened capability boundary.

`fetch_minute_bars` calls the real Alpaca market-data host's historical bars endpoint
(`GET /v2/stocks/{symbol}/bars`, IEX feed, `timeframe=1Min`) — read-only, no order can be placed
through it, and it is added to `AlpacaPaperMarketDataClient` (the market-data-only class, not
`AlpacaPaperClient`) for the same reason `fetch_quote` already lives there.

## 4. Persistence: one new additive migration, Track A's database, Track A's pattern

M090's tables are added to the SAME database Track A's M057–M073 migrations already live in
(the shared `migrations/` chain, current head `e7c1a9d3b5f2`) — NOT a new Store, and NOT
Store B/C (M090 never touches Paper credentials, never reads or writes
`paper_execution_attempt`, never opens a second database). Two tables, mirroring M084's
proposal/decision durability pattern:

- `opportunity` — one row per generated `TradingOpportunity`, append-only except the
  status transition column (mirroring M084's `trade_proposal.status` pattern), carrying every
  Phase 13 field plus the policy fingerprint and evidence-as-of timestamps.
- `opportunity_decision` — one row per Owner action (`OWNER_APPROVED`/`OWNER_IGNORED`),
  append-only, single row per opportunity (a UNIQUE constraint), exactly M084's
  `ApprovalDecision` shape.

`require_exact_m090_schema_head`-style guard is unnecessary here in the same way M058-M073's
own tables never needed one: M090 does not gate a real broker action on the schema (unlike
M085/M087/M089, whose guards exist because a stale schema next to LIVE credentials is the
danger); it is read/research data. The migration itself still follows the exact same
CHECK-constraint and immutability discipline as every other milestone's schema.

## 5. Usecases and the Owner-approval boundary (Phase 15–18)

`usecases/opportunity_engine.py` (new): `GenerateOpportunitiesHandler` (Phase 2–14, orchestration
only, calls the pure domain functions), `ReviewOpportunityHandler` (Phase 16: re-runs every
hard gate against FRESH evidence, refuses/invalidates rather than reprices),
`ApproveOpportunityHandler`/`IgnoreOpportunityHandler` (durably record the Owner's decision).

**The hand-off boundary is explicit and enforced structurally, not just by convention**:
`ApproveOpportunityHandler` records `OWNER_APPROVED` and MAY construct the exact
`TradeProposal`-shaped payload the existing M084/M085 pipeline expects — but this milestone's
composition root never wires that payload to `evaluate_trade_proposal`, `IssuePaperBoundOrderIntentHandler`,
or any Alpaca submission path. No M090 module imports `alpaca_paper.AlpacaPaperClient.submit_order`/
`submit_close_order`, and an architecture test proves it (mirroring `test_m087_exit_boundaries.py`'s
own "no module of this package may import a client that can place ... an order" pattern, already
enforced globally by `tools/check_architecture.py`'s `ORDER_SUBMISSION_PREFIXES`).

## 6. What this milestone explicitly does not build (Phase 18 boundary)

No autonomous stop/target monitoring, no automatic SELL, no scheduler/cron that runs the engine
in the background, no binding of an approved opportunity to live position management. Approval
recording stops at "the Owner said yes to this plan," durably, in Store A's new tables — nothing
downstream of that is built or wired.
