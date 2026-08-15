# M078 — Reality Gate

## What M078 actually proves

For one research session and one explicit timestamp, **what the operator's own
ledger records against that session's approved plans** — an open assertion, a
closed one, or nothing — and which open assertions this session's plans do not
account for.

That is all. It is a statement about **records**, not about markets, money or
conduct.

## What M078 does not prove

It does not prove that any trade occurred; that any order was executed or
filled; that any position is broker-confirmed; that any holding is real; what
anything is worth; whether anything was profitable; or that a recommendation
caused a position. It proves nothing about what the operator did in the world —
only about what they wrote down.

**It especially does not prove that a plan with no record was ignored.**

## Could a reasonable user misread the output?

| Misreading | Prevented by |
|---|---|
| broker-confirmed | no broker concept exists; the banner denies it; `ASSERTED_` prefixes every status |
| executed / filled | those words are absent from every closed vocabulary, enforced by a parametrised test |
| profitable | **no monetary value exists anywhere in the output** — there is nothing to read as profit |
| current market truth | no price is read at all |
| P&L | structurally impossible: no arithmetic over prices is performed |
| investment advice | denied in the banner; no recommendation is produced |
| guaranteed outcome | no outcome of any kind is claimed |
| **"the operator ignored my research"** | the status is named `NO_ASSERTED_POSITION_RECORDED`, never `NOT_ACTED_UPON`; a caveat is emitted unconditionally and asserted by test |
| "this position was unauthorized" | `CITES_NO_PLAN` is a citation fact; the words unauthorized, discretionary and off-plan appear nowhere |
| "the operator followed the plan" | no `FOLLOWED` / `ADHERENCE` / `COMPLIANCE` vocabulary exists, enforced by test |

## The strongest safeguard is structural, not textual

The mission's rule is that no disclaimer may rescue misleading semantics. M078
does not rely on its banner: it **emits no monetary value of any kind**, so
accidental valuation, accidental P&L and accidental profitability claims are
not discouraged — they are impossible. A test walks every field of every
returned dataclass and rejects any `Decimal` or money-named field, and
integration tests persist six distinct asserted prices and prove none reaches
any rendering.

The second safeguard is the same in kind: `NO_ASSERTED_POSITION_RECORDED` is a
statement about the record, not the operator, and the vocabulary that would
judge the operator does not exist in the codebase.

## An honest note on what this milestone did *not* take

M077's freeze record states that decision-versus-outcome evaluation was
deferred because "M076 asserts neither" market revaluation nor realized
proceeds. **The second half of that is inaccurate** — M076 validates and
persists an `asserted_price` on `CLOSED` and `REDUCED` events, so operator-
asserted exit prices already exist; nothing reads them.

That capability is therefore *available* and was still rejected, on honesty
rather than feasibility: subtracting an asserted entry from an asserted exit
produces a number that is substantively realized P&L, and renaming it would be
the exact failure the reality gate forbids. It is the owner's call to
authorize, not this mission's to assume.
