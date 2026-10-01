# M095 Phase 1/2 -- Event Data Source Discovery and Qualification

## What was actually investigated (not assumed)

Real provider documentation was fetched (`WebFetch` against `docs.alpaca.markets`) and
cross-checked against a live, read-only, empirically-verified API call made with the
Alpaca PAPER credentials this repository already holds (`EMPIRICAL_ALPACA_PAPER_API_KEY` /
`EMPIRICAL_ALPACA_PAPER_SECRET_KEY`, the same pair `alpaca_paper.py` already uses for
quotes/bars -- confirmed present in this environment without printing their values). A
second category of provider (structured earnings-surprise calendars: Finnhub, Polygon,
and similar) was researched via `WebSearch` against current (2026) pricing/limits pages,
but **not** live-tested, because doing so would require creating a new third-party
account and provisioning a new API key -- an action outside what this research fork is
authorized to take on its own initiative. That constraint is itself a qualification
input, not a shortcut: see Source 2 below.

## Source 1 -- Alpaca News API (`data.alpaca.markets/v1beta1/news`, Benzinga-sourced)

**Empirically verified, live, read-only GET request**, using the existing paper
credentials, for AAPL news in the already-exposed M093/M094 research window
(2026-06-01 through 2026-06-05, well outside the locked holdout):

```
GET https://data.alpaca.markets/v1beta1/news?symbols=AAPL&start=2026-06-01T00:00:00Z&end=2026-06-05T00:00:00Z&limit=10
-> HTTP 200
-> X-Ratelimit-Limit: 200, X-Ratelimit-Remaining: 199  (free-tier rate limit, confirmed from the live response header, matching docs.alpaca.markets)
-> real articles returned, e.g. id=53019090, source="benzinga",
   created_at="2026-06-04T21:32:02Z", updated_at="2026-06-04T21:32:03Z",
   symbols=["AAPL","AMZN","GOOGL","META","MSFT","NVDA"]
-> "next_page_token" present -> the endpoint paginates; a full-window fetch needs to follow it.
```

- **Historical depth:** per Alpaca's own News API announcement (`alpaca.markets/blog`),
  historical news is available back to 2015 via the Benzinga partnership. The live test
  above independently confirms real data exists for the already-used M093/M094 research
  window (2026-05-13 through 2026-09-29); the locked holdout (2026-03-18 through
  2026-05-12) was never queried (see `holdout-confirmation.md`).
- **Timestamp granularity/timezone:** `created_at` / `updated_at`, RFC-3339, UTC, to the
  second in observed responses (field supports finer precision per docs, but nothing in
  this study depends on sub-second resolution).
- **Point-in-time correctness:** `updated_at` differs from `created_at` on some articles
  by a few seconds in the sample pulled above, meaning articles CAN be edited after
  publication. This repository's own point-in-time rule therefore uses `created_at`
  (first-publication time) as `published_at`, never `updated_at`, and a research decision
  at time T only ever uses events whose `created_at <= T` -- see Phase 5 adversarial
  tests. This is a real, disclosed limitation, not treated as absent.
- **Rate limit:** 200 calls/minute on the free/Basic plan (confirmed live, matches docs).
  Pagination (`next_page_token`) is required for any window returning more than `limit`
  (max 50/request) articles -- the adapter follows it rather than silently truncating.
- **Cost/licensing:** free with the existing paper-trading account; no separate
  subscription, no new signup, no new credential. Per Alpaca's docs the 15-minute-delay
  restriction that applies to the Basic *market-data* (bars/quotes) plan is NOT
  documented as applying to the News API; the live historical fetch above (for a date
  weeks in the past) succeeded with no delay-related error, consistent with that reading.
- **Schema honesty:** `content` is empty string on most articles in the sample (summary
  and headline carry the substance). There is **no EPS, no consensus estimate, no
  earnings-surprise field, no structured sentiment/classification field** anywhere in
  the schema -- confirmed both from the live payload and from Alpaca's own endpoint
  documentation. This is general financial news with real timestamps and symbol tags,
  not an earnings-surprise feed.
- **Noise:** many articles tag 5-10+ symbols at once (broad market-wrap pieces), which
  would misattribute a market-wide story to one company if used naively -- addressed by
  a predeclared filter in Phase 7 (see `event-taxonomy.md`), not by excluding the source.

