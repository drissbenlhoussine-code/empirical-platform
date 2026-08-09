# MILESTONE-061 historical backtest fixture

**Synthetic, hand-authored, fixed local test data. Not live market data. Not downloaded historical data. Not a profitability claim.**

`synthetic_6instrument_historical_backtest_dataset.json` exists solely to exercise the M061 historical-validation engine deterministically. It preserves one canonical one-minute timestamp grid across six instruments (`AAPL`, `AMZN`, `GOOG`, `MSFT`, `NVDA`, `TSLA`) from `2026-08-10T13:40:00+00:00` through `2026-08-10T13:51:00+00:00`.

The fixture is deliberately small and mechanical. It is designed to prove:

- multiple historical decision cutoffs;
- frozen M057 evaluation reuse;
- frozen M058 scan/ranking reuse;
- frozen M059 trade-plan gating reuse;
- frozen M060 position sizing reuse;
- next-bar-open entry timing;
- target-hit, stop-hit, same-bar ambiguity, no-entry, and time-exit handling;
- explicit transaction costs;
- deterministic replay.

## Intended scenarios

Using:

- `reference_window_size = 5`
- `holding_horizon_bars = 3`
- `account_equity = 10000`
- `risk_percent = 0.01`
- `entry_slippage_bps = 5`
- `exit_slippage_bps = 5`
- `fixed_commission_per_side = 0`

the dataset should yield the following historical outcomes:

| Cutoff | Instrument | Intended path |
| --- | --- | --- |
| `2026-08-10T13:45:00+00:00` | `AAPL` | approved trade -> approved position -> target hit |
| `2026-08-10T13:45:00+00:00` | `MSFT` | ranked candidate -> rejected trade plan (`REWARD_RISK_BELOW_MINIMUM`) |
| `2026-08-10T13:46:00+00:00` | `AMZN` | approved trade -> approved position -> stop hit |
| `2026-08-10T13:47:00+00:00` | `NVDA` | approved trade -> approved position -> same-bar stop/target ambiguity resolved conservatively as stop |
| `2026-08-10T13:48:00+00:00` | `GOOG` | approved trade -> approved position -> no entry because next-bar open gaps beyond target |
| `2026-08-10T13:48:00+00:00` | `TSLA` | approved trade -> approved position -> time exit at horizon close |

## Expected aggregate shape

The fixture should produce:

- `evaluated_cutoff_count = 4`
- `approved_trade_plan_count = 5`
- `approved_position_plan_count = 5`
- `simulated_trade_count = 5`
- `executed_trade_count = 4`
- `win_count = 2`
- `loss_count = 2`
- `time_exit_count = 1`
- `no_entry_count = 1`

The resulting net PnL is intentionally small and not marketed as good or bad. The fixture exists to prove that M061 can measure historical behavior honestly, not to prove that the frozen strategy is investable.
