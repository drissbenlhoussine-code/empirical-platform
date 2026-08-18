# M082 — Operator Event Receipt Identity Attestation

**Current authority, version 1.** Generated from `current-authority.json`; do not edit by hand.

This document is the single active statement of what MILESTONE-082 establishes. Every other file in this package is either current validation evidence or historical record, and neither carries authority.

## What a persisted receipt proves

A persisted receipt binds:

- a stable receipt identity;
- a binding to one exact M076 event governance identity;
- that the referenced `public` event row originated from a **prior committed transaction** at receipt insertion;

## What it does not prove

- **Not** the event payload, current or historical.
- **Not** the event's commit time.
- **Not** any wall-clock chronology.
- **Not** historical availability.
- **Not** availability to an arbitrary reader at an arbitrary cutoff.
- **Not** the provenance of persisted metadata.
- **Not** that an arbitrary persisted receipt came through the sanctioned `attest()` path.

## Metadata provenance

As a **generic persisted value**, receipt metadata has **UNAUTHENTICATED PROVENANCE**. A direct SQL receipt for a genuinely prior-committed event is accepted by design and may carry any allowed value.

On the sanctioned `attest()` path only:

- `system_received_at` — the application clock CALL is issued causally after the committed read-back; the value it returns proves no chronology;
- `attester_version` — an application constant;
- `attested_by` — caller-supplied and passed through unchanged;

## Cutoff semantics

The cutoff is a **receipt-label filter only**. It selects receipts whose label is at or before the cutoff, and asserts nothing else.

- It does **not** carries historical knowledge authority.
- It does **not** emits future-tail counts.
- It does **not** enriches entries with event payload.

## Database enforcement

| Property | Enforced |
|---|---|
| the referenced event exists | **yes** |
| the referenced event came from a prior committed transaction | **yes** |
| exactly one receipt per event | **yes** |
| receipt evidence cannot vanish with its event | **yes** |
| row-level UPDATE/DELETE immutability | **yes** |
| non-blank receipt identity and metadata | **yes** |
| the provenance of persisted metadata | **no** |
| any wall-clock chronology | **no** |

## Structural limitations

- Row immutability is row-level UPDATE/DELETE only. TRUNCATE, DROP and a superuser remain outside it.
- No cryptographic signature and no monotonicity enforcement. This is not a trusted timestamping service.
- PostgreSQL commit timestamps are unavailable here and are not used.
- Repeated evaluation at the same cutoff can change, because a label can be backdated.
- A crash between event commit and receipt insertion leaves an unattested gap.
- The view cannot report how much evidence it excluded, and offers no count of it.

## Intended future use

- A future evidence-watermark milestone may bind an evaluation to an explicitly persisted receipt set. It is not started.
- M079's `recorded_at` firewall is **not** replaced by this milestone.
