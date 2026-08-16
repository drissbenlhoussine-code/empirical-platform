# M082 - Transaction Timing Evidence

Everything here was **executed** against PostgreSQL 16.13. Nothing is argued.

## 1. All in-transaction timestamps precede COMMIT

| Function | Behaviour inside one transaction |
|---|---|
| `transaction_timestamp()` | frozen at transaction start; does **not** advance |
| `statement_timestamp()` | advances per statement |
| `clock_timestamp()` | advances continuously |

Measured by sleeping one second inside a single transaction and re-reading all
three. **None of them is a commit time.**

## 2. The commit-gap leak, proved

A transaction assigned its timestamp and paused before committing. `K` was
chosen during the pause.

```
timestamp ASSIGNED : 13:44:14.924211
K chosen in pause  : 13:44:16.424349
rows VISIBLE at K  : 0             <- genuinely not durable
COMMIT             : 13:44:17.926

historical query "assigned_at <= K"  ->  RETURNS THE ROW
```

The row was invisible to every reader at `K`, yet the historical query at `K`
reports it as available. **This is the same class of defect M079 exists to
prevent.** The size of the window is irrelevant to whether the claim is true.

## 3. The post-commit receipt inverts it, proved

The identical pause, against the **real M082 attestation path**:

```
row visible at K            : 0
K                           : 13:56:09.230006
event COMMIT                : 13:56:10.732522
receipt system_received_at  : 13:56:10.753081
```

`system_received_at` falls **after** the commit, and therefore after `K`. The
historical query at `K` correctly returns **nothing**.

```
commit_time(event)  <  system_received_at(receipt)
  =>  system_received_at <= K  IMPLIES  durably committed by K
```

The converse does not hold, and that asymmetry is deliberate: an event committed
just before `K` but attested just after it is **excluded**. M082 may understate
what was known and can never overstate it.

## 4. Commit-time authority is unavailable, and is not faked

```
track_commit_timestamp = off
SELECT pg_xact_commit_timestamp(xmin)
  -> ObjectNotInPrerequisiteState: could not get commit timestamp data
```

Off by default, requires a **server restart**, not retroactive, and
deployment-wide. M082 uses no commit timestamp and claims no commit time.

## 5. What the authority level actually is

| Level | Claim | M082 |
|---|---|---|
| 1 | operator asserted `recorded_at` | not this |
| 2 | application assigned observed time | **not quite this** |
| 3 | database assigned observed time | not this |
| 4 | transaction committed by time X | **THIS, as an upper bound** |
| 5 | evidence visible to every reader by X | not claimed |

M082 reaches level 4 **as a one-directional bound**: the event *had already*
committed when the instant was taken. It does not reach the exact commit time,
and it does not reach level 5.
