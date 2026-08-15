# M080 — Reality Gate

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

## Costs — stated, not buried

| Component | Stored by M076? | In the result? |
|---|---|---|
| commissions | no | **excluded** |
| spread | no | **excluded** |
| slippage | no | **excluded** |
| exchange and regulatory fees | no | **excluded** |
| taxes | no | **excluded** |
| dividends | no | **excluded** |
| corporate actions | no | **excluded** |
| financing and borrow cost | no | **excluded** |
| current market price | no | **no unrealized figure is computed** |

These are emitted as a **structured field** (`excluded_cost_components`) on every
report and named again in the limitations, because a reader must not have to
infer which costs are missing.

**The direction of the bias is stated:** every result is *systematically more
favourable* than any real economic outcome, because all of the omitted
components are costs. That sentence is on every report.

## Could a reasonable user misread the output?

| Misreading | Prevented by |
|---|---|
| "this is my profit" | the banner's first clause calls it arithmetic on assertions; the field is `asserted_round_trip_result`; no field contains `profit` |
| "this is what I actually made after costs" | the eight excluded components are listed on every report with the bias direction named |
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

## One thing worth stating plainly

This milestone makes the platform emit a money-shaped number for the first time
from operator assertions. That is a real increase in what it can be *misread* to
mean, and no amount of banner text fully removes that risk. What has been done
instead is to make every safeguard structural, to name the excluded costs and
the direction of their bias on every report, and to make the number state its
own coverage at the point it is read.

Whether the platform should emit such a number at all remains the owner's call.
This milestone implements it because the mission asked the authorization question
directly and supplied the honest vocabulary; it does not assume the answer for
any milestone beyond this one.
