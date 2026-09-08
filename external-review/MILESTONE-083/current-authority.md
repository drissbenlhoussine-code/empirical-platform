# M083 — Persisted Receipt-Set Evaluation Evidence Watermark

**Current authority, version 1.** Generated from `current-authority.json`; do not edit by hand.

This document is the single active statement of what MILESTONE-083 establishes. Every other file in this package is either current validation evidence or historical record, and neither carries authority.

## What a persisted watermark proves

One persisted watermark row binds:

- a stable watermark governance identity;
- the EXACT set of M082 `receipt_governance_id` values visible to the schema-qualified capture query, under that one statement's own PostgreSQL transaction snapshot;
- that set stored once, in deterministic canonical (`COLLATE "C"`) order;
- that the stored set does not change when a later receipt or event is inserted -- reading an existing watermark reads its stored set only and never re-consults the current receipt inventory;
- that ordinary row-level UPDATE and DELETE against this watermark's row are refused by the installed trigger -- a narrower guarantee than absolute database immutability; it does NOT cover TRUNCATE, DROP, disabling the trigger, or superuser mutation (see `does_not_prove` and `structural_limitations`);

## What it does not prove

- **Not** that any ResearchSession, DecisionCandidate, brief or evaluation consumed this watermark.
- **Not** evaluation time, capture time, or any wall-clock chronology.
- **Not** receipt commit time or event commit time.
- **Not** historical availability at an arbitrary timestamp or cutoff.
- **Not** receipt ordering, a committed prefix, or any sequence authority.
- **Not** event payload, current or historical.
- **Not** receipt metadata provenance.
- **Not** operator truth, broker truth, fills or trades.
- **Not** that every M076 event has a receipt.
- **Not** that an absent receipt did not exist at another time.
- **Not** that the set represents all operator evidence.
- **Not** any future-tail or excluded-receipt count.
- **Not** cryptographic sealing.
- **Not** protection against DDL authority, trigger disabling, TRUNCATE, DROP or superuser mutation.
- **Not** profitability, performance, advice or live-trading readiness.

## Database enforcement

| Property | Enforced |
|---|---|
| the trigger-computed set unconditionally replaces any caller-supplied `receipt_governance_ids` | **yes** |
| deterministic canonical storage order | **yes** |
| an explicit empty array, never NULL, for zero receipts | **yes** |
| row-level UPDATE/DELETE refusal | **yes** |
| idempotent capture by watermark identity, with one immutable winner under concurrent retry | **yes** |
| DDL authority, trigger disabling, TRUNCATE, DROP or superuser mutation | **no** |

## Structural limitations

- Row-level UPDATE/DELETE refusal does not cover TRUNCATE, DROP, or a superuser.
- No cryptographic signature and no monotonicity enforcement.
- Statement-snapshot visibility is NOT prior-commit visibility: a receipt inserted earlier in the SAME transaction as the capture is included even though it has not committed.
- A crash or rollback between the capture statement's start and its commit leaves no partial row -- the whole row is produced inside one statement.
- The watermark cannot report how much evidence it excluded, and offers no count of it.
- The watermark governance identity is caller-supplied and carries no chronology of its own.

## Intended future use

- A future evaluation-context milestone may bind a watermark to one evaluation. It is not started.
- M082's receipt identity attestation is **not** replaced or strengthened by this milestone.
