# MILESTONE-058 market-scan fixture

**Synthetic, hand-authored. Not live or historical market data.** Exists
solely to exercise the M058 trading opportunity scanner deterministically.

`synthetic_6instrument_scan_universe.json` -- six instruments (AAPL, MSFT,
GOOG, AMZN, NVDA, TSLA), each a six-bar `ONE_MINUTE` window sharing an
identical five-bar reference set (`reference_high = 100.50`,
`reference_average_volume = 1012`) and a common evaluation cutoff
(`2026-08-10T13:45:00+00:00`), differing only in their evaluation bar and
resulting `decision_candidate_governance_id`. Consumed via
`run_trading_opportunity_scan`'s universe-fixture format.

## Expected results (computed by hand before running any code)

| Instrument | close | volume | decision | breakout_strength | volume_strength | score |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | 101.10 | 1600 | LONG_CANDIDATE | 0.6/100.50 | 1600/1012 | ~1.586998 |
| MSFT | 100.40 | 900  | NO_TRADE (price fails, volume fails) | -- | -- | -- |
| GOOG | 100.30 | 800  | NO_TRADE (price fails, volume fails) | -- | -- | -- |
| AMZN | 103.00 | 3000 | LONG_CANDIDATE | 2.5/100.50 | 3000/1012 | ~2.989303 |
| NVDA | 102.00 | 2000 | LONG_CANDIDATE | 1.5/100.50 | 2000/1012 | ~1.991210 |
| TSLA | 102.00 | 2000 | LONG_CANDIDATE (identical to NVDA -- deliberate tie) | 1.5/100.50 | 2000/1012 | ~1.991210 |

- `total_instruments = 6`, `candidate_count = 4`, `no_trade_count = 2`.
- Ranked order (score descending, symbol ascending on ties):
  1. AMZN (~2.989303) -- the non-trivial comparison: clearly ahead of the
     NVDA/TSLA pair on both breakout and volume strength, not merely a
     larger digit count.
  2. NVDA (~1.991210) -- tie winner: NVDA < TSLA alphabetically.
  3. TSLA (~1.991210) -- tie loser, same score as NVDA to full Decimal
     precision (identical measurements).
  4. AAPL (~1.586998) -- lowest-ranked legitimate candidate.
- MSFT and GOOG never appear in `ranked_opportunities`, but remain present
  (with `rank=None`, `score=None`) in `scan.evaluations` and are each fully
  explained by their own persisted `DecisionCandidate`.
