# PR #40/#41 deployment procedure (`tools/personal_paper_deploy.py`)

## What this closes

The Oct 20 incident led to PR #40 (trigger-evidence persistence, migration `f3a7c9e2b164`)
and PR #41 (the exit signal quality gate), both merged into `release/v1-personal-paper` at
`3a0d3c9f7959543ad2ba4c7072fd362efaa90b3e`. Deploying them into PERSONAL_PAPER requires a
Store B schema migration -- and `alembic upgrade` in online mode is **unconditionally refused**
for Store B/C (`refuse_unplanned_personal_migration`, `database_safety.py`) before it ever
connects. There is no "just run alembic" path for this database, by design. This script is
the reviewed, auditable, narrowly-scoped tool that performs the deployment anyway, safely.

## The 14 steps

1. **Broker verify** -- the real Alpaca PAPER account is `ACTIVE`, not blocked, and flat
   (zero positions, zero open orders, zero orders in an ambiguous/unknown state).
2. **No in-flight work** -- no `paper_execution_attempt`/`position_exit_attempt` row is in a
   non-terminal state in Store B/C.
3. **Release head** -- the release worktree is clean (`git status --porcelain` empty) and at
   exactly the expected, approved commit.
4. **Backup** -- a fresh Store B+C backup via `tools/personal_paper_backup.py`, with its
   SHA-256 and structural readability (`pg_restore --list`) independently re-verified here,
   not just trusted from the backup tool's own report.
5. **Graceful shutdown** -- the running console is sent `CTRL_BREAK_EVENT` (Windows) / `SIGTERM`
   (POSIX) and this step waits for it to actually exit.
6. **Verify stopped** -- process gone, the backup tool's own lock file clear, and port 8189
   (or whichever port is configured) is free at the OS level.
7. **Migrate** -- the ONE pending migration, `f3a7c9e2b164`, applied via the exact, hash-pinned
   offline SQL in `tools/personal_paper_deploy_migration_f3a7c9e2b164.sql`, run with `psql -f`
   after an explicit identity + pre-image-head re-check. Idempotent: a second call sees the
   post-migration head already in place and does nothing.
8. **Verify schema** -- the new head, the 4 new columns, the 2 new CHECK constraints and the
   updated guard function are all independently re-queried and confirmed present.
9. **Verify unchanged** -- Store B's `paper_execution_attempt` and Store C's
   `position_exit_attempt` row counts are compared against the manifest's own
   `minimum_attempts` (set by step 4's backup, under REPEATABLE READ, with the console already
   stopped) -- not against an in-process value, which would not survive a crash between steps.
10. **Manifest update** -- atomic rewrite: Store B's recorded head moves to `f3a7c9e2b164`, a
    `last_migration` audit record is added (revision, timestamp, release head, migration SQL
    hash, backup location, pre/post heads), and a byte-for-byte copy of the pre-change manifest
    is written alongside it first.
11. **Fast-forward** -- the worktree is fast-forwarded (`git fetch` + `merge --ff-only`) to the
    exact expected head, and -- critically -- this step then parses the worktree's OWN
    `migrations/`/`migrations_paper_exit/` chains and refuses to proceed unless their head
    matches the schema that is now actually live. This is the explicit gate against starting
    new code against an old schema, or old code against a migrated one.
12. **Recovery-mode start** -- the console is started with `--recovery-mode` (read-only; no
    automatic Plan Manager is built; no exit, automatic or manual, can be sent).
13. **Verify startup** -- `/safety` confirms the automatic manager is NOT reported running,
    `/health` confirms a flat broker position, and the schema identity/head are re-checked one
    more time against the manifest.
14. **Stop.** There is no step 15. Transitioning to Active Mode is always a separate, explicit,
    Owner-authorized action taken outside this script.

## Usage

```
python tools/personal_paper_deploy.py \
  --repo-path <release worktree> \
  --expected-release-head <commit sha> \
  --manifest-path <path to personal-paper.json> \
  --backup-root <path> \
  --pg-bin "C:\Program Files\PostgreSQL\16\bin" \
  --console-host 127.0.0.1 --console-port 8189 \
  --console-pid <running console PID> \
  --journal-path <path to deploy-journal.json> \
  [--confirm-production]
```

`EMPIRICAL_ALPACA_PAPER_API_KEY`/`_SECRET_KEY` and `EMPIRICAL_PLATFORM_POSTGRES_*` (Store B)
are read from the environment, fresh, never logged.

**Store C's connectivity (M096 fix):** the real topology is one Postgres server, two
databases -- the real console entrypoint
(`_paper_position_exit_composition.resolve_paper_exit_postgres_config`) reuses Store B's
host/port/user/password verbatim for Store C and only swaps the database name, and the real
environment never sets `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST`/`_PORT`/`_USER`/
`_PASSWORD` at all. This script now resolves Store C the same way:
- If `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST` is **not** set (the real shape today),
  Store C reuses Store B's host/port/user/password, with only the database name taken from
  `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE` (default `empirical_platform_paper_exit`).
- If `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST` **is** set, Store C is treated as
  independently configured and every `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_*` field
  (`_HOST`/`_PORT`/`_USER`/`_PASSWORD`/`_DATABASE`) is resolved on its own -- for a future
  topology where the two stores are split across servers.
