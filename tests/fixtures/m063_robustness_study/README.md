# MILESTONE-063 broad historical robustness fixture

**Synthetic, deterministically generated, fixed local test data. Not live market
data. Not downloaded historical data. Not a profitability claim.**

`synthetic_broad_robustness_dataset_bundle.json` exists solely to exercise the
frozen M057-M062 stack across a materially broader walk-forward sequence with
explicit universe authority and post-hoc regime labeling. It preserves one
canonical one-minute timestamp grid across six instruments (`AAPL`, `AMZN`,
`GOOG`, `MSFT`, `NVDA`, `TSLA`) from `2026-08-10T13:00:00+00:00` through
`2026-08-10T15:39:00+00:00`.

The fixture is fixed local evidence only:

- `dataset_bundle_id = DATASET-6301`
- `dataset_bundle_version = "1"`
- `source_kind = FIXED_ROBUSTNESS_FIXTURE`
- `universe_id = UNIVERSE-6301`
- `universe_version = "1"`
- `universe_membership_model = FIXED_SYNTHETIC_UNIVERSE`
- `survivorship disclosure = SURVIVORSHIP_BIAS_NOT_ADDRESSED`

SHA-256 of the exact committed file:

```text
765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd
```

### Byte-seal reconciliation (owner-authorized, M074 closure)

This value was previously recorded as
`ca98478ce6156f41c4535eaa040fd3e161229a71acd771a477ee9648ac3dd506`. That
digest was taken from a Windows working-tree materialization of this file
(CRLF), not from the committed blob (LF, git object `800ecb19`), so it
validated only on a checkout with `core.autocrlf=true` and failed on every
clean LF checkout, including CI.

The file's bytes were **not** changed: the committed blob is byte-for-byte
what M063 originally froze. Only the recorded digest was corrected, and
`.gitattributes` now pins this path with `-text` so every platform
materializes those exact bytes. The two byte forms were proven to differ
only in line endings and to yield identical M063 results across every
metric, window, and derived backtest run. See
`MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md`.

## Intended scope

The fixture is intentionally broader than M062's holdout bundle. It exists to
prove:

- deterministic walk-forward sequencing;
- first-class dataset and universe authority;
- strict late-window isolation;
- caller-order-independent window semantics;
- descriptive post-hoc regime labeling;
- transparent cross-window robustness reporting;
- deterministic replay;
- raw-SQL-verifiable persistence.

It does **not** exist to prove profitability, live readiness, or survivorship
bias removal.

## Canonical shape

- 6 instruments
- 160 bars per instrument
- 960 total bars
- 10 windows
- 16 bars per window (`warmup=5`, `scoring=8`, `buffer=3`)
- 80 scored cutoffs in total

Canonical window layout (0-based per instrument):

| Window | Full range | Warmup | Scoring | Buffer |
| --- | --- | --- | --- | --- |
| `W01` | 0-15 | 0-4 | 5-12 | 13-15 |
| `W02` | 16-31 | 16-20 | 21-28 | 29-31 |
| `W03` | 32-47 | 32-36 | 37-44 | 45-47 |
| `W04` | 48-63 | 48-52 | 53-60 | 61-63 |
| `W05` | 64-79 | 64-68 | 69-76 | 77-79 |
| `W06` | 80-95 | 80-84 | 85-92 | 93-95 |
| `W07` | 96-111 | 96-100 | 101-108 | 109-111 |
| `W08` | 112-127 | 112-116 | 117-124 | 125-127 |
| `W09` | 128-143 | 128-132 | 133-140 | 141-143 |
| `W10` | 144-159 | 144-148 | 149-156 | 157-159 |

No bar belongs to more than one window. Mutating only `W10` must leave
`W01`..`W09` unchanged.

## Canonical results

Using:

- `reference_window_size = 5`
- `holding_horizon_bars = 3`
- `account_equity = 100000`
- `risk_percent = 0.01`
- frozen M057-M061 strategy/risk/sizing/execution/cost policies

the canonical study should yield:

- `window_count = 10`
- `total_evaluated_cutoff_count = 80`
- `total_simulated_trade_count = 59`
- `total_executed_trade_count = 59`
- `positive_net_pnl_window_count = 7`
- `negative_net_pnl_window_count = 3`
- `positive_total_r_window_count = 7`
- `negative_total_r_window_count = 3`
- `classification = ROBUSTNESS_EVIDENCE_MIXED`

Canonical extremes:

- best net-PnL window: `W08` -> `1245.30999130`
- worst net-PnL window: `W07` -> `-293.055420`
- best total-R window: `W05` -> `18.24646990892242838850180340`
- worst total-R window: `W06` -> `-7.737888034172596900624932265`

Canonical totals:

- all-window net PnL = `3159.55176410`
- all-window total R = `33.84096575766330478385285292`
- excluding-best-window net PnL = `1914.24177280`
- excluding-best-window total R = `15.59449584874087639535104952`

Canonical concentration:

- largest positive-window share of positive PnL =
  `0.3481136196652371557486284593`
- largest negative-window share of absolute negative PnL =
  `0.7014969015918107753748046817`

Canonical post-hoc regime breakdown:

| Regime | Windows | Executed trades | Net PnL total | Total R total |
| --- | --- | --- | --- | --- |
| `HIGH_VOLATILITY` | 4 | 24 | `1763.01930780` | `31.44137038984579508964519536` |
| `NORMAL_VOLATILITY` | 3 | 18 | `935.62955130` | `8.570505275741854650543960310` |
| `LOW_VOLATILITY` | 3 | 17 | `460.902905` | `-6.170909907924344956336302749` |

These are descriptive historical fixture results only. They do not prove an
edge, profitability, or live deployment readiness.
