# M076 — Owner Review Correction Pass

Owner review of PR #6 at head `14e8bd29132b73d4e2db6de477c0c48307d0741b` returned three
blocking correctness findings. All three were real. This records what changed.

## Finding 1 — validation/append concurrency race

**I had found this myself and then argued it away.** My own hostile review listed it as
attack 48 and dispositioned it `ACCEPTED` with the reasoning "single-operator CLI
primitive; the limitation is stated rather than papered over with a lock this milestone
cannot justify". `known-limitations.md` repeated it. The owner is right: **documenting a
race is not a fix for a durable ledger.** A ledger whose invariant can be broken by two
ordinary writers does not have that invariant.

**Root cause.** `RecordOperatorPositionEventHandler.handle()` did
`list_all()` → `validate_appended_event()` → `append()`, each in its own transaction.
Two writers could read the same open quantity, both validate, and both insert, leaving a
sequence the canonical fold rejects.

**Correction.** The repository contract no longer exposes an unvalidated `append`. It
exposes `append_validated`, which the PostgreSQL adapter implements as one transaction:

1. `SELECT pg_advisory_xact_lock(hashtext(:lock_key))` — keyed on the *position governance
   id*, so writers to different positions never contend;
2. re-read that key's committed events;
3. run the pure domain validation;
4. insert.

The lock is transaction-scoped, so it releases on commit or rollback. The handler now
delegates, because the invariant can only be enforced where the transaction is.

**Proof.** Four real concurrency attacks, each running its event through its own
runtime and connection, with a `threading.Barrier` so the writes genuinely collide:

| Attack | Result |
|---|---|
| open 10, then two concurrent `REDUCED(6)` | exactly one succeeds; the other is rejected `REDUCTION_EXCEEDS_OPEN_QUANTITY` after seeing committed state; 2 rows persist; final fold succeeds with quantity 4 |
| two concurrent `OPENED` on one position | exactly one succeeds; other rejected `POSITION_ALREADY_OPEN`; 1 row persists |
| two concurrent identical event ids | exactly one row persists |
| concurrent writes to *different* positions | **both succeed** — proving the fix did not serialise the whole ledger |

Every one also asserts the persisted ledger still folds.

## Finding 2 — timezone invariant missing

The temporal model depends on unambiguous instants, and the column is `TIMESTAMPTZ`, but
the domain accepted naive datetimes. A naive value has no instant, and comparing one
against an aware one raises at runtime.

**Correction.** `event_timestamp` and `recorded_at` must be timezone-aware, and so must
`as_of`. Naive values are rejected deterministically as `NAIVE_TIMESTAMP` before anything
reaches persistence. Inclusive `as_of` is unchanged.

**Proof.** Domain construction (both fields), `as_of`, PostgreSQL round-trip, and two
different offsets representing the same instant folding identically — including the exact
boundary and one microsecond before it.

## Finding 3 — Decimal ↔ NUMERIC(20,6) mismatch

The domain accepted any precision; the column stores six decimal places. `1.1234567` would
be accepted, silently rounded on write, and reload as a *different* value — breaking
deterministic replay and making the rendered price disagree with the stored one.

**Correction.** One explicit canonical invariant, `ASSERTED_PRICE_MAX_DECIMAL_PLACES = 6`.
The domain **rejects** anything beyond it rather than quantizing, because silently altering
a number the operator asserted is itself a small dishonesty. Positivity is now a domain
invariant too, not only a database CHECK. Rejecting was chosen over widening the column as
the narrower, architecture-consistent option.

**Proof.** Zero, negative, `-0.000001`, and three over-precision values rejected; five
in-scale values accepted including `0.000001` and `99999999999.999999`; six-decimal price
round-trips through PostgreSQL with full object equality; over-precision refused *before*
any row is written.

## Verification after correction

| | master `92ff472` | corrected branch |
|---|---|---|
| PostgreSQL off | 8 failed, 1869 passed, 12 errors | 8 failed, **1914** passed, 12 errors |
| PostgreSQL on | 24 failed, 2168 passed, 44 errors | 24 failed, **2227** passed, 44 errors |

Identical failure and error counts; **+45 / +59 passing. Zero regressions.**

- M076 focused: 45 unit + 14 integration
- M070–M076 integration: 36 passed, 5 skipped
- Fresh second PostgreSQL pass on `m076_correction_pass2`, migrations from empty: 14/14
- ruff / format / mypy (289) / architecture / negative fixture / pip-audit / secret scan
  (0) / build / wheel import — all pass

## Honesty boundaries

Unchanged. No M075 semantics touched. No M062/M064/M065 seal debt repaired. The banner,
the vocabulary tests, and the plan-is-not-a-position boundary are all as they were.