- Setting `_PORT`/`_USER`/`_PASSWORD` without `_HOST` is refused (ambiguous partial
  override) rather than silently mixed with Store B's values.

An earlier version of this script always required the fully independent form, which the
real environment never satisfies -- invoking it against production crashed with an
unhandled `KeyError` before touching anything (found during the 2026-10-22 read-only
preflight; CI never caught it because every test set all five
`EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_*` variables itself).

**`--confirm-production` is required, and only accepted, when EITHER `--manifest-path`
resolves to the real default production manifest path**
(`%LOCALAPPDATA%\EmpiricalPlatform\safety\personal-paper.json`) **OR the resolved Store B/C
database (from the ambient `EMPIRICAL_PLATFORM_POSTGRES_*`/`EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_*`
environment) is one of the real, protected databases** -- the same `PERSONAL_DATABASES`
frozenset `database_safety.py` itself uses. An earlier version of this guard checked only the
manifest path; an independent review found that a decoy `--manifest-path` with the ambient
environment still pointed at the real databases would have bypassed it entirely. Any
mismatched combination -- the flag without either real target, or either real target without
the flag -- is refused before anything is touched. There is no flag combination that silently
targets production.

## Journal and resumability

Every step writes a `started`/`completed`/`failed` record (with a timestamp and a human-
readable detail) to the journal file before and after it runs. Re-running the script with
the same `--journal-path` skips steps already marked `completed` and resumes from the first
incomplete one. Every step is independently idempotent to being re-run, and the parts of
state a later step needs that would not survive a crash (the backup location for step 10, the
pre-migration row-count baseline for step 9) are re-derived from durable sources -- the backup
directory on disk, the manifest's own `minimum_attempts` -- rather than passed as in-memory
values between steps.

## Failure and recovery

Every failure raises `DeploymentBlockedError(step, reason)`, whose message combines the
concrete reason with step-specific recovery guidance (see `_RECOVERY_TEXT` in the script).
Summary by phase:

| Boundary | What's guaranteed | Recovery |
|---|---|---|
| Before/during backup | Nothing in Store B/C touched | Investigate, re-run from the top |
| Before/after shutdown | Console state is checked, never assumed | Confirm process/port by hand, re-run |
| Before migration | Store B still at the pre-migration head | Re-run once the refusal reason is fixed |
| During migration | The SQL is one transaction (BEGIN/COMMIT); a failure before COMMIT leaves Store B unchanged -- verify directly, don't assume | **Never** downgrade or restore without separate Owner authorization |
| After migration, before manifest update | Schema is migrated; manifest still says the old head | Re-run step 10 alone; it re-derives everything it needs from disk |
| After manifest update, before restart | Manifest and schema agree; console still stopped | Fix the worktree/process state, nothing DB-related needs touching again |
| During recovery-mode startup | Migration and manifest are already correct | Check the captured log, confirm the port is free, re-run step 12 |

**Rolling back an applied migration is never assumed safe and this script never attempts it.**
The pre-migration backup from step 4 is always preserved; restoring from it is a separate,
explicit, Owner-authorized, out-of-band action.

## Testing

- `tests/unit/test_v1_personal_paper_deploy.py` -- fakes for the broker, process control and
  network ports; the journal state machine; recovery-instruction text for all 14 steps;
  migration-chain-head parsing (including this repo's split-hex-literal revision style); the
  manifest update's atomicity/idempotency/pre-change-copy guarantee; and a full-pipeline
  harness that injects a simulated failure at each of the 14 boundaries in turn and asserts the
  journal is accurate and resuming replays nothing already completed.
- `tests/integration/test_v1_personal_paper_deploy_postgres.py` -- the same steps against real,
  disposable Store B/C databases rebuilt from the actual migration chains (never
  hand-fabricated), plus a real dummy console subprocess for the graceful-shutdown/
  recovery-start steps' real OS process and TCP port mechanics. Requires
  `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` and a disposable Postgres server; see the module
  docstring for why it does NOT use `install_test_connection_guard()` the way other Postgres
  suites do, and why it is its own isolated pytest invocation in CI.

## Known residual risk

Identity-matching between the manifest and the real database comment cannot be exercised
end-to-end against a real, disposable Postgres instance in this repository's own test harness:
`tests/conftest.py` installs a session-wide guard requiring every TEST-shaped database's
identity comment to be the literal `EMPIRICAL:TEST` for the whole process, while `read_manifest`
requires a manifest's `identity` field to start with `PERSONAL_PAPER:{store}:`. The integration
suite works around this by faking only the identity half of the one internal function that
reads it (see that file's module docstring) -- the real production check this exercises was
already independently verified read-only against the live Store B/C identities during the Oct
21 deployment preflight.

**Step 4's backup topology assumption (pre-existing, not introduced here):**
`tools/personal_paper_backup.py::backup()` derives its Postgres connection via
`resolve_foundation_config().postgresql` -- a config-resolution path independent of this
script's own `store_b_config`/`store_c_config` -- and reuses that SAME host/user/password for
both stores, only swapping the `database` field for Store C. This is correct for the real
PERSONAL_PAPER topology (confirmed read-only during the Oct 21 preflight: Store B and Store C
share the same host and port, `127.0.0.1:55433`), but would silently back up Store C with the
wrong credentials if the two stores were ever split across different Postgres servers. Not a
gap this PR introduces or fixes; flagged here because an independent review raised it.
