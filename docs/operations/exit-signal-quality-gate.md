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

`MANDATORY_EXIT` is completely unaffected: `_evaluate_unclaimed` only runs
this check for `kind in (STOP, TARGET)`; the mandatory-liquidation trigger is
time-only and never consults a quote at all, so a poor-quality or thin quote
can never delay it.

## Observability

`PlanManagerThread._run`'s tick loop used to discard `evaluate_once`'s return
value entirely — the exact evidence behind a 2026-10-20-style incident was
never logged anywhere. Every per-tick outcome is now logged (INFO, or
WARNING for `NEEDS_ATTENTION`/`TRIGGER_EVIDENCE_UNCERTAIN`), including the
corroboration sample size and agreement fraction, so a future incident is
reconstructible from the process log alone.

## Residual risks and policy choices left open for Owner review

- **The fail-open choice on a thin sample.** An illiquid symbol or a brief
  feed gap could produce fewer than 5 ticks in 15 seconds, in which case this
  gate adds no protection at all for that tick (identical to pre-hardening
  behavior). The alternative — refusing to claim when evidence is too thin —
  was considered and rejected: it would risk leaving a genuine, required
  protective exit unclaimed indefinitely during exactly the kind of thin
  market where a stop is most needed. This trade-off (silently reduced
  protection during illiquidity vs. a new way to block a protective exit) is
  the Owner's to confirm.
- **The 15-second lookback window and 90%/5-tick constants** are reused from,
  or sized against, this codebase's own existing poll cadence and the actual
  incident's measured evidence (see the constants' docstrings in
  `position_plan_manager.py`), not an industry standard. A different symbol
  or a much quieter market could warrant different numbers; this PR does not
  claim 90%/5/15s is universally correct, only that it is evidence-grounded
  for this incident and leaves a wide margin on both sides of it.
- **One additional Alpaca API call per STOP/TARGET candidate tick.** Only
  when a trigger candidate exists (rare), not on every poll — bounded,
  same-order latency as the existing `fetch_quote`/`fetch_minute_bars` calls.
  Not evaluated under real rate-limit pressure.
- Tests use mock/simulated quote windows that are crude compared to a live
  feed's actual flicker statistics; the 2026-10-20 reproduction stages the
  observed 54%/100% split directly from real retrieved evidence, but no
  automated test replays a full, continuously fetched live tape.

This PR does not declare the system safe for Live trading; it closes one
specific, verified false-trigger mechanism in PAPER and documents what still
depends on Owner judgment.
