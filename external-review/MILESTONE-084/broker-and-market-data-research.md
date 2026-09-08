# MILESTONE-084 Phase C — Broker and Market-Data Interface Research

**Status: research and interface selection only.** No credential was obtained,
no account was opened, no API key was created, no endpoint was contacted, and
no order of any kind was placed or prepared for placement. MILESTONE-084's code
cannot submit an order at all — a package-wide architecture rule refuses any
import of a broker order-submission client, and four negative fixtures prove
the rule fires (`tools/check_architecture.py`,
`tests/architecture/test_module_boundaries.py`).

Research date: **2026-09-08**.

---

## 0. How to read this document, and its one significant limitation

**Every claim below was gathered through web search summaries, not by reading
the vendor's own page.** The execution environment for this milestone routes
outbound HTTPS through an egress proxy that blocks `alpaca.markets`,
`www.interactivebrokers.com` and the other vendor domains; direct fetches
returned `EGRESS_BLOCKED`. Search result summaries were available; the
underlying pages were not.

That matters, and it is stated here rather than buried:

- A URL cited below is **where the claim should be verified**, not a page this
  research read in full.
- Anything that would govern a real decision — eligibility for a Finnish
  individual, current pricing, current rate limits, exact market-data
  entitlements — **must be re-checked by the operator on the vendor's own site
  before any of it is relied on.** Pricing and country eligibility in
  particular change without notice and are exactly the sort of fact a stale
  summary gets wrong.
- No claim below is presented as verified against primary documentation. Where
  a search summary was specific enough to quote a number, the number is given
  with its source; where it was not, the gap is named rather than filled in.

This document therefore selects an *interface shape* and records what is worth
checking. It is not a vendor recommendation and not a due-diligence record.

---

## 1. What MILESTONE-084 actually needs from a future integration

Before comparing vendors, the requirements this product places on one. These
follow from the domain, not from any vendor's feature list:

| Need | Why | Where it appears in M084 |
|---|---|---|
| Real-time quote (bid/ask/last) with an observation timestamp | The engine refuses a quote older than `maximum_market_data_age_seconds` and refuses one not asserted REAL_TIME | `QuoteSnapshot`, `MARKET_DATA_STALE`, `MARKET_DATA_NOT_REAL_TIME` |
| Market/session status | Only an OPEN regular session is tradeable; EARLY_CLOSE deliberately is not | `SessionSnapshot`, `MARKET_NOT_OPEN` |
| Account cash, equity, realized P&L today, order count today | Every capital and activity limit is checked against these | `AccountSnapshot` |
| Open positions and working orders | Conflict checks and the position-count limit | `PositionSnapshot`, `OpenOrderSnapshot` |
| Instrument metadata: market, currency, lot size, fractionability | Sizing floors to whole lots; currency must match | `InstrumentMetadata` |
| Average daily volume | Liquidity gate | `LiquiditySnapshot` |
| Commission and expected slippage | A missing cost estimate is `COST_ESTIMATE_MISSING`, never a zero cost | `TradingCostEstimate` |
| A paper account that mirrors live semantics | M085's target: submission without capital at risk | out of scope here |

Two properties matter more than any individual field:

1. **Every observation must carry its own timestamp.** The engine refuses to
   evaluate against data it cannot age. A vendor that returns a quote with no
   observation time forces the client to stamp it, which means the freshness
   check is measuring the client's clock rather than the data.
2. **The feed's real-time status must be knowable, not assumed.** Delayed data
   presented as live is the single failure mode that would let this product
   propose an order against a price that no longer exists.

Today none of this is connected: MILESTONE-084 reads these snapshots from an
operator-written file and records them as **operator assertions**, in the same
sense MILESTONE-076 records operator-asserted position events. The platform
checks the assertions against the operator's own limits. It does not verify
that the quote is what the market showed.

---

## 2. Candidates considered

### 2.1 Interactive Brokers (IBKR)

