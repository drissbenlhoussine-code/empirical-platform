# M081 - Reality Gate

Answered exactly, in the order the mission asked.

## What does M081 prove?

That, for one position, the operator's own asserted exit prices imply an exact
rational ratio of arithmetic result to asserted entry cost, on the quantity they
assert they exited, computed only from evidence the ledger records as having been
recorded by the knowledge cutoff.

It proves nothing about markets, money, or whether any trade occurred.

## What is the unit / dimension?

**Dimensionless**, and the cancellation is exact rather than approximate. Both
quantities are integer multiples of `10^-6` of the *same* unspecified asserted
price unit, for the *same* position, from the *same* events:

```
ratio = (R x 10^-6) / (C x 10^-6) = R / C
```

The scale cancels identically. The ratio is the exact quotient of two Python
integers.

## What is the denominator authority?

Frozen **M080** itself: `asserted_entry_cost_for_exited_quantity`, which M080
derives as `exited_quantity x asserted entry price`. Nothing else. In particular
**not** M060 plan sizing - see the rejected alternatives.

The denominator is **strictly positive on every reachable input**, because frozen
M076 enforces `asserted_price > 0` and quantities are positive integers. Division
by zero is unreachable, so there is no guard for it.

## Can outputs be compared across positions?

**Arithmetically, yes. Economically, not necessarily** - and the artifact says so
on every report.

Denomination cancels; economics does not. Two positions may differ in which
unrepresented components apply, and spread and slippage remain not separately
attributable. A larger ratio means the operator's asserted prices imply a larger
arithmetic ratio, and nothing more.

## Can they be aggregated?

**M081 emits no aggregate of ratio values. None** - no sum, mean, median,
distribution, best, worst, or count of positive ratios.

Justification for that refusal, since the mission requires any dimensionless
aggregate to be justified: averaging would weight a one-unit exit equally with a
ten-thousand-unit exit; a value-weighted average would require summing money
across unspecified denominations, which the M080 freeze forbids; and the
population is subject to selection effects M081 does not solve. So M081 does not
pretend to solve them.

Counts **by status** are emitted, because counting how many positions are fully
exited is a statement about evidence, not about outcomes.

## Can monetary values be summed?

**Not from anything M081 offers.** It emits no monetary value anywhere, at any
level: no field is named, typed or labelled as money, so there is no monetary
field to sum and no monetary total to form.

> ### ⚠ CORRECTED AFTER OWNER REVIEW (finding 2)
>
> This answer previously continued: ~~"the ratio is gcd-reduced, and reduction
> actively destroys the monetary magnitude: `500` over `1000` becomes `1/2`,
> from which `500` is unrecoverable."~~ **RETRACTED — that is not universally
> true.**
>
> When the two M080 scaled operands are already **coprime**, reduction changes
> nothing and the emitted pair **is** the original scaled pair. One unit opened
> at `0.000003` and closed at `0.000004` emits `1/3`, whose numerator and
> denominator are exactly the scaled result and scaled entry cost; M080's scale
> is publicly fixed at `10^-6`, so the money is readable straight off it.
>
> **M081 makes no promise of monetary non-recoverability.** The guarantee is
> **semantic**: no monetary field exists to aggregate, and no currency is
> established. gcd reduction is a normalisation so that `4/8` and `1/2` are one
> value — not a confidentiality boundary.

A reader who wants the money runs M080, which carries its own denomination
banner.

## Does the metric represent actual investment return?

**No.** It is arithmetic over unverified assertions about prices, with no
verification that any trade occurred, no broker record, no confirmation and no
market data.

## Does it include...

| Component | Included? |
|---|---|
| fees (commissions, exchange and regulatory) | **no** - unrepresented cashflow |
| financing / borrow cost | **no** - unrepresented cashflow |
| dividends | **no** - context-dependent, can move the real outcome either way |
| tax | **no** - context-dependent |
| corporate actions | **no** - context-dependent |
| spread / slippage attribution | **not claimed excluded at all** - the prices are the operator's own, so these may already be embedded in them, and M076 stores no benchmark, quoted, intended or arrival price to measure against |

The direction of the total omitted effect is **not generally knowable**, so no
universal bound in either direction is claimed - M080's finding 2 and finding 4,
inherited unchanged.

## Could a reasonable reader mistake it for ROI, profit %, win rate, performance or a verified return?

This was treated as the central risk, and three interface decisions follow from
it rather than from taste:

1. **It is never rendered as a percentage.** No `%` sign appears in the text or
   the JSON. A percentage reads as a return; a rational does not.
2. **The name states its own numerator and denominator** -
   `asserted_round_trip_result_to_entry_cost_ratio` - so it cannot be quoted
   without carrying what it is a ratio *of*.
3. **24 forbidden tokens** - `ROI`, `RETURN`, `TOTAL_RETURN`, `PROFIT_PERCENTAGE`,
   `PERFORMANCE`, `WIN_RATE`, `EXPECTANCY`, `YIELD`, `R_MULTIPLE` and the rest -
   are asserted absent from every field name, enum member and JSON key with
   word-boundary matching.

The banner additionally denies each reading in the artifact itself, and the
coverage phrase sits on the same line as the number, because the number is what
gets quoted.

## The one thing worth stating plainly

M080 made the platform emit money. M081 makes it emit something that *looks like
a performance figure* - a small unitless number that invites ranking. That is a
real increase in what can be misread.

What has been done instead of hoping: the unsafe comparison is made structurally
impossible rather than discouraged (no money is emitted at all), the safe one is
made exact rather than approximate, ordering is by identity so the artifact never
ranks anything itself, and the difference between arithmetic and economic
comparability is stated on every report rather than assumed understood.

Whether the platform should emit such a number at all remains the owner's call.
