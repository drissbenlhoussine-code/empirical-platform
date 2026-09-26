# Exact-SHA verification — crash-consistent attempt lineage (L1)

CODE_CANDIDATE_SHA: **`806896bc5fb2ae9c2bfe24fe26b4aebf96867651`** (`806896b`), parent
`b80ef2829867aa7684bd4dc6dc666e2b958b2f13` (the preserved, unpublished exact-head CI record for
`6b6518c`), on `feature/m085-alpaca-paper-human-approved-execution`. Every commit after `806896b`
in this round is verified docs-only (`git diff --name-status` restricted to `external-review/`)
or names its executable change explicitly (the V1 renderer correction, §6).

All commands ran in the foreground, one at a time, on a clean tree at the named SHA (`dirty=0`
printed at the head of every log in `runs-806896b/`). Mutation chunks never overlapped another
test run. No Alpaca endpoint was called; PostgreSQL tests used the disposable database
`m085_pgon_b24c471`; `m085_acceptance_2e5c38c` was not touched.

## 1. Environment (printed)

Windows 11 Pro 10.0.26200; Python 3.13.14; pytest 9.1.1; psycopg 3.3.4 pinned `PSYCOPG_IMPL=python`
over libpq 16.0.13 (`impl python libpq 160013` printed by R2/R3); SQLAlchemy 2.0.51; alembic 1.18.5;
PostgreSQL 16.13 on 127.0.0.1 with trust auth for the disposable role (no password exists; the
env variable carries the literal placeholder `trust-auth-placeholder-not-a-credential`);
detect-secrets 1.5.0; ruff 0.16.3; mypy 1.20.2. No CI has run on `806896b` (not pushed).

## 2. Results on `806896b`

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused | `test_m085_pre_send_crash.py` (24), send boundary (19), identity lineage (67), identity collision, handlers, corrective pass (domain + handlers), domain, entrypoints, hostile HTTP (125), acknowledgement terms (15), send-boundary transport (2) | **820 passed** | `runs-806896b/R1-focused.txt` |
| R2 PostgreSQL | **`test_m085_pre_send_crash_postgres.py` (3, real child-process death)**, temporal 7 (one test corrected, §4), time-basis 48, lifecycle 57, concurrency 49, corrective pass 62, identity collision 7, authority contract 71, M084 file audit 23 | **327 passed** | `runs-806896b/R2-postgres.txt` |
| R3 non-PostgreSQL full suite | `pytest tests`, PostgreSQL opt-in unset | **4055 passed, 0 failed, 1236 skipped** (all opt-in gates; +3 versus `00716e4` = the new PostgreSQL crash tests); **coverage 80.39 % ≥ 79 %** (20 411 statements / 3 481 missed) | `runs-806896b/R3-full-non-pg.txt` |
| R4 mutations | the **102** families whose target file changed `00716e4..806896b` (domain 68, usecases 34 — includes the 5 new L1 families); five sequential chunks; whole-tree SHA-256 before/after | **102 / 102 detected**; digest `a8bce8c2…a2fabf` identical before and after every chunk; tree clean after each | `runs-806896b/mutation-chunk-0{0..4}.md`, `R4-chunk-0{0..4}.txt`, `affected-families.txt` |
| R5 static | compileall; ruff format `--check` (750 files); ruff check; mypy (368); architecture + negative fixture; frozen-path guard (M083 27 + M084 69 = 96, by blob id and diff); architecture/frozen tests (41); authority renderers M082–M085 `--check`; M084 file audit (75); pip-audit (no known vulnerabilities); build | **green** | `runs-806896b/R5-static.txt` |
| R5 secret scan | `scripts/security.ps1` (venv on PATH) — 1414 targets | **1 finding** — see §3 | same log |

Not summed anywhere: R2 re-executes files R1 does not; R1's domain files overlap R3.

Pre-commit runs on the same executable content (working tree before `806896b`): PostgreSQL 327
passed (`l1/pg-suites-on-fixed-worktree.txt`); the 5 new and 16 affected lineage / send-boundary /
reconcile families 21/21 detected (`l1/precommit-mutations.md`), whole-tree digest identical
before and after (`a8bce8c2…a2fabf`, first 16 hex `a8bce8c248b67622`).

## 3. The secret-scan finding, and what was done about it