**Relevance to a Finland-based individual.** IBKR serves EEA clients through
Interactive Brokers Ireland Limited, which publishes its own API page
([interactivebrokers.ie](https://www.interactivebrokers.ie/en/trading/ib-api.php)).
Search summaries did not confirm anything Finland-specific; the operator must
confirm their own eligibility and entity directly.

**Interfaces.** Two families, per
[IBKR Campus](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/):
a REST **Web API** (Trading and Account Management feature sets), and the older
socket-based **TWS API** with C++, C#, Java and Python clients.

**The finding that matters most for an unattended system.** Search summaries
state that for retail and individual clients, Web API authentication is managed
through the **Client Portal Gateway**, a local Java program, and that
*"Individual clients using the CP Gateway tool must complete a manual login with
their IBKR username and password"*; automation of access is described as
available *"only when employing token-based authentication schemes such as
OAuth."*
([IBKR Campus Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/),
[Authenticating with the IBKR Client Portal REST API](https://www.interactivebrokers.com/campus/traders-insight/authenticating-with-the-ibkr-client-portal-rest-api/))

If that holds on the vendor's own page, it is an **architectural fact, not an
inconvenience**: an individual IBKR integration involves a locally running
gateway process and a periodic human login. For MILESTONE-084 that is neutral —
this product already requires a human at the approval step. For any later
milestone contemplating unattended operation it would be decisive, and it
should be confirmed before such a milestone is designed rather than after.

**Rate limits.** Summaries state a global limit of **10 requests per second per
authenticated username**, with HTTP 429 on breach and a stated 10-minute
penalty box for violating IP addresses
([IBKR Campus Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/)).
Ten requests per second is ample for a product that evaluates a small watchlist
on a human's cadence, and would be tight for anything that polls per-symbol in
a loop.

**Paper trading.** IBKR offers a paper account described as mirroring a live
account with the same tools, asset classes and markets
([IB API, Interactive Brokers Ireland](https://www.interactivebrokers.ie/en/trading/ib-api.php)).
Whether the paper environment reproduces rejection and partial-fill behaviour
faithfully enough to be evidence for M085 is **not established here** and is
the first thing M085 should test rather than assume.

**Market data.** IBKR market data requires subscriptions arranged per exchange
in Account Management. Neither the specific subscriptions needed for the
instruments this product would watch, nor their cost for a Finnish individual,
was established.

### 2.2 Alpaca

**Relevance to a Finland-based individual.** Alpaca announced completion of
**EEA passporting to 29 countries, Finland among them**, through its European
entity authorised by Spain's CNMV under MiFID II. The announcement is dated
**2026-07-07**
([Businesswire](https://www.businesswire.com/news/home/20260707116782/en/Alpaca-Completes-EEA-Passporting-to-29-Countries-Expanding-Access-to-Regulated-Investment-Services-Across-Europe),
[Alpaca blog](https://alpaca.markets/blog/alpaca-completes-eea-passporting-to-29-countries-expanding-access-to-regulated-investment-services-across-europe/)).

**An important distinction the announcement itself draws.** The passporting
announcement is framed around *"fintechs and financial institutions"* and
*"businesses building investment products"* accessing Alpaca's infrastructure —
that is, a **B2B** offering. It is **not** a statement that a Finnish
individual may open a retail brokerage account. Separate Alpaca support pages
address individual accounts and non-US residents
([Countries Alpaca is available](https://alpaca.markets/support/countries-alpaca-is-available),
[Live trading account as a non-US resident](https://alpaca.markets/learn/live-trading-account-non-us)),
and those pages could not be read here. **Do not read "Finland is on the list"
as "an individual in Finland can open a live account."** That specific question
is open and must be answered on Alpaca's own pages.

**Paper trading.** Search summaries state that the Paper Trading API is offered
by AlpacaDB, Inc., does not involve real money or real securities, and that a
country not listed under Country of Tax Residence leaves an applicant eligible
for **paper trading only**
([Paper Trading docs](https://docs.alpaca.markets/us/docs/paper-trading),
[Alpaca support](https://alpaca.markets/support/is-alpaca-available-outside-the-us)).
If that holds, a paper key may be obtainable even where a live account is not —
which is precisely the environment M085 needs and M086 does not.

**Interface shape.** A REST API with API-key authentication and no local
gateway process. For a future unattended component this is materially simpler
than IBKR's individual-client path; for MILESTONE-084 the difference is
immaterial, because nothing is connected.

### 2.3 Saxo Bank

Saxo publishes an **OpenAPI** described as available to individual clients as
well as institutional partners, REST-like over HTTP with streaming support,
using SAML and OAuth
([Saxo developer portal](https://www.developer.saxo/openapi/learn),
[What is Saxo OpenAPI?](https://openapi.help.saxo/hc/en-us/articles/4488515250717-What-is-Saxo-OpenAPI)).
Saxo also operates a simulation environment
([developer.saxobank.com/sim](https://developer.saxobank.com/sim/login/)).

Of the three, Saxo is the only one whose public description explicitly names
**individual clients** for the API and offers **OAuth without a local gateway**
plus a simulation environment. That combination is worth investigating before
either alternative is assumed better. Saxo's fee schedule and Finnish
availability were not established.

### 2.4 Nordnet, LYNX

**Nordnet** operates in Finland as Nordnet Bank AB Suomen Sivuliike, but no
public trading-API developer portal was found; open-banking aggregator access
(Plaid, Tink, TrueLayer) is account-information access, not order entry
([openbankingtracker](https://www.openbankingtracker.com/provider/nordnet-bank/apis)).
On the evidence gathered, Nordnet is not a candidate for programmatic order
entry.

**LYNX** returned nothing usable in search. LYNX is an IBKR introducing broker,
so its API story is likely IBKR's; that is an inference, not a finding, and is
recorded as such.

### 2.5 Market data, separately from the broker

Broker-supplied market data ties the feed to the broker relationship and its
subscriptions. An independent feed decouples them. Candidates named in 2026
comparisons — all pricing figures below come from **secondary comparison
articles, not vendor pages**, and must be re-checked:

| Provider | As reported by comparison articles | Note |
|---|---|---|
| Finnhub | free tier ~60 calls/min; paid tiers reported around $59 (Pro) and $200+ (Enterprise) | [apilayer comparison](https://blog.apilayer.com/12-best-financial-market-apis-for-real-time-data-in-2026/) |
| Polygon.io | reported rebranded to **Massive** on 2025-10-30; from ~$99/month at 5 requests/second | US-focused; [ksred comparison](https://www.ksred.com/the-complete-guide-to-financial-data-apis-building-your-own-stock-market-data-pipeline-in-2025/) |
| Databento | usage-based; reported $125 signup credit, Standard ~$199/mo adding live data | institutional depth-of-book; [nb-data comparison](https://www.nb-data.com/p/best-financial-data-apis-in-2026) |
| Marketstack | 70+ exchanges, free tier, paid from ~$9.99/month | breadth over depth |

**The gap none of these comparisons close.** This product needs a quote whose
*own* observation timestamp is trustworthy and whose real-time status is
explicit. Comparison articles rank on coverage, latency and price and say
almost nothing about either. Whichever provider is chosen, the first thing to
verify is what the response says about when the quote was observed and whether
it is real-time or delayed — because those two fields, not price, are what this
product's refusals depend on.

---

## 3. Interface selection for MILESTONE-085

**Selected shape, not selected vendor.** The evidence gathered here is not
strong enough to choose a vendor, and pretending otherwise would be the kind of
overclaim this project exists to avoid. What it *is* strong enough to fix is
the shape of the boundary M085 must build behind:

1. **A provider-neutral port.** M084's snapshots (`QuoteSnapshot`,
   `AccountSnapshot`, `SessionSnapshot`, `InstrumentMetadata`,
   `LiquiditySnapshot`, `TradingCostEstimate`) are already vendor-free and
   already carry `provider_id` and `observed_at`. M085 should implement an
   adapter that *fills these types*, not one that leaks a vendor's own models
   inward.
2. **Feed kind is data, not configuration.** `DataFeedKind` must be set from
   what the provider actually returns. A hard-coded `REAL_TIME` would turn the
   staleness gate into decoration.
3. **Paper first, and paper proven.** M085 targets a paper account, and its
   first obligation is to establish what the paper environment does and does
   not reproduce — rejections, partial fills, latency — rather than to assume
   it mirrors live.
4. **Credentials never enter the domain.** Whatever vendor is chosen, keys
   belong in the same configuration boundary as the PostgreSQL password and
   must not reach `decision_candidate` or `usecases`. The architecture rule
   added in this milestone already refuses the client libraries themselves.

**Recommended order of investigation for M085**, given what is and is not
established: Saxo first (individual clients named explicitly, OAuth without a
local gateway, simulation environment), Alpaca second (simplest interface; the
open question is whether a Finnish *individual* can obtain even a paper key),
IBKR third (broadest market access; the individual-client gateway and manual
login are a real design constraint to confirm before committing).

---

## 4. What this research does not establish

Stated plainly so no reader over-reads it:

- **Not established:** that a Finland-based individual can open an account with
  any vendor named here, live or paper.
- **Not established:** any current price, fee, rate limit or market-data
  entitlement. Every figure above is from a secondary source.
- **Not established:** that any paper environment faithfully reproduces live
  order handling.
- **Not established:** any regulatory, tax or reporting obligation arising from
  algorithmic order preparation by an individual in Finland. This is out of
  scope for an engineering milestone and is named here because it is a real
  question, not because it has been answered.
- **Not done:** no account opened, no key created, no endpoint contacted, no
  order placed or prepared for placement.
