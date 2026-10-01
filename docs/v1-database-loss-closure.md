# V1 database loss closure — pending legacy-tool protection

Status: **BLOCKED_FROZEN_DESTRUCTIVE_TOOL**. Do not initialize the real stores.
This change is not a claim that historical execution data was recovered.

## Bounded investigation

Classification: **CAUSE_NOT_PROVEN**.

The previously established endpoint remains localhost:55433, Store B
`empirical_platform_paper`, Store C `empirical_platform_paper_exit`. Both public
schemas are empty, with no Alembic revision or prior execution rows. Windows User
and process configuration point to those stores. Database discovery was not repeated.

The M089 real round-trip document records a filled entry, a filled exit, and a
closed-verified lifecycle on September 30. The prior local session records that
Store B was on localhost:55433. October 1 session evidence reports empty stores,
a later empty-schema migration, and destructive PostgreSQL tests launched without
explicit database overrides. Their fixtures used `DROP SCHEMA public CASCADE`.
This is a plausible deletion mechanism, but the retained evidence does not prove
the first deletion, the exact inherited environment of every invocation, or an
exclusive cause. No person or process is identified as the proven cause.

The bounded backup search examined 347,112 files under Documents, OneDrive,
LocalAppData/EmpiricalPlatform, and `.empirical`, excluding dependency/cache trees.
It found no candidate logical backup containing the lost history. The known
`empirical-platform-postgres.bak-20260927` directory predates M089. It has not been
started or restored and is not classified as a verified recovery backup.

Local sanitized evidence and search results are in
`.generated/v1-verification/database-connection-recovery.md` and
`.generated/v1-loss-closure/forensics.json`. The original historical execution
evidence is `external-review/MILESTONE-089/real-paper-round-trip-2026-09-30.md`.
Historical governance failures recorded there remain failures.

## Implemented boundaries

The independent Windows manifest is
`%LOCALAPPDATA%/EmpiricalPlatform/safety/personal-paper.json`. It records
PERSONAL_PAPER identities, the exact endpoint, reviewed heads, a history-count
baseline, and explicit initialization state. Its current state is LOSS_DETECTED.
It contains no credentials. Neither startup nor backup can bless an empty database.

Paper startup checks the manifest, database-level identity comment, exact head,
and history floor before constructing the broker-facing runtime. Missing schema,
identity, revision, or a lower count fails closed. Existing integrated physical
schema-contract checks remain in force. Database comments survive a schema drop;
the external manifest survives database deletion. Installing the database comments
on the real stores is deferred because that would be a database write.

PostgreSQL pytest engines, the shared M085/M089 fixture builders, and current M085
campaign entry points require TEST mode, a name ending in `_test`, and the
independent database comment `EMPIRICAL:TEST`. The personal database names, names
registered in the external manifest, and port 55433 are rejected before connecting.
The database marker is checked before fixture transactions begin, including direct
SQLAlchemy engines. CI explicitly provisions and marks empty disposable databases.
`tools/mark_test_database.py` cannot relabel a populated or independently identified
database. Ordinary online Alembic commands refuse the protected real database names.

These are operational accident guards, not a security boundary against a database
superuser or a deliberately bypassed Python process. The remaining legacy-tool gap
below must be closed before claiming complete destructive-tool isolation.

## Exact blocker

`tools/m084_mutation_campaign.py` accepts an arbitrary `--database` (line 641 at
the reviewed source) and `_rebuild_schema()` executes `sudo ... psql ... DROP
DATABASE` before the migration/pytest guards run. A direct invocation can therefore
target a personal store. The other frozen M084 launchers also use raw psql without
the new independent-identity preflight. They must not be run against the personal
cluster.

The repository's M083/M084 frozen-path policy requires byte identity to the
owner-ratified baseline. Both `tools/check_frozen_paths.py` and
`tests/architecture/test_frozen_paths.py` enforce it; the exemption set is empty.
Changing this M084 tool directly would fail that required gate. Merely wrapping it
would leave its direct entry point unsafe. The guard and baseline were not weakened.
The necessary next step is an explicitly ratified safety correction to the frozen
tooling, with refusal tests for personal names, personal markers, and port 55433,
followed by the full gates. Until then the requested readiness label is withheld.

## Backup operation and limits

`scripts/register-personal-paper-backup.ps1 -Repository <release-checkout>` registers
the Windows task **EmpiricalPlatform Personal Paper Backup**, hourly, without
overlapping runs. The installed task runs as the current user while logged on and
catches up when available. It does not provide backups while this machine is off
or the user is logged out. No password is embedded in its command line.

