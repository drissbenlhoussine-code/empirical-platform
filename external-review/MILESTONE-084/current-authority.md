# M084 — Decision-to-Approval Product Core

**Current authority, version 1.** Generated from `current-authority.json`; do not edit by hand.

This document is the single active statement of what MILESTONE-084 establishes. Every other file in this package is either current validation evidence or historical record, and neither carries authority.

## What one approved order intent proves

One intent, and the records it is derived from, together establish:

- the one versioned operator configuration that governed the evaluation, named by identity and version;
- one evaluation context bound to exactly one PERSISTED MILESTONE-083 evidence watermark, by foreign key -- a context for a watermark that does not exist cannot be stored;
- a consumed-receipt count and set digest READ FROM the loaded watermark's own stored set, neither of which the caller can supply or overstate;
- that one input set yields either exactly one proposal or exactly one closed NO_TRADE reason, selected by explicit precedence and reproducible across runs;
- that quantity, entry price and every risk verdict were DERIVED by the engine -- none of the three is a parameter it accepts;
- one SHA-256 fingerprint binding an approval to one exact set of order terms, so a changed quantity, price, symbol, order type or expiry cannot inherit an older approval;
- that a stored proposal's order terms cannot be edited afterwards -- `status` is the only column any statement may change;
- a closed proposal state machine in which only PREPARED has outgoing edges and every other status is terminal;
- at most one explicit decision per proposal, naming the operator who made it, admitted only while the proposal was still PREPARED;
- at most one order intent per proposal, whose terms the database re-derives from that proposal and that decision at insert;
- that every stored intent is NOT_SUBMITTED, and that this milestone provides no transition away from NOT_SUBMITTED -- not in code, where no method exists, and not in the database, where a CHECK constraint and an append-only trigger both refuse it;
- that no module of the package imports a client capable of placing, modifying or cancelling an order, enforced statically across every module rather than a named subset;

## What it does not prove

- **Not** that an asserted quote, account balance or session status matches what the market or a broker actually showed -- every market input is an operator assertion this milestone records and range-checks, never verifies.
- **Not** that the MILESTONE-082 receipts behind the bound watermark describe anything historically true.
- **Not** profitability, expected return, or advice of any kind.
- **Not** fillability, liquidity at the proposed price, or execution quality.
- **Not** that any broker would accept the intent or its terms.
- **Not** that an approved intent was, will be, or can be sent to any venue.
- **Not** paper-trading or live-trading readiness.
- **Not** regulatory, tax or reporting compliance in any jurisdiction.
- **Not** protection against DDL authority, `ALTER TABLE ... DISABLE TRIGGER`, TRUNCATE, DROP, or a superuser.
- **Not** cryptographic sealing against a determined attacker with database write access.
- **Not** any wall-clock chronology beyond the instants the caller supplied.
- **Not** that an instrument absent from the proposal table was never evaluated -- a NO_TRADE writes nothing.

## Database enforcement

| Property | Enforced |
|---|---|
| Only an unleveraged, long-only, intraday, PREPARATION-mode configuration is storable | **yes** |
| A stored proposal's order terms cannot be changed | **yes** |
| Only PREPARED has outgoing transitions; every other status is terminal | **yes** |
| A decision is admitted only against a still-PREPARED proposal, with that proposal's current fingerprint and version | **yes** |
| At most one decision exists per proposal | **yes** |
| At most one order intent exists per proposal | **yes** |
| An intent's terms are re-checked against the proposal and decision it cites | **yes** |
| `submission_state` accepts only NOT_SUBMITTED | **yes** |
| Decisions, intents and risk-check evidence refuse row-level UPDATE and DELETE | **yes** |
| An evaluation context requires an existing MILESTONE-083 watermark row | **yes** |
| DDL authority, `DISABLE TRIGGER`, TRUNCATE, DROP, superuser | **no** |

## Structural limitations

- Row-level UPDATE/DELETE refusal is exactly that. TRUNCATE is statement-level and a row trigger does not intercept it; DROP TABLE, DROP TRIGGER, `ALTER TABLE ... DISABLE TRIGGER`, `session_replication_role = replica` and superuser mutation all remain possible. This must not be described as absolute database immutability.
- Market inputs are operator-asserted. This milestone connects to no broker and no market-data vendor: a human writes the observations down, and the platform records and range-checks them without verifying them.
- The content fingerprint is a change detector and an approval binding. It is not a signature and offers no protection against an attacker who can write to the database.
- Risk-check evidence is stored but deliberately excluded from the fingerprint: a proposal that moves from PREPARED to APPROVED is the same order, and making the digest depend on diagnostic text would break that.
- A NO_TRADE is returned and not persisted, so these tables are not a record of every evaluation that was performed.
- The engine reads no clock. Every instant it records was supplied by its caller, and the record carries no independent evidence of when anything happened.
- The liquidation-deadline check compares local times in the operator's configured timezone. It consults no exchange calendar and knows nothing of holidays or shortened sessions; `exchange_calendar_policy` records which policy the operator believes applies, and enforces nothing.

## Intended future use

- A future milestone may submit an intent to a paper account. It is not started.
- Such a milestone must add a submission-state transition explicitly, in the open, because none exists here to inherit.
- MILESTONE-083's watermark authority is CONSUMED by this milestone and is neither replaced nor strengthened by it.
