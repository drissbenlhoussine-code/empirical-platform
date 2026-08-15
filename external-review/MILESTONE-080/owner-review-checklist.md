# M080 — Owner Review Checklist

## The decision this milestone asks you to make

M080 emits a **money-shaped number derived from operator assertions** — the
first the platform has produced outside historical simulation. The mission asked
whether that is now authorized and supplied honest vocabulary; this branch
implements it under that reading. **Whether the platform should emit such a
number at all remains yours to confirm.**

## What to check, and where

| # | Check | Where |
|---|---|---|
| 1 | The number is named for what it is | `asserted_round_trip_result`; §7 and §23 of the design; `reality-gate.md` |
| 2 | No forbidden vocabulary anywhere | `test_no_forbidden_token_appears_in_any_closed_vocabulary` and the JSON-key twin; 13 tokens including bare `PNL` |
| 3 | Every excluded cost is named on every report | `EXCLUDED_COST_COMPONENTS`, 8 items, structured field **and** limitation |
| 4 | The bias direction is stated | "systematically more favourable than a real economic outcome" |
| 5 | No unrealized figure for open quantity | no such field; `test_no_unrealized_value_is_computed_for_an_open_position` |
| 6 | No aggregate, percentage or win rate | `test_no_aggregate_result_across_positions_is_emitted` |
| 7 | A partial result cannot read as a whole one | implementation review **R01**; three distinct result lines |
| 8 | The derived-`CLOSED`-quantity hazard is handled | design review **T07**; `EXIT_QUANTITY_UNRECONCILED`; shortfall proven never negative over 1521 cutoff pairs |
| 9 | The M079 firewall is inherited whole | `_report_from_known_evidence` cannot reach post-cutoff rows; double-database proof |
| 10 | Frozen modules untouched | `changed-files.txt`; R-P07..P13 |
| 11 | Zero schema impact | no migration, no table, no column, no repository |
| 12 | Retractions and anomalies preserved | this package retains the once-observed M077 flake and two wrong probe assertions of mine |

## Three judgment calls I made rather than assumed

1. **Position-centric, not session-centric.** Composing M078's session audit
   would void an entire session's answer whenever one unrelated position's
   knowledge-filtered prefix fails to fold — which knowledge filtering makes
   common. M080 reports the cited plan as metadata and leaves the session join
   to M078. Design review **A03**.
2. **The unreconciled result is still shown**, labelled as covering only the
   visible exits, rather than withheld entirely. Withholding would lose real
   information; showing it unlabelled would be dishonest. §7 and R01.
3. **No aggregate at all.** The most requested next thing is a portfolio total,
   and it is deliberately absent because it is a performance claim M080 has no
   authority to make.

## What would change my recommendation

If you judge that an operator-asserted monetary figure should not exist in the
platform at all, the honest fallback is candidate **E** from the ranking — the
same lifecycle reconstruction with the arithmetic removed. It scores 41 to
candidate A's 48, leaves the proved gap open, and unlocks nothing, but it emits
no money.
