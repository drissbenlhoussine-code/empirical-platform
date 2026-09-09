# MILESTONE-084 — Scope and Design

## 1. The flow, and why it has exactly these steps

```
configuration (versioned)
    └─> evaluation context  ──consumes──> M083 evidence watermark
            └─> proposal  ──or──>  one closed NO_TRADE reason
                    └─> human decision (APPROVE | REJECT | CANCEL)
                            └─> approved order intent  [NOT_SUBMITTED, terminal]
```

Five steps, five tables, one human decision in the middle. Nothing spans the
decision: there is no handler, no repository method and no CLI command that
evaluates and approves in one call, because a convenience that spanned that
gap would be an approval nobody made.

## 2. The four hard product invariants

Unleveraged, long-only, intraday-only, preparation-mode. These are not
switches that happen to default safely — they are refused at construction and
refused again by CHECK constraints:

| Invariant | Domain | Database |
|---|---|---|
| `maximum_leverage` exactly 1 | `ValueError` at construction | `ck_operator_trading_configuration_unleveraged` |
| short selling forbidden | `ValueError` | `ck_operator_trading_configuration_long_only` |
| overnight positions forbidden | `ValueError` | `ck_operator_trading_configuration_intraday_only` |
| account mode PREPARATION | `ValueError` | `ck_operator_trading_configuration_preparation_only` |

"Exactly 1", not "at most 1". A configuration cannot express a different
capital model at all, in either direction.

## 3. Why the database repeats what the domain already refuses

The domain refusal is the legible one a developer meets first. The database
refusal is the one that still applies to a psql session, a repository written
in a hurry, or a migration-era script that never imported the domain. Neither
is decoration, and the pair is stated in `current-authority.json` so a
reviewer can see which rules have both layers and which have only one.

The rules the database carries on its own account:

- **Order terms are immutable after insert.** `status` is the only column any
  statement may change. This is what makes the approval fingerprint binding
  durable rather than advisory: the terms a human approved cannot be edited
  underneath the approval, so a stale approval cannot come to authorize a
  different order.
- **The state machine is closed and checked on UPDATE.** Only PREPARED has
  outgoing edges. A rejected proposal cannot be revived.
- **A decision is admitted only while its proposal is still PREPARED**, and
  only carrying that proposal's current fingerprint and version.
- **One decision per proposal, one intent per proposal**, by unique
  constraint — not by application convention.
- **An intent's terms are re-derived** from the proposal and decision it
  cites. An intent that disagrees with either by one field is refused.

## 4. The caller cannot size the trade

`evaluate_trade_proposal` accepts no desired quantity, no desired price and no
risk verdict. Quantity is derived from cash above the reserve, the per-trade
capital cap, the percentage cap and the lot size, then floored. A caller who
wants a different size must change the configuration, which is versioned and
auditable.

Twenty-six risk checks run on every evaluation. Each returns PASSED, FAILED or
UNKNOWN, and **UNKNOWN is never treated as PASSED** — a check that could not be
evaluated is a reason not to trade, and the engine says which one. A proposal
exists only when every applicable check passed, and the type refuses to be
constructed otherwise.

When more than one rule fails, exactly one reason is reported, chosen by an
explicit precedence tuple rather than by set iteration order. A refusal that
varied run to run would be a refusal nobody could act on.

## 5. What was corrected during the work, and why

Three things were found by tests and fixed at the root rather than worked
around. They are listed because how a defect was resolved says more than
whether one was found.

**The liquidation check was vacuous.** It compared the mandatory liquidation
deadline against the evaluation instant — but a valid configuration already
requires the deadline to follow the last permitted entry, so within the entry
window the check could never fail. It now requires the *whole proposal
lifetime* to fit before the deadline, which is both reachable and the property
that actually matters: a proposal still approvable after the deadline
authorizes an entry that cannot be closed intraday, which is an overnight
position.

**The fingerprint disagreed with itself across a database round trip.**
`NUMERIC(20,8)` returns `200.10000000` for a price stored as `200.10`, and the
digest formatted the `Decimal` as given, so every re-read proposal looked
tampered with. The digest now normalizes each amount first: it depends on the
value, not on the scale the column happened to return. Display formatting is
deliberately a *different* rule — a person reading a price wants `200.10`, not
`200.1`.

**Risk checks were not persisted at all**, so a proposal read back from the
database violated its own "every check passed" invariant with an empty tuple.
The invariant was not weakened. The checks are now stored in an append-only
child table, ordered, constrained to PASSED — because "which gates did this
pass, and what did each one see" is the question an operator asks months later,
and an answer that has to be re-derived from code that has since changed is not
an answer.

## 6. Market inputs are operator-asserted

This milestone connects to no broker and no market-data vendor. Every snapshot
a proposal is evaluated against reaches the platform because a human wrote it
into a file — the same shape MILESTONE-076 uses for operator-asserted position
events. The platform records the assertion and checks it against the operator's
own configured limits. It does **not** verify that the asserted quote is what
the market showed, and nothing in this milestone should be read as though it
did.

One consequence, stated plainly rather than discovered later: a snapshot the
operator will not assert as `REAL_TIME` always produces
`MARKET_DATA_NOT_REAL_TIME`. A proposal built on data nobody will claim is live
is not a proposal this product will make.

## 7. Boundaries kept, and the precedent for each

- **Entrypoints reach domain types through `usecases`, not directly.** The
  MILESTONE-083 REV-005 precedent: widening the architecture allowlist to give
  entrypoints a direct edge to `decision_candidate` would be a real loosening
  of the boundary in exchange for an import statement.
- **Reads fail closed rather than coerce.** The MILESTONE-083 AUD-001 lesson:
  a stored value of the wrong type, or a status outside a closed enumeration,
  raises instead of being mapped onto a plausible-looking one.
- **Repository control flow is unit-tested offline.** The MILESTONE-083
  REV-004 precedent: code reachable only through a live database is code
  untested wherever that database is absent, as it is in CI.
- **Immutability is described narrowly.** Row-level UPDATE/DELETE refusal under
  the installed triggers, exactly as M082 and M083 worded it. TRUNCATE, DDL and
  superuser paths remain, and the authority contract says so.

## 8. Deliberately not built

- No broker or market-data connection of any kind.
- No submission, scheduling, retry or background execution.
- No exchange calendar. `exchange_calendar_policy` records which policy the
  operator believes applies and enforces nothing; the liquidation check
  compares local times only.
- No persistence of NO_TRADE outcomes. These tables are not a record of every
  evaluation performed, and the authority contract states that limitation.
- No `PROJECT_CHECKPOINT.md` change, no merge, no freeze. This is a candidate.