**Qualification: QUALIFIED**, scoped specifically to symbol-tagged, timestamped
general-news event *presence* (including a reproducible, headline-keyword-based
earnings-news flag -- see Phase 7). **NOT qualified** as a source of structured
earnings-surprise magnitude/sign, which this schema does not supply at any tier.

## Source 2 -- Structured earnings-surprise calendars (Finnhub, as the representative case)

Researched via `WebSearch` against Finnhub's current pricing/capability pages (not live
API-tested, per the account-creation constraint above):

- Finnhub's free tier: 60 calls/minute; `company_earnings` (historical quarterly EPS
  actual/estimate/surprise) is **limited to the most recent 4 quarters per symbol** on
  the free tier (paid tiers unlock 20+ years). Four quarters from "now" (2026-10) would
  span roughly 2025-10 through 2026-10, which happens to cover the M093/M094 research
  window by coincidence of timing, but this is a rolling window tied to the *current*
  date, not a stable historical archive -- unsuitable as a reproducible research
  foundation independent of when the study is re-run.
- **No credential for Finnhub (or Polygon, Benzinga-direct, or IEX Cloud) exists in this
  environment.** Obtaining one requires registering a new account and provisioning a new
  API key -- outside what this research fork is authorized to do unilaterally (new
  third-party account creation is a user-authorized action, not a research-tooling one).
- Even setting the credential question aside, the free-tier 4-quarter rolling limit
  would make any earnings-surprise-magnitude study not independently reproducible beyond
  the next few months, which conflicts with this milestone's own point-in-time/
  reproducibility bar.

**Qualification: REJECTED** for this milestone's purposes -- not because the data
doesn't exist, but because (a) no credential is provisioned and this fork cannot
provision one, and (b) the free tier's rolling-4-quarter limit is not a stable research
foundation. This is recorded as an explicit, actionable gap for the Owner (see Owner
report Q14/Q15): if a real earnings-surprise study is wanted, the Owner would need to
create an account with Finnhub (or a similar vendor) and add its key to the environment
the same way `EMPIRICAL_ALPACA_PAPER_API_KEY` already exists.

## Source 3 -- Analyst upgrade/downgrade actions

Alpaca's News API includes some analyst-action articles as ordinary news items (no
structured upgrade/downgrade/target-price fields observed in the schema). No dedicated
analyst-ratings API was found documented under Alpaca, and no credentialed alternative
exists in this environment for the same reason as Source 2.

**Qualification: REJECTED** as a structured source; **folded into** Source 1's general
news feed only to the extent a headline can be reproducibly keyword-matched (see Phase 7
taxonomy) -- not treated as a verified upgrade/downgrade signal.

## Phase 2 gate -- outcome

Per the mission's own gate: a source qualifies only if timestamps are precise enough,
historical records are available, point-in-time alignment is possible, it is technically
reproducible, licensing permits this research use, and it does not silently expose
later revisions as if known earlier. Source 1 (Alpaca/Benzinga News) clears all six for
the scope of symbol-tagged, timestamped **news-event presence** (optionally
earnings-keyword-flagged by a predeclared, reproducible headline rule) -- it does NOT
clear the bar for structured earnings-surprise magnitude, which no available,
already-credentialed source in this environment supplies.

**M095 therefore proceeds, scoped narrower than the mission's full Phase 7 taxonomy
wish-list**: the event study below uses `EVENT_PRESENT` / `NO_EVENT` as the primary
predeclared classification (any Alpaca/Benzinga news article, filtered to
single-or-dual-symbol-tagged articles to exclude broad market-wrap noise, published
before the observation point), with a secondary, reproducible, headline-keyword-based
`EARNINGS_KEYWORD_NEWS` vs `OTHER_NEWS` split. `EARNINGS_POSITIVE_SURPRISE` /
`EARNINGS_NEGATIVE_SURPRISE` / `GUIDANCE_POSITIVE` / `GUIDANCE_NEGATIVE` /
`ANALYST_UPGRADE` / `ANALYST_DOWNGRADE` as *structured, surprise-signed* categories are
**not produced** -- no qualified source supplies the underlying structured fields, and
this milestone does not fabricate them from headline text or price action. This scoping
decision is made here, in Phase 2, before any outcome data is examined (Phase 7
compliance).

This is not `EVENT_DATA_BLOCKED` -- a real, qualified, point-in-time-safe event source
(news presence + a reproducible earnings-keyword flag) is available and used -- but it
is a narrower event study than the mission's full wish-list, and that narrowing is
disclosed here rather than silently assumed away.