`scripts/backup-personal-paper.ps1` loads only PostgreSQL Windows User environment
variables. The Python backup tool validates each identity/head/history floor inside
a read-only repeatable-read transaction and exports that snapshot to `pg_dump`.
It uses custom-format dumps and validates each archive with `pg_restore --list`.
Completed pairs include SHA-256 file digests and source identities. An incomplete
pair stays `.partial`, cannot become a recovery candidate, and never triggers
retention. Concurrent runs are excluded by an exclusive filesystem lock. A stale
lock requires investigation, not automatic deletion.

Retention keeps 168 completed pairs (approximately seven days at hourly success).
Only recognized sets whose two archive hashes still verify are eligible for
deletion. Unknown, corrupt, and incomplete files remain for investigation. Retention
requires a new successful pair; LOSS_DETECTED cannot rotate old backups away.
After success, history floors advance to the snapshot's counts. The local status
file is `%LOCALAPPDATA%/EmpiricalPlatform/safety/backup-status.json`; a nonzero task
result requires attention. The currently installed task correctly reports exit 2,
BACKUP_BLOCKED, because the real stores are in LOSS_DETECTED. This is not a successful
backup of the missing history.

The automated PostgreSQL rehearsal creates separate disposable databases, dumps
both, restores to different disposable databases, verifies their data, verifies
retention, and proves that a reduced history count blocks the next pair without
deleting good backups. It never calls a broker. It runs in the deployment CI job.

Each store has its own consistent snapshot; the pair is not a cross-database atomic
snapshot. Restore requires reconciliation with broker state before any runtime is
enabled. This local backup protects against logical deletion, not loss of the same
disk or machine. An independently secured off-machine copy remains an operational
follow-up. Dumps contain private trading data and must stay out of Git.

## Restore procedure — operator execution only

1. Keep Paper runtimes stopped, preserve incident evidence and the current manifest,
   and disable the backup task while investigating. Do not delete existing backups.
2. Select a complete pair, verify both SHA-256 digests against `complete.json`, and
   inspect both `pg_restore --list` outputs. Confirm source identities, revisions,
   and timestamps. A structurally valid dump is not proof of the desired history.
3. Rehearse restoration to newly created, explicitly named `_test` databases on an
   isolated cluster. Use `pg_restore --no-password --exit-on-error --dbname=<target>
   <archive>` with credentials supplied securely through the environment. Never use
   `--clean` on a real database. Verify required durable records and schema contracts.
4. Review consistency between entry and exit records and actual broker state using
   read-only evidence. Resolve uncertainty before enabling a runtime; do not create
   fabricated execution rows to make reconciliation appear successful.
5. Obtain explicit authorization for the concrete real restore targets and downtime.
   Preserve any existing real state separately. Restore only the approved pair.
6. Install/revalidate the approved PERSONAL_PAPER database comments, exact heads and
   history floors. Change the external manifest to INITIALIZED only after verifying
   the restored state. Re-enable backups and require a verified successful new pair.
   Runtime startup and broker actions remain separate authorization steps.

## Clean initialization preparation — not executed

The local review artifacts
`.generated/v1-loss-closure/store-b-initialize-REVIEW-ONLY.sql` and
`store-c-initialize-REVIEW-ONLY.sql` were generated with Alembic's offline `--sql`
mode, at B `b9f2c4d6a8e1` and C `f083b6c29d17`. Generation makes no connection and
does not change either real store. The artifacts are complete SQL plans, not
evidence that initialization occurred.

After the blocker above is resolved, review the SQL and obtain explicit approval
for permanent loss acknowledgement and clean initialization. Immediately before
execution, verify the exact endpoint and empty schemas again. Apply only the
reviewed offline scripts with `psql -X --set ON_ERROR_STOP=1`, explicit host/port/name,
and an administrative credential; never feed a wildcard or inferred database name.
Apply the B/C identity comments from the independent manifest to their exact stores.
Use separate owner/maintenance and runtime roles, with no DDL/TRUNCATE/database
ownership for the runtime role; review the existing shared role before changing its
privileges because the simulation environment also uses this cluster.

Verify exact heads and physical contracts, explicitly record a new empty baseline
of zero as a clean start (not restored history), then set INITIALIZED and require the
first verified backup. Keep historical loss and M089 evidence documented separately.
No automatic transition, migration, reset, restore, synthetic historical insert, or
broker action is included in this preparation.
