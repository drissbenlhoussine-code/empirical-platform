# Exit signal quality gate (v1 Personal Paper release)

## The incident this closes

On 2026-10-20, `PositionPlanManager` claimed a STOP exit for an AAPL plan
(stop_price=338.40) against a single IEX quote snapshot: bid=335.72,
ask≈340.11-340.17. Retrieving Alpaca's own historical IEX quote ticks for the
15 seconds preceding that claim shows why a single snapshot was not enough
evidence: of 664 ticks in that window, only 360 (54%) actually crossed
stop_price — a coin flip. The ask stayed anchored near the real trading price
(≈340.06-340.69) throughout; only the bid intermittently flickered to the
anomalous low level and back, for at least 28 seconds. No trade ever printed
anywhere near 335.72. The automatic SELL that followed filled at 340.41 —
a reasonable, in-line price — so the harm was never a bad fill; it was
claiming the STOP at all on a false signal.

PR #40 (`forensic/v1-exit-trigger-evidence-audit`, merged as `d1661fd`) made
this reconstructible after the fact by persisting the exact triggering quote
(`approved_plan.triggered_exit_quote_{bid,ask,captured_at,source}`). It
deliberately did not change the trigger decision itself. This hardening is
that follow-up decision.

## What was already true before this change (not duplicated here)

Two protections already existed on the exit path, and neither one caught
this incident, which is exactly why a distinct, new gate was needed:

- **Freshness and spread, at preview/submit time.** `paper_execution.quote_refusal`
  (M085) is reused unchanged by `PreviewPositionExitHandler` and
  `SubmitAuthorizedPositionExitHandler`, refusing a quote that is too old or
  whose spread exceeds `ExecutionPolicy.maximum_spread_percent`. It runs
  against a **later** quote than the one that claimed the trigger — in the
  real incident, that later quote happened to have already reverted to a
  normal spread, so it never refused anything. This gate protects execution
  quality, not the validity of the claim decision that already happened.
