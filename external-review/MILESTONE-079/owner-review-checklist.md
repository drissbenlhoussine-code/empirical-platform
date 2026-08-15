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
