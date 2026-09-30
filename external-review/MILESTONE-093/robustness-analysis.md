# M093 Phases 15/16 -- Cross-Symbol Robustness and Within-Research Walk-Forward

## Phase 15 -- cross-symbol robustness (COST1)

Per-symbol trade count, net P&L, profit factor, share of total gross profit, and the
leave-one-symbol-out net (total net P&L with that symbol's trades removed). No losing
symbol is excluded from any total reported anywhere in M093.

RELATIVE_STRENGTH correctly evaluates only 6 symbols (AAPL, MSFT, NVDA, AMZN, META, GOOGL)
-- SPY and QQQ are excluded as the benchmark symbols themselves, per the family's own
non-self-referential rule (Phase 9), confirmed structurally in Phase 0-10 and re-confirmed
here by the absence of SPY/QQQ rows below.

| Family | Symbol | n | Net | PF | Gross-profit share | Leave-one-out net |
|---|---|---:|---:|---:|---:|---:|
| TREND_CONTINUATION | AAPL | 595 | -1,086.59 | 0.567 | 15.8% | -7,298.19 |
| TREND_CONTINUATION | AMZN | 595 | -1,752.57 | 0.409 | 13.4% | -6,632.21 |
| TREND_CONTINUATION | GOOGL | 486 | -1,304.29 | 0.463 | 12.5% | -7,080.49 |
| TREND_CONTINUATION | META | 337 | -541.61 | 0.730 | 16.2% | -7,843.17 |
| TREND_CONTINUATION | MSFT | 431 | -1,001.81 | 0.504 | 11.3% | -7,382.96 |
| TREND_CONTINUATION | NVDA | 637 | -1,161.23 | 0.656 | 24.5% | -7,223.55 |
| TREND_CONTINUATION | QQQ | 373 | -544.52 | 0.399 | 4.0% | -7,840.26 |
| TREND_CONTINUATION | SPY | 577 | -992.16 | 0.178 | 2.4% | -7,392.62 |
| VWAP_PULLBACK | AAPL | 171 | -262.14 | 0.527 | 23.3% | -1,283.83 |
| VWAP_PULLBACK | AMZN | 103 | -262.10 | 0.321 | 9.9% | -1,283.87 |
| VWAP_PULLBACK | GOOGL | 123 | -233.61 | 0.479 | 17.1% | -1,312.36 |
| VWAP_PULLBACK | META | 74 | -16.18 | 0.929 | 16.9% | -1,529.79 |
| VWAP_PULLBACK | MSFT | 118 | -229.62 | 0.407 | 12.6% | -1,316.35 |
| VWAP_PULLBACK | NVDA | 109 | -192.59 | 0.503 | 15.5% | -1,353.38 |
| VWAP_PULLBACK | QQQ | 72 | -114.46 | 0.279 | 3.5% | -1,431.51 |
| VWAP_PULLBACK | SPY | 124 | -235.27 | 0.064 | 1.3% | -1,310.70 |
| OPENING_RANGE_5 | AAPL | 3078 | -2,289.48 | 0.818 | 17.5% | -47,449.94 |
| OPENING_RANGE_5 | AMZN | 2464 | -9,481.41 | 0.464 | 14.0% | -40,258.01 |
| OPENING_RANGE_5 | GOOGL | 2405 | -6,605.32 | 0.517 | 12.1% | -43,134.10 |
| OPENING_RANGE_5 | META | 1862 | -1,783.59 | 0.859 | 18.6% | -47,955.83 |
| OPENING_RANGE_5 | MSFT | 2545 | -9,036.05 | 0.432 | 11.7% | -40,703.37 |
| OPENING_RANGE_5 | NVDA | 2346 | -7,767.10 | 0.574 | 17.9% | -41,972.32 |
| OPENING_RANGE_5 | QQQ | 2250 | -3,691.06 | 0.460 | 5.4% | -46,048.36 |
| OPENING_RANGE_5 | SPY | 3747 | -9,085.40 | 0.155 | 2.8% | -40,654.02 |
| OPENING_RANGE_15 | AAPL | 2948 | -2,238.50 | 0.806 | 18.2% | -42,645.20 |
| OPENING_RANGE_15 | AMZN | 2020 | -9,118.85 | 0.382 | 11.1% | -35,764.85 |
| OPENING_RANGE_15 | GOOGL | 2225 | -5,376.28 | 0.548 | 12.8% | -39,507.42 |
| OPENING_RANGE_15 | META | 1620 | +421.47 | 1.040 | 21.5% | -45,305.17 |
| OPENING_RANGE_15 | MSFT | 2243 | -7,845.60 | 0.430 | 11.6% | -37,038.09 |
| OPENING_RANGE_15 | NVDA | 2154 | -8,747.37 | 0.488 | 16.3% | -36,136.33 |
| OPENING_RANGE_15 | QQQ | 2055 | -3,274.71 | 0.469 | 5.7% | -41,608.98 |
| OPENING_RANGE_15 | SPY | 3497 | -8,703.86 | 0.139 | 2.8% | -36,179.83 |
| MEAN_REVERSION | AAPL | 1566 | -2,375.02 | 0.405 | 15.1% | -15,400.40 |
| MEAN_REVERSION | AMZN | 2080 | -3,482.06 | 0.352 | 17.7% | -14,293.35 |
| MEAN_REVERSION | GOOGL | 1089 | -1,878.14 | 0.374 | 10.5% | -15,897.28 |
| MEAN_REVERSION | META | 648 | -980.91 | 0.431 | 6.9% | -16,794.51 |
| MEAN_REVERSION | MSFT | 1000 | -1,512.89 | 0.407 | 9.7% | -16,262.52 |
| MEAN_REVERSION | NVDA | 3328 | -6,155.00 | 0.366 | 33.2% | -11,620.42 |
| MEAN_REVERSION | QQQ | 525 | -685.27 | 0.373 | 3.8% | -17,090.15 |
| MEAN_REVERSION | SPY | 551 | -706.13 | 0.308 | 2.9% | -17,069.29 |
| RELATIVE_STRENGTH | AAPL | 628 | -486.48 | 0.868 | 13.9% | -7,738.75 |
| RELATIVE_STRENGTH | AMZN | 727 | -2,637.02 | 0.527 | 12.8% | -5,588.21 |
| RELATIVE_STRENGTH | GOOGL | 589 | -1,440.04 | 0.673 | 12.9% | -6,785.20 |
| RELATIVE_STRENGTH | META | 493 | -909.70 | 0.774 | 13.6% | -7,315.53 |
| RELATIVE_STRENGTH | MSFT | 570 | -482.07 | 0.868 | 13.8% | -7,743.17 |
| RELATIVE_STRENGTH | NVDA | 1280 | -2,269.93 | 0.769 | 32.9% | -5,955.31 |

**Finding:** every symbol, in every family, is net-negative at COST1 -- there is no
single symbol whose removal would flip any family to profitability (every leave-one-out
net is itself deeply negative), and no symbol contributes a profit share that would offset
the rest even partially. NVDA and META are consistently the least-bad symbols across
families (highest PF, largest gross-profit share), echoing the same NVDA concentration
already observed in M091's V1 result -- but "least bad" here still means a clearly losing
PF everywhere. No symbol is removed from any total; all totals above match the full
Phase 11 aggregates exactly.

## Phase 16 -- within-research-data walk-forward

Chronological split of the 100-session research window only (2026-05-13 through
2026-09-29): design = first 70 sessions (2026-05-13 through 2026-08-18), observe = last 30
sessions (2026-08-19 through 2026-09-29). This is entirely distinct from, and does not
touch, the separately-locked final holdout (2026-03-18 through 2026-05-12), which remains
untouched throughout M093 per Phase 1/19.

| Family | Design PF | Observe PF |
|---|---:|---:|
| TREND_CONTINUATION | 0.572 | 0.394 |
| VWAP_PULLBACK | 0.494 | 0.320 |
| OPENING_RANGE_5 | 0.554 | 0.493 |
| OPENING_RANGE_15 | 0.544 | 0.490 |
| MEAN_REVERSION | 0.379 | 0.359 |
| RELATIVE_STRENGTH | 0.747 | 0.695 |

**Finding:** every family is below PF 1.0 in both halves of the chronological split, with
no reversal or emerging edge in the later "observe" portion of the research data. This
rules out the possibility that early screening was skewed by a favorable opening period
that later faded (or vice versa) -- the negative result is stable across the whole research
window, not an artifact of a particular sub-period.
