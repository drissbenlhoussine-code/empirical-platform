# MILESTONE-057 market-data fixtures

**These are synthetic, hand-authored fixtures. They are not live or
historical market data, and no claim is made that they resemble real
AAPL trading activity.** They exist solely to exercise the M057 trading
evaluation vertical slice deterministically in tests.

Each file is a JSON array of one-minute bars for a single fictitious
`AAPL` session, ordered by strictly increasing timestamp, matching the
input contract consumed by `_parse_bars_file` in
[`evaluate_trading_observation.py`](../../../src/empirical_platform/entrypoints/evaluate_trading_observation.py).

- `synthetic_aapl_1min_long_candidate.json` -- five quiet reference bars
  followed by one evaluation bar whose close breaks above the reference
  high on above-average volume. Feeding this through the frozen
  `PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION` v1 strategy with the
  default 5-bar reference window produces `LONG_CANDIDATE`.
- `synthetic_aapl_1min_no_trade.json` -- the same five reference bars
  followed by an evaluation bar that stays inside the reference range on
  below-average volume, producing `NO_TRADE`.
- `synthetic_aapl_1min_lookahead_probe.json` -- the same five reference
  bars, but the evaluation bar itself carries a deliberately extreme
  high/volume alongside a close that only clears the *true* reference
  high (computed from the five prior bars alone). `ObservationWindow`
  structurally forbids a bar dated after the evaluation bar from ever
  entering a window at all, so the residual look-ahead risk in this
  architecture is narrower and more specific: whether the evaluation
  bar's own OHLCV silently contaminates the reference-window statistics
  it is being compared against (e.g. an off-by-one that slices the last
  N bars of the *whole* window instead of the last N *reference* bars).
  If that leak existed, this fixture's extreme high/volume would flip
  the decision from `LONG_CANDIDATE` to `NO_TRADE` and corrupt the
  reported `reference_high`/`reference_average_volume`; the regression
  test asserts both stay anchored to the five true reference bars.
