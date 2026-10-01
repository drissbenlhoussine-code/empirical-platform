# MILESTONE-095 -- Event-Driven Edge Research: Owner Report

Research dataset: 100 sessions (2026-05-13 -> 2026-09-29, identical to M093/M094's own
window), 6 ranked symbols (AAPL, AMZN, GOOGL, META, MSFT, NVDA), SPY/QQQ as benchmark-only.
Locked FINAL HOLDOUT (2026-03-18 -> 2026-05-12): **never accessed** (see
`holdout-confirmation.md`). This is a research-direction study, not a strategy build --
nothing here has entry/stop/target geometry or position sizing, and zero broker writes
occurred.

## 1. What new data source was added?

Alpaca's News API (`data.alpaca.markets/v1beta1/news`, Benzinga-sourced), reached with the
SAME paper-trading credentials this repository already holds. A new, narrow, read-only
method (`AlpacaPaperMarketDataClient.fetch_news`) was added alongside the existing
`fetch_quote`/`fetch_minute_bars` -- no order-shaped argument or return value anywhere,
and the package-wide architecture rule forbidding any order-submission SDK import is
unchanged.

## 2. Is it point-in-time safe?

Yes, with one disclosed caveat. Every article carries both `created_at` (first
publication) and `updated_at` (can be later, if the article was edited). This milestone
uses `created_at` exclusively as `published_at` and never reads `updated_at` for any
decision -- confirmed by a dedicated test that constructs a fake article WITHOUT an
`updated_at` attribute at all, proving the normalization code path never touches it. A
decision at time T only ever sees events with `published_at <= T`; an adversarial test
proves an event published one second after T is invisible to a decision at T.

## 3. What does it cost?

Free, under the existing Alpaca account -- no new subscription, no new signup. Rate limit
200 calls/minute (confirmed live from the response headers during this study). A
**structured earnings-surprise calendar (e.g. Finnhub)** would require creating a NEW
third-party account, which this research work was not authorized to do on its own
initiative -- see `data-source-qualification.md` Source 2, and Q14 below.

## 4. What events were tested?

Company-specific (<=2-symbol-tagged) news articles, split into `EARNINGS_KEYWORD_NEWS`
(headline matches a predeclared, text-only regex: "earnings", "EPS", "beats/misses
estimates", "guidance", etc.) vs. `OTHER_NEWS`. No structured earnings-surprise sign,
guidance direction, or analyst-rating classification was produced -- no qualified source
supplies the underlying structured fields (see `event-taxonomy.md`).

## 5. How many observations?

2,821 company-specific articles (89 earnings-keyword, 2,732 other) across the 6-symbol,
100-session window. 570 of 600 possible symbol-sessions resolved into a gap-bucket
observation (30 missing bars/prior-close, consistent with prior milestones' own gap
rate for this provider).

## 6. Does event + gap outperform gap alone?

**Could not be cleanly tested as originally designed** -- the "no event" control group
for gap-up sessions is empty (n=0): this news source is dense enough that virtually
every session has SOME qualifying article beforehand. This is itself a finding, not a
bug (see Q12). The narrower `EARNINGS_KEYWORD_NEWS` (n=15) vs. `OTHER_NEWS` (n=559)
comparison showed a numerically larger mean move for earnings-keyword news (+0.146% vs.
+0.014%) but with a sample too small (n=15) and a positive-fraction actually BELOW the
other-news group's -- read as noise, not signal.

## 7. Does relative volume improve it?

The most separated split measured in this milestone: among event+gap-up observations,
high relative early volume (>= the trailing-20-session median) showed +0.244% mean 30m
move vs. -0.197% for low relative volume. This was discovered by looking at the study's
own output, not predeclared beforehand, so it is flagged as a lead for a future,
properly pre-registered follow-up -- not adopted as a finding here (Phase 17's own
discipline against post-hoc cutoff selection).

## 8. Which forward horizon is strongest?

None, on the predeclared combined event+gap-up group: the 30-minute mean move (+0.023%)
is the representative figure the cost/temporal/cross-symbol gates evaluated, and it fails
cost survivability regardless of horizon. Descriptively, `GAP_UP_LARGE` alone (not the
group actually tested) shows its largest moves at 30m (+0.294%) and session (+0.359%) --
again a post-hoc observation, not a tested finding.

## 9. Does the effect exceed COST1?

**No.** +0.023% mean 30-minute move vs. a 0.10% COST1 round trip (same cost model as
M091-M094, unchanged). Does not survive COST2 (0.30%) either.

## 10. Is it stable across time?

**No.** First chronological half of the research window: -0.065% mean. Second half:
+0.091%. The sign flips.

## 11. Is it stable across symbols?

**No.** 4 of 6 symbols (AAPL, AMZN, GOOGL, NVDA) show a negative mean 30m move; 2 (META,
MSFT) show a positive one. No single symbol dominates the sample (largest share 20.5%),
so this is genuine cross-symbol disagreement, not a concentration artifact.

## 12. How often would opportunities occur?

~54 event+gap-up qualifying observations/month across all 6 symbols combined (~12.5/week,
~2.6/day) -- a "moderate" to "high" frequency band per the mission's own taxonomy, frequent
enough to be practically tradeable IF the effect were real. It is not, on the evidence
above.

## 13. Which event directions qualify?

**None.** The one predeclared direction tested (`EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP`)
fails 3 of its 4 mechanical gates (cost survivability, temporal stability, cross-symbol
sign agreement) -- see `candidate-selection.md`.

## 14. What data remains missing?

Structured earnings-surprise magnitude/sign (actual vs. consensus EPS), guidance
direction, and analyst upgrade/downgrade actions with price targets. No
already-credentialed source in this environment supplies these. A real earnings-surprise
study would require the Owner creating an account with a vendor such as Finnhub (free
tier: 60 calls/min, but earnings-surprise history limited to the most recent 4 quarters
per symbol -- usable for a window like this one, but not a stable multi-year archive) or
a paid tier of a similar provider, and adding its API key to the environment the same way
`EMPIRICAL_ALPACA_PAPER_API_KEY` already exists.

## 15. What should we build next?

Not a strategy on `EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP` as tested -- it fails 3 of 4
gates. Two concrete, specific leads worth a dedicated, PROPERLY PRE-REGISTERED follow-up
(fixed definitions BEFORE looking at that study's own outcome data, reusing the exact
cost/temporal/cross-symbol gate this milestone already built):

1. **`GAP_UP_LARGE` scoped on its own**, not combined with `GAP_UP_SMALL` -- the
   asymmetry observed here (and the +0.1525 selectivity IC, the largest rank correlation
   measured across M093-M095's cumulative research) suggests gap MAGNITUDE may matter
   more than event presence per se.
2. **High relative early volume as a co-filter** on top of (1) -- the single most
   separated split measured in this milestone.

Both should be tested as ONE new predeclared direction (large gap + high relative
volume), not two, to keep the decision gate honest and avoid re-introducing the
post-hoc-cutoff problem this report explicitly flagged. The structured earnings-surprise
gap (Q14) is a separate, lower-priority track that needs an Owner decision on a new
vendor account before it can be investigated at all.
