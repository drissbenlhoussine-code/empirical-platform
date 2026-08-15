# M079 — Owner Review Checklist

Each item is checkable directly from the repository.

## Governance

- [ ] `origin/master` is still `5945e4effd48dfa97939bbd9448fa600503d4f89`
- [ ] `LATEST_FROZEN_MILESTONE=MILESTONE-078` on master, unchanged
- [ ] `M079_STATUS=NOT_STARTED` on master, unchanged
- [ ] no M079 freeze record exists anywhere
- [ ] the branch does not touch `PROJECT_CHECKPOINT.md`

## The claim that matters most

- [ ] a backfilled assertion is **invisible** at the earlier knowledge cutoff
      and **visible** at the later one, with the same effective cutoff
      (`test_m079_backfilled_assertion_is_invisible_at_the_earlier_knowledge_cutoff`)
- [ ] raw SQL independently agrees on eligibility at three cutoffs
      (`test_m079_raw_sql_confirms_both_timestamps_and_eligibility`)
- [ ] M076 still sees the backfill that M079 hides
      (`test_m076_is_not_mutated_and_still_answers_effective_time`)
- [ ] M079 equals M076 when `knowledge_as_of` is the present
      (`test_m079_matches_m076_when_knowledge_is_the_present`)

## The adversarial case

- [ ] a `CLOSED` visible without its `OPENED` yields
      `INCOMPLETE_KNOWLEDGE_SEQUENCE`, `position is None`, and **nothing
      invented**
- [ ] genuinely incoherent data yields `LEDGER_INCOHERENT_FOR_POSITION`, so
      incompleteness cannot mask corruption
- [ ] one incomplete key does not withhold the whole snapshot

## Frozen preservation

- [ ] `operator_position_ledger.py` byte-identical to master
- [ ] `same_day_capital_feasibility.py`, `portfolio_aware_capital_feasibility.py`,
      `research_decision_follow_through.py` byte-identical
- [ ] zero migrations added or changed
- [ ] M062/M064/M065 untouched; M063 record preserved

## Honesty

- [ ] the banner denies broker verification, execution, fills, holdings,
      valuation, P&L, profitability, causation and advice
- [ ] `KNOWN` is defined as *known to the ledger*, in the banner and in a
      per-snapshot limitation
- [ ] no field names a return, gain, loss, P&L or proceeds
- [ ] `VERIFIED`, `EXECUTED`, `FILLED`, `REALIZED`, `CONFIRMED` appear in no
      closed vocabulary

## Evidence integrity

- [ ] the implementation review records **R02**: the design review's own header
      count was overstated and how it was corrected
- [ ] no verdict was erased; corrections are recorded in place

---

## Owner review correction pass — what to re-check

| # | Check | Where |
|---|---|---|
| 1 | The unfiltered re-fold is gone | `operator_evidence_availability.py` — no `unfiltered_by_key`, no second `_fold_one_key` call in the failure path |
| 2 | The snapshot logic literally cannot see post-cutoff evidence | `_snapshot_from_known_evidence(known, ...)` — and `test_the_snapshot_builder_cannot_reach_post_cutoff_events_at_all` |
| 3 | No leaking count survives | `total_event_count` and `excluded_by_knowledge_cutoff` removed from the dataclass, the JSON and the text |
| 4 | The status vocabulary offers no future-dependent verdict | three members only; `test_no_status_distinguishes_future_resolvable_from_truly_corrupt` |
| 5 | Identical prefix, different future → identical output | `test_a_future_backfilled_opening_does_not_change_the_answer_at_k` and the parametrised per-field test |
| 6 | The same, over two real PostgreSQL databases | `test_m079_two_databases_identical_up_to_k_produce_identical_output` |
| 7 | The two databases genuinely differ | `test_m079_the_two_databases_diverge_once_knowledge_advances` |
| 8 | Temporal evolution still works and does not reach backwards | `test_advancing_the_knowledge_cutoff_resolves_the_sequence_legitimately` |
| 9 | Claim language weakened to what `recorded_at` supports | banner, limitation 8, `test_the_banner_claims_recording_not_actual_availability` |
| 10 | Retractions are visible, not erased | design review banner, reality gate, validation results, this file |
| 11 | M076 untouched and still sees everything | `test_m079_leaves_m076_free_to_see_every_event`; zero frozen files in the diff |

## What the correction cost, so you can weigh it

- An operator can no longer be told whether an unresolved gap is likely to close.
- The snapshot can no longer report how many assertions it hid.

Both were removals of information the system could not honestly have at `K`.
