# M082 - Focused Re-Review After the Corrections

> **⚠ CORRECTED AFTER OWNER REVIEW — READ THIS FIRST.**
>
> Two conclusions recorded below are **RETRACTED**. They are left in place, not
> deleted, so the original reasoning stays readable and the correction stays
> visible.
>
> **RETRACTION 1 (Owner finding 1) — "point-in-time historical snapshot".**
> The artifact was built from the CURRENT ledger, so a receipt created after the
> cutoff and an event created after the cutoff both changed the historical
> output. Executed: two databases with identical evidence at W produced
> `ATTESTED_AFTER_CUTOFF` vs `NO_SYSTEM_RECEIPT_EVIDENCE`, differing counts, and
> a leak of a future event's id, position and instrument symbol. Any sentence
> below claiming the artifact is a point-in-time snapshot, or that "nothing
> attested after the cutoff influences any figure", is **SUPERSEDED** by
> `reality-gate.md`. The snapshot is now built FROM RECEIPTS labelled at or
> before the cutoff; `ATTESTED_AFTER_CUTOFF`, `NO_SYSTEM_RECEIPT_EVIDENCE`,
> `attested_after_cutoff_count` and `unattested_count` no longer exist.
>
> **RETRACTION 2 (Owner finding 2) — the wall-clock upper bound.**
> Any sentence below asserting `commit_time(event) < system_received_at`, that
> `system_received_at <= W` implies durable commit by W, that the guarantee is
> "one-directional", or that M082 "can never overstate", is **RETRACTED**. A
> backward host clock breaks it, and the attack is executed in
> `test_a_backward_clock_breaks_the_wall_clock_implication`. What survives is
> the CAUSAL claim: the read-back preceded the receipt. **M082 therefore does
> NOT replace M079's `recorded_at` firewall.**
>
> Renames that followed: `attested_known_by` → `events_with_receipt_labelled_by`,
> `attested_as_of` → `receipt_label_cutoff`, `--attested-as-of` →
> `--receipt-label-cutoff`.


## R01 - the concurrent-loser path

| Re-attack | Result |
|---|---|
| Do concurrent attesters still crash? | **No** - six threads, zero errors |
| Exactly one receipt survives? | Yes |
| Do all callers see the same instant? | Yes |
| Is the read still inside the transaction? | **No** - detection inside, read after close |
| Did idempotency change? | No - 15 retries return the identical receipt |
| Did the happy path change? | No - all other attacks unchanged |
| Is the defect recorded in the code? | Yes, with why the design review missed it |

## R02 - the M076 reversibility test

| Re-attack | Result |
|---|---|
| Does M076's suite pass? | Yes - 16 passed |
| Did M076 semantics change? | **No** - the module is byte-identical |
| Did M076's schema change? | No |
| Does the test still prove M076's downgrade works? | **Yes** - against M076's own predecessor revision |
| Is it still head-dependent? | **No** - that was the whole defect |
| Is this flagged to the Owner? | **Yes** - it is the one frozen-milestone file M082 touches |

## The secret-scan finding

The scan reported one finding on my migration: its alembic revision identifiers,
flagged as high-entropy hex. **Not suppressed.** The repository already filters
these, but only in the *annotated* form every other migration uses
(`revision: str = "..."`). My file used the bare form and so fell outside the
established convention. Conforming to the convention resolved it.

| Re-attack | Result |
|---|---|
| Secret scan clean? | **0 findings** |
| Any suppression added? | **None** - no `noqa`, no allowlist entry, no baseline file |
| Does the migration still work? | up / down / up all verified |

## Whole-suite confirmation after all corrections

| Suite | Result |
|---|---|
| M082 unit | **30 passed** |
| M082 PostgreSQL integration | **23 passed** |
| M082 fresh second pass | **4 passed** |
| M076-M082 chain | **435 passed** |
| Executed attack battery | **263 / 263** |
| Full regression, both modes | failing-ID sets identical to the `28a1053` baseline |