After `806896b` made the evidence tracked, the repository scanner reported one finding:
`external-review/MILESTONE-085/crash-consistent-lineage/l1/precommit-mutations.txt` line 2,
"Hex High Entropy String" — the campaign's **whole-tree SHA-256 digest** (`tree digest before:
a8bce8c2…`) in my stdout capture. It is not a credential. detect-secrets' entropy threshold fires
on this digest and not on the earlier chunk logs' digests (`b484179c…`, `5576bb5c…`) by chance of
entropy, and the scanner's benign filter clears only values git actually holds (blob ids), which
a tree digest is not. A captured log is not edited to satisfy a scanner. Disposition: the redundant
stdout capture is **removed from the tracked evidence** in the docs-only commit that follows
`806896b`, with this note; the same run is fully recorded by the campaign's own report
`l1/precommit-mutations.md` (21 rows, each `EXECUTED_PASS`, restore digests per family) and the
digest is quoted above. The capture remains in the history of `806896b`. The scan is re-run on the
docs commit (§6).

## 4. Crash-boundary results (the finding's own scenarios)

| Boundary | On `00716e4` (before) | On `806896b` (after) | POSTs |
|---|---|---|---|
| A. historical order exists; death DURING the pre-send lookup | attributed: `FILLED`, `broker_order_id=broker-historical`, `RECONCILED` (unit and PostgreSQL child death) | `SUBMISSION_IN_PROGRESS`, `broker_order_id=None`, `IDENTITY_OBSERVED_NOT_ATTRIBUTED`; still unresolved at +300 s; a new dispatch is refused | 0 |
| A′. death right after `SUBMISSION_IN_PROGRESS`, before any read | attributed (unit) | observed, not attributed | 0 |
| B. historical order FOUND; death before the observation was persisted | attributed (unit and PostgreSQL child death) | observed, not attributed | 0 |
| C. positive control: our POST left; death before the acknowledgement | recovered `PAPER_ACCEPTED` / `broker-1` (unit), `broker-child-1` (PostgreSQL) | unchanged: recovered, `SEND_BOUNDARY_ENTERED` present, no resend, repeat dispatch refused | 1 |
| death DURING the boundary write | n/a | no record → no lineage → observed, not attributed | 0 |
| death right AFTER the boundary write | n/a | lineage by design (identity verified absent at 404 moments before); absence never resolves it | 0 |
| database failure at the boundary write | n/a | `REJECTED` / `NOT_SENT`, `DISPATCH_NOT_SENT`, no record | 0 |
| database failure at the write AND at the refusal | n/a | process error; `IN_PROGRESS` without record → no lineage | 0 |
| authorization expires during the write | n/a | `NOT_SENT`; the record exists but the unsent marker outranks it | 0 |
| kill switch engages during the write | n/a | `NOT_SENT` | 0 |
| concurrent reconciliation while the dispatcher is inside its lookup | n/a | reconciler: observed, not attributed; dispatcher then observes the order → `SUBMISSION_UNKNOWN` / `IDENTITY_EXISTS_UNSENT` | 0 |
| tampered account in the persisted record (after our POST) | n/a | not attributed (`IDENTITY_OBSERVED_NOT_ATTRIBUTED`) | 1 (the original) |

Two existing tests encoded the gap (an interruption before any send, asserting adoption) and were
corrected to interrupt after the request left, asserting exactly one POST:
`test_m085_temporal_postgres.py::test_reconciliation_resolves_an_interrupted_dispatch_through_the_database_edges`
and the `_stuck_in_progress` helper of `test_m085_corrective_pass_handlers.py` (its consumers now
count the dispatcher's own pre-send lookup). No gate weakened.

## 5. Self-review

**Proven.** The boundary record is written after the identity lookup (404) and every preparatory
read, and before the kill-switch read and time sample (ordering pinned in
`test_m085_send_boundary.py`; family `final_checks_follow_the_boundary_write`); lineage requires
it for `IN_PROGRESS` and for transmitted-looking UNKNOWN codes (`lineage_requires_the_send_boundary_record`);
it binds field by field (`send_boundary_record_is_bound_field_by_field`, 8 tampers); reconciliation
checks the account (`historical_adoption_requires_the_account_binding`); removing the write breaks
legitimate recovery (positive control `send_boundary_recorded_before_the_send`). Unsent markers
still deny first (`lineage_unsent_never_attributed`).

**Residuals (recorded, not hidden).**
- S-1 The window between the boundary write and the POST leaves lineage with no request sent. It is
  the price of a durable send-capable phase and is bounded by the `identity_lookup=404` the record
  carries. Attribution in that window can only be of an order that appeared *after* the identity
  was verified absent — which is also exactly the order a completed POST would have created.
- S-2 The boundary event is one more database write inside `before_send` (after the reads, before
  the final checks). Its latency is covered by the final checks (tests above); its failure is a
  definite not-sent. It adds no network operation between decision and POST.
- S-3 Legacy `SUBMISSION_UNKNOWN` records with `AMBIGUOUS`/`UNUSABLE_ANSWER`/`UNCERTAIN_HTTP_*`
  created before this correction have no boundary record and will now be **observed, not
  attributed** (visible, unresolved) rather than adopted. There are none in any acceptance database
  (Paper acceptance NOT_STARTED; the disposable databases are rebuilt per run). No backfill.
- S-4 The record's binding lives in the event `detail` (≤ 500 chars, ~300 used) as `key=value`
  tokens, verified by parsing; the event table's `event_type` is a free string, so no migration or
  authority change was needed. A future round may prefer typed columns; the current shape is
  verified by tests and families.
- S-5 R-1 from the previous round (a stale pre-opened socket yields an uncertain attempted send,
  never a refusal, never a retry) is unchanged.

## 6. Commits after the code candidate

| Commit | Content | Executable change |
|---|---|---|
| (docs commit following `806896b`) | this record; `runs-806896b/` logs; `l1/precommit-mutations.txt` removed (§3); README pointer | none |
| (V1 renderer correction) | see [../v1-exhaustion-table-correction.md](../v1-exhaustion-table-correction.md) | `tools/render_m085_exhaustion_table.py` + its tests only; verified by its own gates (recorded there) |

## 7. Outcome

L1: **REPRODUCED_AND_FIXED**. Recommendation for this round: READY_FOR_OWNER_PUBLICATION_APPROVAL
— local commits only; not pushed; not merged; not frozen; not OWNER_ACCEPTED; not READY_FOR_PAPER;
Paper acceptance NOT_STARTED; M086 NOT_STARTED.
