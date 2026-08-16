# M080 — Reality Gate

> **Corrected twice after Owner review.** A later pass found two further honesty
> defects: **no currency denomination authority exists in M076**, and
> **spread/slippage cannot be claimed excluded** because the prices are the
> operator's own and may already embed them. Both are corrected below.

> **Corrected after Owner review.** This document previously claimed that every
> excluded component is a cost and therefore that every M080 result is
> "systematically more favourable than a real economic outcome". **That claim is
> false and is retracted** — dividends, corporate actions and tax effects are not
> costs and can move the real outcome in either direction. The corrected
> statement is below; the superseded passage is struck through in place.

## The question this milestone must answer exactly

**M080 emits money. What EXACTLY is it?**

It is the **arithmetic difference between what the operator asserted they
received on exit and what they asserted they paid on entry, for the quantity
they assert they exited** — computed only from assertions the ledger records as
having been recorded by the knowledge cutoff.

Formally:

```
asserted_round_trip_result
    = Σ(exit quantity × that exit's asserted price)
    − (exited quantity × the asserted entry price)
```

Every input is a number a human typed into a ledger. Not one is a measurement.

## What it is NOT

| Not | Why not |
|---|---|
| broker realized profit or loss | there is no broker in this platform, and nothing is reconciled against one |
| verified profit | nothing verifies the assertion |
| an actual execution result | M076's own banner: not an execution, not a fill |
| actual cash proceeds | no cash movement is recorded anywhere |
| investment performance | no aggregate, no percentage, no time-weighting exists |
| a market return | no market price is read |
| a tax result | no tax rule, lot-matching or jurisdiction exists |
| evidence a trade occurred | the ledger records assertions, not events |
| advice | none given |

## Is the word "P&L" used?

**No — and that is enforced, not merely intended.** The bare token `PNL`, along
with `PROFIT`, `REALIZED`, `VERIFIED`, `EXECUTED`, `FILLED`, `WIN_RATE`,
`EXPECTANCY`, `BROKER_REALIZED_PNL`, `ACTUAL_PROFIT`, `VERIFIED_PROCEEDS`,
`MARKET_RETURN` and `EXECUTION_PNL`, appears in **no** status, field name, enum
value or JSON key. A test walks every one of those surfaces and fails on any
occurrence.

The phrase appears in exactly one place: the banner, saying what the result is
**not**.

There is a real collision worth naming. `realized_pnl`, `profit_factor` and
`maximum_realized_pnl_drawdown` **already exist** in this repository — in M062
validation studies, M063 robustness studies and M067 portfolio studies. Every one
of those is **simulated** P&L over historical bars. None touches an operator
assertion. M080 is a different kind of claim and deliberately shares none of
that vocabulary.

## Unrepresented economic components — stated, not buried

⚠ **This section previously read "Costs — stated, not buried" and asserted a
universal favourable bias.** Retracted (finding 2).
⚠ **It then read "Excluded economic components" and placed spread and slippage
among the frictions.** Also retracted (finding 4): M080 cannot establish that
they are excluded at all. The superseded table is struck through and preserved.

> ~~| commissions | no | **excluded** | would normally reduce a raw result |~~
> ~~| spread | no | **excluded** | would normally reduce |~~
> ~~| slippage | no | **excluded** | would normally reduce |~~
> ~~| exchange and regulatory fees | no | **excluded** | would normally reduce |~~
> ~~| financing and borrow cost | no | **excluded** | would normally reduce |~~
> ~~| taxes | no | **excluded** | either direction |~~
> ~~| dividends | no | **excluded** | either direction |~~
> ~~| corporate actions | no | **excluded** | either direction |~~

**The current, three-way statement:**

| Group | Component | Stored by M076? | What may honestly be said |
|---|---|---|---|
| `UNREPRESENTED_CASHFLOW_COMPONENTS` | commissions | no | cash the ledger never records; including it would normally **reduce** a raw result |
| " | exchange and regulatory fees | no | same |
| " | financing and borrow cost | no | same |
| `CONTEXT_DEPENDENT_COMPONENTS` | taxes | no | **either direction** — jurisdiction- and context-dependent |
| " | dividends | no | **either direction** — a dividend on a long position *raises* the real outcome |
| " | corporate actions | no | **either direction** — splits, mergers and spin-offs alter quantity or basis |
| `NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS` | spread | no | **NOT claimed excluded** — the asserted prices are the operator's own executions and may already embed it |
| " | slippage | no | **NOT claimed excluded** — same |
| — | current market price | no | **no unrealized figure is computed** |

The union is emitted as a **structured field**
(`unrepresented_economic_components`) on every report, and the three groups are
named separately in the limitations so their different epistemic status cannot be
flattened.

**What the artifact now says, and all it may say:**

- the arithmetic **does not represent** the listed economic components;
- it is therefore **NOT a complete economic outcome**;
- the **direction of the total omitted effect is NOT generally knowable**;
- unrecorded cashflows — commissions, exchange and regulatory fees, financing and
  borrow cost — would normally **reduce** a raw result;
- taxes, dividends and corporate actions can alter interpretation in **either**
  direction and are not represented;
- spread and slippage are **not claimed to be excluded**: they may already be
  embedded in the asserted prices, and M076 stores no benchmark, quoted, intended
  or arrival price against which any execution effect could be measured;
- every value is in **unspecified asserted price units** with no currency
  denomination established by this milestone.

~~Every result is systematically more favourable than any real economic
outcome.~~ **RETRACTED — no universal bound in either direction is claimed.**

