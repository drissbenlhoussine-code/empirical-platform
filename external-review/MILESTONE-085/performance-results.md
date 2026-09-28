# MILESTONE-085 — Performance Results

**VALIDATION EVIDENCE ONLY. Nothing here enters the authority contract.**

Measured at `2026-09-10T00:26:07.806388+00:00` (UTC).

## Environment boundary, so no number can be quoted without it

- PostgreSQL: `PostgreSQL 16.13, compiled by Visual C++ build 1944, 64-bit`
- Database: `m085_perf`
- Samples per measurement: 25
- Scales: 0, 100, 1000, 10000 attempt rows
- Concurrent load: none
- One machine, one disk, no tuning; medians and p95 rather than means, because a
  mean over a few dozen samples is dominated by whichever one met a checkpoint.

## Latency by scale

| Query | Purpose | Rows | Median (ms) | p95 (ms) | Max (ms) | n |
|---|---|---|---|---|---|---|
| `queue_recent` | the operator dispatch queue, newest first | 0 | 0.347 | 0.676 | 5.396 | 25 |
| `attempt_by_intent` | the single attempt for one intent | 0 | 0.226 | 0.380 | 0.654 | 25 |
| `attempt_by_client_order_id` | the reconciliation identity lookup | 0 | 0.229 | 0.526 | 0.617 | 25 |
| `reconciliation_candidates` | attempts still needing reconciliation | 0 | 0.195 | 0.478 | 0.809 | 25 |
| `audit_history_for_intent` | the whole audit trail behind one intent | 0 | 0.200 | 0.352 | 0.918 | 25 |
| `queue_recent` | the operator dispatch queue, newest first | 100 | 0.250 | 0.534 | 1.031 | 25 |
| `attempt_by_intent` | the single attempt for one intent | 100 | 0.197 | 0.294 | 0.429 | 25 |
| `attempt_by_client_order_id` | the reconciliation identity lookup | 100 | 0.193 | 0.307 | 0.365 | 25 |
| `reconciliation_candidates` | attempts still needing reconciliation | 100 | 0.201 | 0.596 | 0.797 | 25 |
| `audit_history_for_intent` | the whole audit trail behind one intent | 100 | 0.163 | 0.278 | 0.641 | 25 |
| `queue_recent` | the operator dispatch queue, newest first | 1000 | 0.218 | 0.601 | 0.937 | 25 |
| `attempt_by_intent` | the single attempt for one intent | 1000 | 0.239 | 0.402 | 0.407 | 25 |
| `attempt_by_client_order_id` | the reconciliation identity lookup | 1000 | 0.197 | 0.334 | 0.392 | 25 |
| `reconciliation_candidates` | attempts still needing reconciliation | 1000 | 0.193 | 0.344 | 0.379 | 25 |
| `audit_history_for_intent` | the whole audit trail behind one intent | 1000 | 0.154 | 0.658 | 0.712 | 25 |
| `queue_recent` | the operator dispatch queue, newest first | 10000 | 0.210 | 0.428 | 1.169 | 25 |
| `attempt_by_intent` | the single attempt for one intent | 10000 | 0.125 | 0.309 | 0.479 | 25 |
| `attempt_by_client_order_id` | the reconciliation identity lookup | 10000 | 0.167 | 0.465 | 0.482 | 25 |
| `reconciliation_candidates` | attempts still needing reconciliation | 10000 | 0.167 | 0.445 | 0.554 | 25 |
| `audit_history_for_intent` | the whole audit trail behind one intent | 10000 | 0.154 | 0.324 | 0.846 | 25 |

## Query plans at the largest scale

The plan matters more than the
number: a sequential scan that is fast on ten thousand rows is still a
sequential scan, and it is the plan that says whether the next order of
magnitude will hurt.

### `queue_recent` at 10000 rows

```
Limit  (cost=0.29..2.13 rows=20 width=51) /   ->  Index Scan using ix_paper_attempt_claimed_desc on paper_execution_attempt  (cost=0.29..924.22 rows=10000 width=51)
```

### `attempt_by_intent` at 10000 rows

```
Index Scan using uq_paper_attempt_one_per_intent on paper_execution_attempt  (cost=0.29..8.30 rows=1 width=16) /   Index Cond: ((intent_governance_id)::text = 'INT-PERF-000500'::text)
```

### `attempt_by_client_order_id` at 10000 rows

```
Index Scan using uq_paper_attempt_client_order_id on paper_execution_attempt  (cost=0.29..8.30 rows=1 width=16) /   Index Cond: ((client_order_id)::text = 'm085-perf-000500'::text)
```

### `reconciliation_candidates` at 10000 rows

```
Limit  (cost=0.29..9.90 rows=50 width=24) /   ->  Index Scan Backward using ix_paper_attempt_claimed_desc on paper_execution_attempt  (cost=0.29..961.72 rows=5000 width=24) /         Filter: ((state)::text = ANY ('{PAPER_SUBMITTED,PAPER_ACCEPTED,SUBMISSION_UNKNOWN}'::text[]))
```

### `audit_history_for_intent` at 10000 rows

```
Incremental Sort  (cost=8.31..8.36 rows=2 width=31) /   Sort Key: occurred_at, event_id /   Presorted Key: occurred_at /   ->  Index Scan using ix_paper_event_intent_occurred on paper_execution_event  (cost=0.29..8.30 rows=1 width=31) /         Index Cond: ((intent_governance_id)::text = 'INT-PERF-000500'::text)
```

## What measurement changed

The first run of this harness found the operator queue read doing a **Seq Scan
plus a Sort over every row**: `ORDER BY claimed_at DESC, attempt_id DESC` with no
state filter cannot use the `(state, claimed_at)` composite index. At ten thousand
rows it still answered in about 2ms, which is exactly the trap -- the number looked
fine and the plan did not.

`ix_paper_attempt_claimed_desc` was added to the migration BECAUSE of that plan,
not because indexing a timestamp seemed prudent. Measured before and after, at
10,000 rows:

| Query | Before | After | Plan before | Plan after |
|---|---|---|---|---|
| `queue_recent` | 2.048 ms median | 0.262 ms median | Seq Scan + Sort | Index Scan |
| `reconciliation_candidates` | 2.331 ms median | 0.136 ms median | Seq Scan + Sort | Index-backed |

These tables are append-only and therefore only grow, so a full sort on every
queue read is a defect that gets worse rather than a cost that stays constant.

## What this does and does not establish

- It establishes that the operator-facing reads are index-backed where an index
  exists, and shows the plan for each so a future regression is visible.
- It does NOT establish production throughput, behaviour under concurrent load,
  behaviour on other hardware, or any claim about how many orders this product
  could dispatch. It dispatches one, after a human authorizes it.
- The append-only tables grow without bound by design. Nothing here is a retention
  policy, and this milestone does not add one.

