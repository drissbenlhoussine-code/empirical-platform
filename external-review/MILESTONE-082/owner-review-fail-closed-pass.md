# M082 - Owner Review Fail-Closed Pass

Everything here was **executed**. Nothing is argued.

Old head `17d9f0d`. One correction commit, same branch, same PR (#12).

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

## Three probe errors of my own, recorded

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
