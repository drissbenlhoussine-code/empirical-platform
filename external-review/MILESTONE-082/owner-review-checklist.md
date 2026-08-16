# M082 - Owner Review Checklist

> **⚠ Rewritten after the Owner review correction pass.** Two calls in the first
> version — that the label was an upper bound, and that the artifact was a
> point-in-time snapshot — were **wrong**, not merely debatable. They are listed
> below as corrections, not as judgment calls.

## Corrections made, not judgment calls

| # | What was wrong | What it is now |
|---|---|---|
| C1 | the artifact was built from the CURRENT ledger, so future receipts and future events changed the historical output | built **from receipts** labelled at or before the cutoff; later rows are structurally unreachable |
| C2 | `attested_after_cutoff_count` / `unattested_count` were future-aware | **removed and not replaced**; the snapshot says it cannot report what it excluded |
| C3 | `system_received_at` was called an upper bound on commit time, and the report "could never overstate" | a **system-assigned label**; the bound is **RETRACTED** and the backward-clock attack is executed |
| C4 | the milestone implied it closed M079's knowledge-time gap | it explicitly does **NOT** replace M079's `recorded_at` firewall |

## The judgment calls that remain, stated so you can overrule them

| # | Call | Why |
|---|---|---|
| 1 | **Option 1, not Option 2** — keep the historical artifact and make it truly receipt-cutoff, rather than relabel it "current receipt coverage" | Option 2 would not close anything, and the milestone's objective was historical authority. Option 1 keeps a true primitive. |
| 2 | **Build no separate current-coverage product** | Nothing in this milestone needs one, and inventing it would be new scope. If you want it, it must be a distinct product with distinct semantics. |
| 3 | **Option A, not Option B** — weaken to causal attestation rather than hunt for a stronger clock authority | Every candidate was rejected on evidence: commit timestamps are off and restart-gated, `transaction_timestamp()` precedes COMMIT, a sequence is assignment order, and assuming clock monotonicity *is* the defect. |
| 4 | **Remove the status enum entirely** rather than keep a one-member enum | With both other members gone, every entry is attested by construction; absence is the representation. |
| 5 | **Rename four public surfaces** | A name is a claim. "known by" and "as of" asserted knowledge-time stances the label cannot support. |
| 6 | **Make the attestation clock injectable** | The Owner mandated an executed backward-clock attack. Production wiring passes nothing; the CLI has no path to it, and a test asserts that. |
| 7 | **Raise on a receipt whose event was not supplied** rather than skip it | A missing referent is an infrastructure inconsistency, not an absence of evidence. The FK makes it unreachable in the real adapter. |
| 8 | **Two transactions, not one** | One transaction guarantees the proved commit-gap leak. Two admit a crash window where an event has no receipt. Honest absence beats false presence. |
| 9 | **Never backfill legacy events** | The table is created empty. Absence stays absence. |
| 10 | **Do not disable the old M076 writer** | That would alter frozen behaviour. The cost is non-universal coverage, and the artifact says so. |
| 11 | **Do not make M079/M080/M081 consume this** | It would change the meaning of every figure they emit — and after C3/C4, this authority is weaker than theirs is assumed to be, which makes silent adoption worse, not better. |
| 12 | **⚠ Touch one frozen milestone's TEST file** | `test_m076_migration_is_reversible` downgraded by a relative step and assumed M076 was at head. Re-verified in full this pass — see the table below. |

## R02 re-verification, as you required

| Requirement | Result |
|---|---|
| no M076 behavioural assertion changed | **confirmed** — the diff's only `assert` line is docstring prose |
| no test weakened | **confirmed** — same up→down→up structure and assertions |
| only migration-target addressing changed | **confirmed** — `"-1"` → `"31365632c016"` |
| target is genuinely M076's own predecessor | **confirmed** — the literal `down_revision` in M076's migration |
| passes against M076 in isolation | **confirmed** — with M082's migration removed, `alembic heads` = `b7e1c4a95d38 (head)`, test passes |
| passes with M082's migration present | **confirmed** — full M076 suite, 16 passed |
| no production M076 code changed | **confirmed** |

## What to check

| # | Check | Where |
|---|---|---|
| 1 | both Owner findings were reproduced before being fixed | `owner-review-correction-pass.md` |
| 2 | future-receipt non-interference | `test_a_receipt_created_after_the_cutoff_changes_nothing` |
| 3 | future-event non-interference | `test_an_event_created_after_the_cutoff_changes_nothing` |
| 4 | no future-tail counts, and no replacement | `test_no_count_in_the_artifact_is_aware_of_anything_after_the_cutoff` |
| 5 | the backward clock breaks the old implication | `test_a_backward_clock_breaks_the_wall_clock_implication` |
| 6 | the causal claim survives it | `test_the_causal_claim_survives_the_backward_clock` |
| 7 | the artifact makes no bound or knowledge-time claim | `test_no_artifact_surface_claims_an_upper_bound_or_a_knowledge_time` |
| 8 | the old overclaiming names are gone | `test_the_old_overclaiming_names_are_gone` |
| 9 | production wiring cannot inject a clock | `test_production_wiring_uses_the_host_clock_and_takes_no_caller_instant` |
| 10 | a `recorded_at` lie still creates no authority | second-pass suite, five-years-early lie |
| 11 | legacy and bypassed events stay unattested | scenarios E and J |
| 12 | concurrency idempotency still correct | scenario I, and the second pass's five attesters |
| 13 | migration still creates the table empty | `validation-results.md` |
| 14 | M079/M080/M081 byte-identical and receipt-free | `validation-results.md` |

## What I would still push back on

- **Calling `system_received_at` a commit time, or a bound on one.** It is a label.
- **Reading this milestone as closing M079's gap.** It does not, and saying so is the point of the correction.
- **Adding any count of what the snapshot excluded.** That count is future-aware by construction.
- **Adding a receipt sequence.** Proved misleading.
- **Backfilling legacy events to make coverage look complete.** That fabricates knowledge history.
