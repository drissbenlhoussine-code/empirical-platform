# MILESTONE-062 multi-period validation fixture

**Synthetic, deterministically generated, fixed local test data. Not live or
downloaded historical market data. `source_kind = "FIXED_VALIDATION_FIXTURE"`
throughout -- never described as historical-market evidence.**

`synthetic_multi_period_validation_dataset_bundle.json` -- one canonical,
continuous one-minute timestamp grid across four instruments (`AAPL`,
`AMZN`, `GOOG`, `MSFT`), 48 bars per instrument, generated once by
`generate_m062_fixture.py` (not committed to the repository; a scratch
generator script) using `random.Random(SEED)`, `SEED = 6062001` -- fixed
and documented, never adjusted after inspecting results. Each bar has an
independent, uniform 18% chance of being a "breakout bar" (a larger
bullish move paired with a volume spike), applied identically across the
full 48-bar sequence with no bias toward any particular segment; all other
bars are a mild, symmetric random walk. This produces genuine, unscripted
breakout opportunities (price above the recent reference high *and*
volume above the recent reference average -- the frozen M057 strategy's
own two conditions) without hand-picking which bar, instrument, or
segment receives one.

**Generation is a one-shot, accept-as-is process.** The parameters above
(breakout probability, drift/volatility ranges) were chosen once, before
any result was inspected. The seed was never re-rolled and no bar was
hand-edited afterward to shape the segment comparison in Section "Actual
results" below -- including the fact that HOLDOUT_1 underperforms
DEVELOPMENT_REFERENCE. Bad holdout performance is treated as a valid,
expected, unmassaged result (MILESTONE-062 Phase 12).

SHA-256 of the exact committed file (recorded here, outside the file
itself, to avoid a self-reference hash paradox -- the same convention used
for every external-review package ZIP in this repository):

```
3289c380b233b06495c865b1645185436318b2394d77faaea97be96bf787c9f3
```

## Segment layout

Three private, non-overlapping, contiguous 16-bar blocks per instrument
(`warmup=5` + `scoring=8` + `buffer=3`), declared in the bundle's own
`segments` array in this exact order:

| segment_id | role | bar indices (0-based, per instrument) | warmup | scoring | buffer |
| --- | --- | --- | --- | --- | --- |
| `DEV` | `DEVELOPMENT_REFERENCE` | 0-15 | 0-4 | 5-12 | 13-15 |
| `HOLDOUT_1` | `HOLDOUT_1` | 16-31 | 16-20 | 21-28 | 29-31 |
| `HOLDOUT_2` | `HOLDOUT_2` | 32-47 | 32-36 | 37-44 | 45-47 |

No bar belongs to more than one segment. `warmup_bar_count` equals the
study's own `reference_window_size` (5, the M057 default); `buffer_bar_count`
equals the study's own `outcome_model.holding_horizon_bars` (3, the M061
default) -- `build_validation_study()` rejects any bundle where these do
not match exactly. Each segment therefore produces exactly 8 scored
decision cutoffs (`scoring_bar_count`), and no segment's `HistoricalDataset`
slice (fed to the unmodified M061 engine) ever includes a bar from another
segment -- the complete holdout/data-isolation firewall this milestone
requires.

## Actual results (real `evaluate()`/`build_scan()`/`build_trade_plan()`/
`build_position_plan()`/`build_historical_backtest_run()` output, `account_equity=100000`, `risk_percent=0.01`, default risk/sizing/execution/outcome/cost policies)

| Segment | Cutoffs | Simulated | Executed | Wins | Losses | Time exits | Net PnL | Total R | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEV | 8 | 4 | 4 | 4 | 0 | 2 | 933.85 | 14.31 | 100% | undefined (no losses) |
| HOLDOUT_1 | 8 | 3 | 3 | 1 | 2 | 1 | 64.58 | -0.59 | 33.3% | 1.39 |
| HOLDOUT_2 | 8 | 5 | 5 | 5 | 5 | 2 | 383.23 | 5.45 | 60% | 4.16 |

`holdout_1_net_pnl_delta = -869.27`, `holdout_2_net_pnl_delta = -550.62`
(both holdouts underperform the development reference on net PnL; total R
likewise degrades from DEV to HOLDOUT_1). This is reported as-is -- M062
draws no conclusion beyond the raw comparison itself (see the governance
document's honesty-gate section).

## Survivorship-bias and sample-size disclosure

Fixed four-instrument universe, no membership changes, no delisting model:
`SURVIVORSHIP_BIAS_NOT_ADDRESSED`. 8 scored cutoffs and at most 5 executed
trades per segment is a small sample by any statistical standard -- these
counts are reported plainly, never described as statistically strong
evidence.
