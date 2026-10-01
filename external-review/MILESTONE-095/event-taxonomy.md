# M095 Phase 7 -- Predeclared Event Taxonomy

Fixed in `src/empirical_platform/decision_candidate/m095_event_data.py` BEFORE
`tools/m095_event_study.py` was run against any outcome data. Neither the keyword list nor
the company-specificity filter was edited after seeing results.

## Primary classification: `event_present` (boolean)

An observation is `event_present = True` for a given symbol/session if at least one
**company-specific** (tagged with <=2 symbols, per `is_company_specific`) Alpaca/Benzinga
news article has `published_at <= session_open` for that symbol. This is the only
qualified signal (`data-source-qualification.md`, Source 1) -- general news presence with
a real, verified publication timestamp, nothing more.

## Secondary classification: `EventType` (predeclared, headline-text-only)

- `EARNINGS_KEYWORD_NEWS` -- the headline matches `EARNINGS_KEYWORD_PATTERN`, a fixed,
  case-insensitive regex over earnings/guidance-report language ("earnings", "EPS",
  "beats/misses estimates", "raises/cuts guidance", etc.). Deliberately excludes
  sentiment words ("surges", "soars", "plunges") that would smuggle a price-derived
  judgment into a "predeclared" taxonomy.
- `OTHER_NEWS` -- everything else.

This regex produces the IDENTICAL classification for a headline regardless of what the
price did afterward -- confirmed by `tests/unit/test_m095_event_data.py::
test_earnings_keyword_matches_are_reproducible_text_only_heuristic`, which classifies
both a "beats estimates" and a "misses estimates" headline as `EARNINGS_KEYWORD_NEWS`.

## What was NOT built, and why (predeclared, not a late excuse)

`EARNINGS_POSITIVE_SURPRISE` / `EARNINGS_NEGATIVE_SURPRISE` / `GUIDANCE_POSITIVE` /
`GUIDANCE_NEGATIVE` / `ANALYST_UPGRADE` / `ANALYST_DOWNGRADE` as the mission's full Phase 7
wish-list describes them -- i.e. SIGNED, structured classifications -- are **not
produced**. No already-credentialed source in this environment supplies the structured
EPS/consensus/analyst-target fields a signed classification would need (Phase 1/2
qualification). Labeling a headline's sign from its own text (treating "beats" as
positive and "misses" as negative) was considered and rejected: it would conflate a
reproducible PRESENCE signal with an unverified, text-inferred SIGN that this milestone
cannot cross-check against any structured ground truth -- closer to the kind of
retrospective labeling Phase 7 explicitly forbids than to a legitimate predeclared
taxonomy, even though the words come from the headline rather than the price. This
scoping decision was made in `data-source-qualification.md` (Phase 2), before
`tools/m095_event_study.py` was ever run.

## An honest, discovered limitation: the "no event" control group is nearly empty

2,821 company-specific articles were fetched across 6 symbols over the 100-session
research window -- roughly 4.7 articles per symbol-session on average. Benzinga's feed
includes contributor opinion pieces, CEO-quote roundups, and routine coverage, not only
discrete "events" in the everyday sense. As a direct consequence, **every gap-up
observation in this study had at least one qualifying article published before that
day's open** -- the `without_event` control group for both `GAP_UP_SMALL` and
`GAP_UP_LARGE` has `n=0` (`event-study-results.json`'s own `event_vs_control` section).
Phase 9's "event vs. no event" control-group design, as the mission describes it, could
not be meaningfully executed with this source at the company-specificity filter level
(<=2 symbols) chosen here -- not because of an implementation bug, but because the
source's news volume is too dense for a binary present/absent split to discriminate.

The `EARNINGS_KEYWORD_NEWS` vs. `OTHER_NEWS` split (89 vs. 2,732 articles) is this
milestone's actual working proxy for event sparsity, and it is reported in
`event-study-findings.md` -- it does not change the overall classification. This
limitation, and a possible refinement (tightening to single-symbol-only articles, or a
minimum-novelty filter) for a future iteration, is recorded honestly here rather than
silently worked around.
