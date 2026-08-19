# MILESTONE-082 — Operator Event Receipt Identity Attestation — Current Design

**Status: FINAL_CLOSURE_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **The authority of this milestone is not stated here.** It is stated once, in
> machine-readable form, in
> [`external-review/MILESTONE-082/current-authority.json`](external-review/MILESTONE-082/current-authority.json),
> and rendered deterministically to
> [`external-review/MILESTONE-082/current-authority.md`](external-review/MILESTONE-082/current-authority.md).
> If this document and the contract ever disagree, the contract is correct and
> this document is a defect.

This file describes the current architecture only. It contains no retraction, no
reproduced defect and no review chronology.

---

## 1. Capability

An additive, append-only receipt sidecar for M076 operator-asserted position
events. `attest()` runs in a transaction of its own, reads the event back from
committed persistence, and only then inserts a receipt.

That ordering is the whole claim, and it is causal: it holds regardless of any
clock.

## 2. Components

| Layer | Element |
|---|---|
| Domain | `OperatorEventReceipt`, `AttestedEventEntry`, `AttestedEvidenceReport`, `build_attested_evidence_report`, `events_with_receipt_labelled_by` |
| Port | `OperatorEventReceiptRepository` — `attest`, `get_for_event`, `list_labelled_by`, `list_all` |
| Adapter | `PostgreSQLOperatorEventReceiptRepository`, injectable clock, cutoff applied in SQL |
| Usecases | `AttestOperatorEventReceiptHandler`, `GetAttestedEvidenceReportHandler` |
| Entry point | `empirical-platform-receipt-label-cutoff-view`, flag `--receipt-label-cutoff` |
| Schema | `operator_event_receipt`, migration `d9a2f5c81b73` |

## 3. Schema and enforcement

One table. A foreign key to `operator_position_event.governance_id` with
`ON DELETE RESTRICT`; a UNIQUE constraint on `event_governance_id`; four CHECK
constraints refusing blanks over the complete 29-character Python `str.strip()`
set; a BEFORE INSERT trigger refusing a receipt whose referenced event was
written by the current transaction; and a row trigger refusing UPDATE and
DELETE.

The exact enforcement table, and the exact list of what the database does **not**
enforce, are in the canonical contract.

## 4. Artifact

The report is built **from receipts alone**. It carries no payload field, no
status vocabulary and no count of what it excluded. The cutoff is a receipt-label
filter and nothing more.

## 5. Interaction with frozen milestones

M076 production code, M079, M080 and M081 are unchanged and do not consume this
authority. `PROJECT_CHECKPOINT.md` is unchanged.

## 6. Historical record

Every earlier version of this design — including its retractions, its reproduced
attacks and the full Finding 1 to Finding 28 review chronology — is preserved,
unedited, at:

```
external-review/MILESTONE-082/history/MILESTONE_082_SCOPE_AND_DESIGN_at_f61f14b.md
  source commit : f61f14b15fb5caa5bebc89abef2bca65cecd0318
  original path : MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md
  bytes (LF)    : 46733
  sha256 (LF)   : 4112b1b1da560739827a042f48e5a72c49ec66e4e7c524f88fe89a9656c85e9b
```

That archive is historical record. It is not current authority, and nothing
imports or renders it.
