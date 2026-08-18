> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 - Owner Review Fail-Closed Pass

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


Everything here was **executed**. Nothing is argued.

Old head `17d9f0d`. **Two** correction commits, same branch, same PR (#12):
`6337ba4` (the fail-closed fix) and `8415939` (repair of a defect `6337ba4`
introduced). The mission asked for one commit if possible; it was not possible,
and the reason is recorded below rather than hidden by an amend.

---

## FINDING 6 - the prior-commit trigger failed open on unexpected errors

The trigger read:

```sql
BEGIN
    writer_status := pg_xact_status(probe::text::xid8);
EXCEPTION WHEN OTHERS THEN
    writer_status := NULL;
END;
```

and refused only on `'in progress'`. **Everything else was accepted**, including
every unexpected failure of the checker itself. For an invariant whose freeze
claim is "a persisted M082 receipt proves the referenced M076 event came from a
prior transaction", a broken checker must not become permission to insert.

### The stated justification did not hold, and that was checked by execution

The handler's comment said it existed because an old xid may no longer have CLOG
status. Measured on PostgreSQL 16.13:

```
pg_xact_status('1'::xid8)                        -> committed      (NOT an error)
pg_xact_status(<current + 1000000>::xid8)        -> ERROR: transaction ID ... is in the future
```

So `pg_xact_status` handles the documented old-transaction case **by returning a
value**, not by raising. `EXCEPTION WHEN OTHERS` was therefore never needed for
it — and it *was* silently swallowing a real, reachable failure: the "in the
future" error, which a wrapped-epoch reconstruction can genuinely produce.

### The forced-error attack, executed

A role without `EXECUTE` on `pg_xact_status`:

```
ERROR:  permission denied for function pg_xact_status
```

driven through a `WHEN OTHERS` handler:

```
WHEN OTHERS result: NULL-swallowed      ->  would be ACCEPTED
```

That is the fail-open, demonstrated rather than reasoned about.

### The fix

The handler is **removed**. The call is unguarded:

```sql
writer_status := pg_xact_status(probe::text::xid8);

IF writer_status IN ('in progress', 'aborted') THEN
    RAISE EXCEPTION ...;
END IF;
```

**No SQLSTATE is caught at all.** No specific documented exception was found that
genuinely needs handling, and inventing one would be worse than propagating.

### Behaviour table, each row measured

| Status | Behaviour | Evidence |
|---|---|---|
| `in progress` | **REFUSE** | same-transaction, savepoint, nested savepoint all refused |
| `aborted` | **REFUSE** | unreachable for a visible row; refused anyway |
| `committed` | accept | prior-committed, concurrent-higher-xid, frozen all accepted |
| NULL | accept | documented old-transaction semantics; **not observed here** — see below |
| **any error** | **REFUSE — fails closed** | forced privilege error, 0 rows inserted |

---

## The two unknowns, now kept apart

The Owner's distinction, implemented literally:

| Situation | Behaviour |
|---|---|
| **SUPPORTED UNKNOWN STATUS VALUE** — `pg_xact_status` returns NULL | accepted; a live transaction always has its CLOG, so NULL cannot be an in-progress writer |
| **CHECKER FAILURE** — the call, the xid reconstruction, or SQL execution errors | **fails closed**; the error propagates and the INSERT is refused |

**Honest gap:** NULL was **not reproducible** in this environment —
`pg_xact_status('1')` returns `committed`. The NULL branch rests on PostgreSQL's
documented old-transaction semantics and is stated as such, not claimed as
measured.

---

## Mandatory attacks, all executed

| # | Attack | Result |
|---|---|---|
| 1 | same-transaction event + receipt | **REFUSED** |
| 2 | same transaction through SAVEPOINT | **REFUSED** |
| 3 | nested SAVEPOINT | **REFUSED** |
| 4 | prior committed event | **ACCEPTED** |
| 5 | concurrent higher-xid committed writer | **ACCEPTED** (no false refusal) |
| 6 | old / `VACUUM FREEZE`d event | **ACCEPTED** |
| 7 | aborted writer | row **visible to nobody** (0); the FK speaks, not the status check |
| 8 | **forced error in the status-check path** | **INSERT FAILS, 0 rows — FAIL CLOSED** |
| 9 | direct same-transaction raw SQL still blocked | **REFUSED** |
| 10 | ordinary `attest()` path still succeeds | **ACCEPTED** |
| 11 | migration up / down / up | 2 triggers, 2 functions, table empty |
| 12 | fresh PostgreSQL 16 database pass | 4 passed |

Attack 8 has a **control**: with the privilege restored, the identical INSERT
succeeds and one row lands. That is what proves the refusal came from the
checker error and not from anything else. Without the control the test would
prove nothing — a refusal for the wrong reason looks the same as a refusal for
the right one.

The assertion on the installed function body is deliberately secondary: the
behavioural attack is the proof, and the `pg_proc` check exists only so a future
edit cannot reintroduce the swallow silently.

---

## The defect I introduced, and the wrong diagnosis I gave

This is the part of the pass worth the most scrutiny, so it is recorded as a
sequence rather than as a footnote.

### The causal sequence

```
  1. 6337ba4  fail-closed correction committed
                 |
                 |  in the SAME edit, an S106 lint finding (hardcoded probe-role
                 |  password) was fixed by generating one with secrets and passing
                 |  it as a bind parameter
                 v
  2.          DEFECT INTRODUCED
                 CREATE ROLE ... LOGIN PASSWORD :pw
                 CREATE ROLE is a UTILITY STATEMENT. PostgreSQL will not accept a
                 bind parameter in one:
                   psycopg.errors.SyntaxError: syntax error at or near "$1"
                   LINE 1: CREATE ROLE m082_failclosed_probe LOGIN PASSWORD $1::VARCHAR
                 v
  3.          INCORRECT DIAGNOSIS
                 The focused suite was run while the full regression still held the
                 same database. It returned 11 failures. I attributed them ENTIRELY
                 to that collision.
                 The collision was real. It was also MASKING the defect above, and I
                 stopped at the first plausible explanation instead of confirming it
                 with a clean re-run.
                 v
  4.          FULL REGRESSION EXPOSED IT
                 PostgreSQL-on: 25 failed vs baseline 24, diff 69 vs 68 ids,
                 exactly one extra entry:
                   > FAILED tests/integration/test_m082_operator_event_receipt_lifecycle.py::test_an_unexpected_checker_error_fails_closed
                 v
  5. 8415939  REPAIR
                 secrets.token_hex(24) interpolated directly. Hex cannot contain a
                 quote, so interpolation is safe BY CONSTRUCTION rather than by
                 hoping. S106 stays clean; no suppression was added.
                 v
  6.          CLEAN RE-VERIFICATION
                 M082 PostgreSQL suite: 44 passed, in isolation, at 8415939
                 Full regression: 24 failed / 2792 passed / 44 errors, PostgreSQL on
                                   8 failed / 2327 passed / 12 errors, PostgreSQL off
                 Failing-ID diff: EMPTY in both modes (68 and 20 ids)
```

### What this says about the method

The defect was **not** caught by any of the twelve mandated attacks, nor by the
focused suite, nor by reading the code. It was caught by the one check that
compares the whole suite against a baseline and diffs exact test identities.

A single extra failing ID was the entire signal. Had I compared **counts**
instead of **identities**, 25-vs-24 would still have been visible — but had I
skipped the full regression on the grounds that "the change is small and the
focused suite passes", the broken commit would have gone to Owner review
claiming a fail-closed guarantee that its own regression test could not execute.

The interim figures reported mid-pass were measured **before** the `secrets`
edit and therefore described neither commit. `validation-results.md` now carries
figures re-measured at `8415939`, with that error stated in place.

## Three further probe errors of my own, recorded

1. I asserted `"EXCEPTION" not in` the installed function body — which fails on
   the trigger's own `RAISE EXCEPTION`, the refusal that must stay. Narrowed to
   `EXCEPTION WHEN`, and a positive assertion that `RAISE EXCEPTION` is still
   present was added.
2. I called `.replace()` on `sqlalchemy_url()`, which returns a SQLAlchemy `URL`
   object, not a string. Fixed with `.set(username=..., password=...)`.
3. My role cleanup used `DROP ROLE IF EXISTS`, which refuses while the role
   holds grants, and then `DROP OWNED BY`, which has no `IF EXISTS`. Both found
   by executing the cleanup, not by reading documentation.

---

## What this pass did NOT change

Receipt-label-cutoff semantics, causal-only authority, `system_received_at`
wording, M079/M080/M081, M076 production code, and the schema shape. The only
schema-adjacent change is the trigger function body, which is the correction
itself.