## Exactness — corrected after Owner review

The result must be **exact for every price/quantity combination M076
persistence admits**, and independent of the caller's `Decimal` context. It was
not: `Decimal(quantity) * price` and `_money()`'s `normalize()` both evaluate
under the ambient context, so at `quantity = 2147483647` and the maximum price
the exact 30-digit product was silently rounded to 28 significant digits.

All monetary arithmetic is now carried in **Python integers scaled to 10⁻⁶**,
which is exact by construction and context-free, and rendering performs no
`Decimal` operation at all. Proven at the boundary:

```
2147483647 @ 99999999999999.999999  ->  exited at 0.000001
result: -214748364699999999995705.032706      (30 significant digits, no loss)
```

identical under ambient precisions 1, 5, 9, 28 and 60 and under `ROUND_UP` and
`ROUND_FLOOR`, and matching an independent integer recomputation from the raw
PostgreSQL rows byte for byte.

## Denomination — there is none, and M080 says so

M076 persists `instrument_symbol`, `quantity` and `asserted_price`. It persists
**no** currency, quote currency, price currency or denomination column —
verified against the migration, the domain event and the repository adapter.

M080 therefore has **no authority to call any figure USD, EUR or anything
else**, and does not. Every value is arithmetic in the **same unspecified
asserted price units** the ledger carries. A symbol is not a denomination: it
identifies an instrument, not the units its price is quoted in.

Two consequences are stated explicitly on every report, including the empty and
the withheld ones:

- a value here must **not** be read as any currency on M080's authority;
- two values must **not** be assumed to share a denomination merely because both
  appear in this report — which is the trap a future aggregating milestone would
  otherwise fall into.

## Spread and slippage — not claimed excluded

⚠ **The previous pass placed spread and slippage among "frictions" whose
omission makes a result look better. That was too strong and is retracted.**

M080's arithmetic uses the operator's **own asserted execution prices**. If those
are what the operator says they actually paid and received, spread and slippage
effects **may already be embedded in them**. M076 stores no benchmark price, no
quoted bid or ask, no intended price and no arrival price, so there is nothing to
measure an execution effect against.

Whether they are absent, embedded, partly embedded or independently attributable
is **not determinable from this data**, and M080 claims none of those.

## Could a reasonable user misread the output?

| Misreading | Prevented by |
|---|---|
| "this is my profit" | the banner's first clause calls it arithmetic on assertions; the field is `asserted_round_trip_result`; no field contains `profit` |
| "this is what I actually made after costs" | the eight excluded components are listed on every report, partitioned into frictions and non-directional components, with the explicit statement that this is **not a complete economic outcome** and that the total direction is **not generally knowable** |
| "this position made 120" when 6 of 10 units are still open | **implementation review R01** — the result line itself now reads `on the 4 exited unit(s) ONLY; 6 still open and NOT covered` |
| "this closed position made −60" when 4 units are unaccounted for | the line reads `on ONLY the 6 exited unit(s) visible here … so this is NOT the whole position's result` |
| "my portfolio made X" | **no aggregate exists.** Not omitted by oversight — an aggregate is a performance claim this milestone has no authority to make |
| "I'm up 12%" | **no percentage exists**, for the same reason |
| "nothing was exited, so I broke even" | nothing exited emits **no arithmetic at all**, never a zero |
| "the ledger is corrupt" | `UNRESOLVED_KNOWLEDGE_SEQUENCE` carries M079's exact meaning: unknowable from this cutoff's evidence alone |
| "this was true historically" | both cutoffs are echoed in every rendering, and the firewall is proven over two databases |

## The safeguards are structural, not textual

The mission's rule is that no disclaimer may rescue misleading semantics. M080's
guarantees are computations and absences, not wording:

- **The firewall is a predicate.** `_report_from_known_evidence` is never given
  the unfiltered events, so a post-cutoff assertion cannot influence any figure.
- **The partial-result guard is arithmetic.** The entry cost is computed on the
  *exited* quantity, so a partial exit cannot be extrapolated even by accident.
- **The completeness guard is a reconciliation.** `opened − exited − still_open`
  is checked from visible evidence, so a coherent fold cannot silently hide
  missing exits.
- **The overclaiming guards are absences.** No aggregate, no percentage, no
  unrealized figure and no market price exist to be misused.
- **The exactness guarantee is integral, not contextual.** No `Decimal`
  operation appears in the arithmetic or the rendering, so no ambient precision
  or rounding mode can alter a published figure.

## One thing worth stating plainly

This milestone makes the platform emit a money-shaped number for the first time
from operator assertions. That is a real increase in what it can be *misread* to
mean, and no amount of banner text fully removes that risk. What has been done
instead is to make every safeguard structural, to name the unrepresented economic
components on every report — with a direction stated only where a direction is
actually knowable, and none claimed for spread and slippage — to state on every
report that the value carries **no established currency denomination**, and to
make the number state its own coverage at the point it is read.

> ⚠ *This paragraph previously read "to name the excluded costs and the direction
> of their bias". Retracted by findings 2, 3 and 4.* A previous pass's evidence
> recorded this paragraph as already fixed; **that record was itself wrong** —
> the paragraph was still live until this pass. The mistaken record is corrected
> in the stale-claims table of `hostile-implementation-review.md`.

Whether the platform should emit such a number at all remains the owner's call.
This milestone implements it because the mission asked the authorization question
directly and supplied the honest vocabulary; it does not assume the answer for
any milestone beyond this one.
