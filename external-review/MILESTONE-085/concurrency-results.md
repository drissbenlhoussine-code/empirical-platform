# MILESTONE-085 — Concurrency Results

**49 tests. 16 races, each run three times on three independently rebuilt schemas,
plus one anti-vacuity test that requires the three to have been genuinely distinct.
All passing.**

Executed by `tests/integration/test_m085_concurrency.py` against real PostgreSQL
16.13, with real threads.

## Sleep is not evidence of ordering

Every race is arranged with `threading.Barrier` or `threading.Event`, never with a
sleep. A sleep can bound a failure — "if this has not happened in two seconds it
never will" — but it cannot establish that two operations overlapped. A test that
passes because one thread happened to be slow is a test that will keep passing
after the guarantee it checks has been removed.

## Three repetitions, measured rather than asserted

Each repetition drops `public`, re-runs the complete migration history, and records
the schema and `paper_execution_attempt` object identifiers.
`test_three_repetitions_ran_on_three_rebuilt_schemas` then requires **three distinct
schema oids and three distinct table oids**. If the fixture ever stopped rebuilding,
that test fails rather than letting one repetition be described three times.

That test also has to skip when PostgreSQL is off, and it did not at first — the
PostgreSQL-OFF regression mode caught it, because with the database absent every
repetition skipped and the assertion had nothing to check. It now skips under the
same condition its subjects skip under, which is not a weakening: with no repetition
having run there is nothing that could have been distinct.

## The races

| Race | What must hold | Result |
|---|---|---|
| Two workers claiming one dispatch, released by a barrier | Exactly one wins; the database holds exactly one attempt; the LOSER receives the persisted winner | PASS |
| Four workers racing the same claim | One attempt row, one consumed authorization | PASS |
| Two simultaneous authorization saves for one preview | Exactly one survives | PASS |
| A consumed authorization after a simulated process restart | Still consumed, through a brand-new service and runtime | PASS |
| Expiry racing dispatch | Refused by name | PASS |
| A changed fingerprint racing dispatch | Refused by name | PASS |
| An authorization bound to another account | Refused by name | PASS |
| Crash between the claim and the network | A CLAIMED attempt and ZERO acknowledgements | PASS |
| Failure inside the claim transaction | Neither the consumption nor the attempt survives | PASS |
| Two acknowledgements computing the same sequence | One lands; no duplicate survives | PASS |
| Two concurrent reconciliation transitions | Converge on a state the closed table permits; identity unmoved | PASS |
| A cancel racing a fill | Ends in one of the two legal destinations; a terminal outcome carries its instant | PASS |
| Kill switch engaged concurrently | Seen by the next read, because it is never cached | PASS |
| Three concurrent kill-switch moves | No duplicate version survives | PASS |
| A buying-power change before dispatch | The account reference is unchanged; the balance is re-checked | PASS |
| Constraint-name honesty | A failure names the constraint that actually fired | PASS |

## The two results worth reading twice

**The loser receives the winner, and that is REQUIRED rather than tolerated.** An
earlier version of the first test accepted "the loser raised instead" as an
alternative outcome. The mutation campaign then removed `AND consumed_at IS NULL`
from the claim UPDATE and the mutation SURVIVED — because without that clause the
loser hits the consumption trigger and raises, which the permissive branch allowed.
The conditional UPDATE exists precisely so that a duplicate dispatch request ends up
reconciling the real order, since a caller handed an exception is a caller that may
retry. The test now demands a losing CLAIM and tolerates no failures.

**A crash between the claim and the network leaves evidence, deliberately.** The
claim is committed before any network request, so a crashed worker leaves a
DISPATCH_CLAIMED attempt and zero acknowledgements. That is the point: the claim is
what stops a second worker from starting a fresh dispatch, and the absent
acknowledgement is what stops a reader believing a request was sent.

## What this does not establish

- Not behaviour under production load. Sixteen races with two to four threads is
  not a load test, and nothing here claims a throughput figure.
- Not serialisable isolation. The guarantees rest on unique constraints, a
  conditional UPDATE and triggers, not on an isolation level; the tests run at the
  connection default.
- Not immunity to a database owner. Every refusal here is row-level under the
  installed triggers, and `test_m085_paper_execution_postgres.py` EXECUTES the holes
  that remain.
