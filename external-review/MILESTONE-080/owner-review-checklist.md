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
| 3 | Every unrepresented economic component is named on every report | ⚠ *this row previously said "every excluded **cost**" and named `EXCLUDED_COST_COMPONENTS` — both corrected by Owner findings 2 and 4.* Now `UNREPRESENTED_ECONOMIC_COMPONENTS`, 8 items in three groups, structured field **and** limitation |
| 4 | The direction claim is honest | ⚠ *this row previously asserted "systematically more favourable than a real economic outcome" — **retracted**, that bound does not hold.* Now: unrecorded cash charges would normally reduce a raw result; taxes/dividends/corporate actions move either way; spread/slippage are **not claimed excluded at all** |
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

---

## Owner review correction pass — what to re-check

| # | Check | Where |
|---|---|---|
| 1 | No `Decimal` operation remains in the arithmetic or rendering | `_scaled_price`, `_money_from_scaled`; `test_the_module_performs_no_decimal_arithmetic_at_all` |
| 2 | The boundary result is exact to the last digit | `-214748364699999999995705.032706`, in unit **and** PostgreSQL suites |
| 3 | The result cannot move with the caller's context | six precisions and two rounding modes, object + text + JSON |
| 4 | Raw PostgreSQL rows recomputed independently agree | `test_m080_boundary_row_arithmetic_is_exact_against_raw_sql` |
| 5 | Rendering cannot re-round a >28-digit value | `test_money_rendering_does_not_round_a_value_beyond_the_context_precision` |
| 6 | No global Decimal state is mutated and `prec` is not raised | no `getcontext()` call exists in the module |
| 7 | The component list is no longer named for costs | ⚠ *this row named `EXCLUDED_ECONOMIC_COMPONENTS`; **superseded by finding 4** — the constant is now `UNREPRESENTED_ECONOMIC_COMPONENTS` and the field/JSON key `unrepresented_economic_components`* |
| 8 | Dividends / corporate actions / taxes are not classified as costs | ⚠ *this row named `EXCLUDED_NON_DIRECTIONAL_COMPONENTS`; **superseded by finding 4** — the two-way split is now three-way, and these three are `CONTEXT_DEPENDENT_COMPONENTS`* |
| 9 | No universally-favourable-bias claim survives anywhere | four phrasings checked across banner, limitations and text |
| 10 | The original broker / P&L / profit guards still hold | 13 tokens and six banner phrases re-asserted at the boundary case |
| 11 | E04 / E06 / E07 / E12 / H08 are retracted, not rewritten | `hostile-design-review.md` |

## Why the API name changed before freeze

`excluded_cost_components` was a field name that **makes a claim**, and the claim
was false. Renaming it costs nothing; freezing it would have preserved a
misleading contract permanently. Owner finding 4 then showed that even
`excluded_economic_components` overclaimed, because "excluded" asserts absence
and spread/slippage may be **embedded** in the asserted prices. The frozen-facing
name is now `unrepresented_economic_components`.

---

## Owner review — final honesty reconciliation pass

| # | Check | Where |
|---|---|---|
| 1 | M076 persists **no** currency, quote-currency or denomination column | verified against the migration, the domain event and the repository; `test_m076_persists_no_currency_field_at_all` |
| 2 | No denomination is invented for any symbol | `AAPL`, `XAU`, `BTC`, `ZZZZ` all produce no currency token outside explicit denials |
| 3 | The denomination limitation rides on **every** report shape | closed, open, partial, empty and withheld — parametrised |
| 4 | `instrument_symbol` is denied as a currency authority | stated in the limitation and asserted |
| 5 | A future milestone cannot read two entries as a same-currency aggregate | the limitation says so, and no aggregate field exists |
| 6 | Spread and slippage are **not** claimed excluded | `NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS`; "may already be embedded" |
| 7 | They are absent from the group that carries a direction | asserted against the directional limitation line |
| 8 | No active surface says "costs excluded" | banner, limitations, text and JSON all checked |
| 9 | The exact-arithmetic correction survived untouched | boundary result re-asserted |
| 10 | The M079 firewall survived untouched | equality under a post-cutoff row re-asserted |