- **Market-data adapter pinning.** `AlpacaPaperMarketDataClient` is pinned to
  `feed=iex` and its own docstring already says a quote from it is "evidence
  about one venue's book at one instant and nothing more." The Free/paper
  tier has no SIP access (confirmed against Alpaca's own market-data docs);
  nothing in this change asks for or assumes one.

## What changed

`PositionPlanManager._evaluate_unclaimed` no longer claims a STOP/TARGET
trigger off a single quote snapshot alone. Before calling
`claim_exit_trigger` (the one irreversible step — `ApprovedPlan.is_claimed`
refuses the same trigger forever after), it fetches a short recent window of
independent IEX quote ticks (`AlpacaPaperMarketDataClient.fetch_recent_quotes`,
covering the `EXIT_QUOTE_CORROBORATION_WINDOW_SECONDS` = 15s —
`DEFAULT_POLL_INTERVAL_SECONDS` — immediately preceding `now`) and checks
whether they agree with the single latest tick.

This is deliberately **not** a new price or spread threshold. It reuses the
exact comparison `evaluate_exit_trigger` already makes (`bid <= stop_price` /
`bid >= target_price`), just requires it to hold across several independent
recent prints, not only the single latest one:

- **≥90% of the recent window agrees** → `EXIT_QUOTE_CORROBORATION_MINIMUM_FRACTION`
  is met → claim proceeds on the same tick, no added delay. A genuine,
  sustained move (the Oct-20 incident's own comparison case) shows ~100%
  agreement in a comparable window, because real price deterioration
  persists tick to tick; it does not oscillate back to the old level.
- **Fewer agree** → `PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN`. Nothing is
  claimed; the plan is re-evaluated fresh on the next tick (at most one poll
  interval later), exactly like the existing `MONITORING`/`NOT_ELIGIBLE`/
  `NO_QUOTE` outcomes. If the condition is genuine, it corroborates on the
  very next tick and fires then, one poll interval later than before. If it
  was a flicker, it resolves away and nothing is claimed on a false signal.
- **Fewer than `EXIT_QUOTE_CORROBORATION_MINIMUM_SAMPLE` (5) ticks available**
  in the window → the sample is too thin to assess agreement at all (an
  illiquid stretch may simply not produce enough prints in 15s). The gate
  **fails open** toward the pre-hardening behavior: it trusts the single
  latest quote, exactly as before this change. This is a deliberate policy
  choice (see "Residual risks" below), not an oversight.

`MANDATORY_EXIT` itself never consults a quote: `_evaluate_unclaimed` only
runs this check for `kind in (STOP, TARGET)`. But `evaluate_exit_trigger`
prioritizes a price trigger over `MANDATORY_EXIT` even when the deadline has
ALSO already passed (its own docstring: a price that has already crossed the
stop is "the more urgent risk-bounding fact") — so when both conditions are
simultaneously true, it never even reaches the deadline branch. An
adversarial review of this PR found that an uncertain price-trigger
verdict therefore used to leave the plan **completely unclaimed** on a tick
where `MANDATORY_EXIT` was independently and unconditionally due — silently
contradicting the mission's own requirement that a poor-quality quote must
never delay a mandatory exit. `_evaluate_unclaimed` now re-checks
`plan.mandatory_exit_deadline` directly whenever the price trigger's
evidence is uncertain, and reclassifies to `MANDATORY_EXIT` (no quote
evidence attached, exactly like every other mandatory-exit claim) if the
deadline has passed. See
`test_an_uncertain_stop_candidate_past_the_mandatory_deadline_still_claims_mandatory_exit`.

## Observability

`PlanManagerThread._run`'s tick loop used to discard `evaluate_once`'s return
value entirely — the exact evidence behind a 2026-10-20-style incident was
never logged anywhere. Every per-tick outcome is now logged (INFO, or
WARNING for `NEEDS_ATTENTION`/`TRIGGER_EVIDENCE_UNCERTAIN`), including the
corroboration sample size and agreement fraction, so a future incident is
reconstructible from the process log alone.

## Adversarial review findings (2026-10-21, before merge)

An independent adversarial pass over this PR, before it was allowed to merge,
found and fixed two real defects in the first version of this gate:

1. **MANDATORY_EXIT could be silently shadowed by an uncertain price
   trigger** — see the corrected paragraph above. This was the single most
   serious finding: it directly recreated the shape of risk this whole
   mission exists to close, specifically on the obligation the mission named
   as non-negotiable ("a poor-quality quote must not silently prevent timely
   mandatory exit"). Fixed and covered by a reproduction test that failed
   against the pre-fix code.
2. **A `fetch_recent_quotes` failure (not just an empty/thin result) used to
   propagate uncaught** out of `_evaluate_unclaimed`, through `evaluate_once`,
   aborting the ENTIRE tick — every other plan that tick was about to
   evaluate, not just the one whose corroboration call failed. This was
   inconsistent with the gate's own stated fail-open philosophy: an empty
   result already failed open; an exception should too, not open a new,
   wider blast radius. `_corroborate_price_trigger` now catches a
   `fetch_recent_quotes` failure and falls back to trusting the single
   latest quote, logged at WARNING. See
   `test_a_failing_recent_quotes_call_still_claims_a_genuine_stop`.

Neither finding was caught by CI or the original test suite — both were
found by deliberately asking "what does this gate do to the OTHER two
exits (MANDATORY_EXIT) and to ITS OWN failure modes", not by re-running the
Oct-20 reproduction harder. This is recorded here as the clearest evidence
that CI passing is not proof the policy is safe.

## Policy evidence: provisional, not statistically validated

The 90% agreement threshold, 15-second window, and 5-tick minimum are
**evidence-grounded against one incident, not a statistically validated
model of IEX quote behavior.** They should be read as a defensible starting
point, not as numbers an Owner can treat as proven:

- The 54% (incident) vs. ~100% (comparison window) split comes from a single
  symbol (AAPL), a single incident, and a single comparison window pulled
  from the same trading day. It is real, directly retrieved evidence — not
  invented — but it is an n of one, not a distribution.
- "90%" was chosen because it sits with wide margin on both sides of that
  one data point, not because any statistical analysis establishes 90% as
  optimal. A different split (e.g. 75% or 95%) was not evaluated.
- The window ticks counted toward "sample_size" are not statistically
  independent observations: Alpaca's IEX feed can emit several ticks within
  the same millisecond (observed directly in the incident data — e.g. five
  distinct prints between 15:01:41.111 and 15:01:41.113), so "12 of 12
  ticks agree" can overstate the true independent evidence behind a verdict
  if most of those ticks are sub-millisecond echoes of the same underlying
  book state rather than 12 separate looks at the market. The gate still
  correctly separates the incident's 54% from a genuine move's ~100% in
  practice, but the "independent" framing in the code comments is a
  simplification, not a rigorous claim.

## Alternatives considered and why they were not used instead

- **Spread-aware validation at the trigger layer** (reject/delay a claim
  whose bid/ask spread exceeds some percent). Rejected: measured directly
  against real Alpaca data pulled for this PR, AAPL's spread legitimately
  reached **9.5%** in the first 30 seconds after market open on the SAME
  trading day as the incident, while the incident's own anomalous quote was
  only ~1.3% (within the already Owner-approved 5% entry-side
  `maximum_spread_percent`). A spread threshold tight enough to catch the
  incident would also have to be tight enough to not be defeated by it —
  and would then misfire constantly at the open, exactly when a genuine
  gap-down stop is most likely to be needed and least able to tolerate
  delay. Reusing the EXISTING trigger comparison across a short time window
  (what this PR does) does not have this false-positive-at-the-open problem
  because it does not look at spread at all.
- **Independent trade-price corroboration** (compare the triggering bid
  against the most recent IEX trade, via `fetch_minute_bars` or a new
  trades endpoint). Considered and not implemented: 1-minute bar
  granularity is too coarse to resolve a sub-minute flicker without adding
  up to 60s of latency, and the quotes-only approach already implemented
  solves the verified incident without a second new adapter capability.
  This remains available as a SEPARATE, additive corroboration source if
  the Owner wants defense in depth beyond what this PR adds.
- **A universal, hand-picked spread or price threshold with no incident
  behind it.** Explicitly rejected per the mission's own instruction; every
  number in this PR traces to either an existing Owner-approved policy
  constant (reused, not duplicated) or this incident's own measured data.

## Residual risks and policy choices left open for Owner review

- **The fail-open choice on a thin sample or a failed corroboration call.**
  An illiquid symbol, a brief feed gap, or an Alpaca historical-quotes
  outage could all produce no protection at all for that tick (identical to
  pre-hardening behavior). The alternative — refusing to claim when evidence
  is unavailable — was considered and rejected: it would risk leaving a
  genuine, required protective exit unclaimed indefinitely during exactly
  the kind of thin/degraded-data market where a stop is most needed. Note
  the correlated-failure risk this creates: a real outage or feed
  degradation could plausibly affect BOTH `fetch_quote` and
  `fetch_recent_quotes` at once, or produce exactly the kind of
  thin/irregular data that both triggers a false signal AND starves the
  gate meant to catch it. This trade-off is the Owner's to confirm, not a
  defect this PR can resolve unilaterally.
- **A genuinely volatile but non-flickering move straddling the stop/target
  line** (price searching for a new equilibrium at the open, repeatedly
  crossing back and forth across the exact threshold over several seconds)
  would also read as "inconsistent evidence" under this gate and be delayed
  by at least one poll interval, the same as a true anomaly. This is an
  accepted trade-off, not distinguished from the 2026-10-20 flicker case —
  both are "my own recent evidence disagrees with my own latest tick" by
  construction. No test or incident currently demonstrates this actually
  degrades outcomes in practice; it is flagged as plausible, unverified risk.
- **The 15-second lookback window and 90%/5-tick constants** are reused from,
  or sized against, this codebase's own existing poll cadence and the actual
  incident's measured evidence (see the constants' docstrings in
  `position_plan_manager.py` and "Policy evidence" above), not an industry
  standard or a statistically validated model. A different symbol or a much
  quieter market could warrant different numbers.
- **One additional Alpaca API call per STOP/TARGET candidate tick.** Only
  when a trigger candidate exists (rare), not on every poll — bounded,
  same-order latency as the existing `fetch_quote`/`fetch_minute_bars` calls.
  Not evaluated under real rate-limit pressure. It also widens the surface
  for the pre-existing "one exception aborts the whole tick" property of
  `PlanManagerThread._run` (now mitigated specifically for this call by the
  fail-open fix above, but `fetch_quote`'s own failure mode is unchanged and
  out of this PR's scope).
- Tests use mock/simulated quote windows that are crude compared to a live
  feed's actual flicker statistics; the 2026-10-20 reproduction stages the
  observed 54%/100% split directly from real retrieved evidence, but no
  automated test replays a full, continuously fetched live tape.

This PR does not declare the system safe for Live trading; it closes one
specific, verified false-trigger mechanism in PAPER and documents what still
depends on Owner judgment.
