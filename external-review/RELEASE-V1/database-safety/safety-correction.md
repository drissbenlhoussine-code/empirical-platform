# M084 destructive-tool safety correction

Owner authorization: 2026-10-01, "AUTHORIZE FORMAL M084 SAFETY BASELINE CORRECTION".
This is a **safety correction / superseding operational baseline**, not a rewrite
of historical evidence. The original M084 baseline remains historical evidence.

## Defect discovered after the original freeze

`tools/m084_mutation_campaign.py::_rebuild_schema` accepted an arbitrary database
name and passed interpolated DROP DATABASE / CREATE DATABASE commands to sudo/psql
before the release's identity checks. The requested target could be personal Store
B or C. This was release-blocking. No historical loss is newly attributed to it;
the bounded loss investigation remains CAUSE_NOT_PROVEN.

## Exact authorized change

Only `_rebuild_schema` changed in the M084 tool. It now validates the explicit
TEST target, uses the configured SQLAlchemy endpoint, proves the independently
stored TEST marker and server-reported database/port, and resets public schema
in a transaction. It never issues DROP DATABASE. Preserving the database preserves
its independent identity marker. Migration uses the same Python interpreter that
performed the safety check, avoiding the old Linux-specific interpreter path.
The existing migration target and mutation/business rules remain unchanged.

The shared destructive-connection guard now rejects connection strings supplied as
names, malformed/overlong identifiers, server-reported personal names or personal
port 55433, endpoint/name mismatches, absent metadata, and anything except the exact
EMPIRICAL:TEST marker. Host aliases and URL query overrides do not establish identity.
These guards run before fixture/reset DDL and TRUNCATE. There is no automatic marking
of ambiguous databases and no force/bypass flag in the corrected reset.

No trading strategy, broker execution behavior, order semantics, risk policy,
historical evidence or unrelated M084 business logic is changed. An AST regression
compares the historical and current modules after removing only `_rebuild_schema`.

## Pinned identities

Hex groups below are concatenated to obtain each complete Git object identity.
They are grouped to avoid misclassifying public Git identifiers as secrets.

| Identity | Git object, grouped hex |
|---|---|
| Original ratified M084 commit | `11271346 23b25178 b4d98236 d5ab75f8 f2134760` |
| Original affected tool blob | `3b9c3e03 eccc4bc2 07737175 63d87771 0d54c8fe` |
| Corrected operational tool blob | `51665c99 decd9c84 bd486bc5 acc3a471 7acc6256` |

`baseline.json` is the machine-readable correction record. `original-tool.py.txt`
is a byte-preserving archive of the original Git blob, also keeping that original
object available in shallow checkouts. The original M084 digest manifest and commit
remain unchanged. The shared frozen-path gate accepts only the exact recorded
corrected tool blob and verifies the archived historical blob. Further tool changes
or historical-copy tampering fail the gate. No file was added to EXEMPT. The secret scanner verifies the original manifest
entry against the actual archived Git blob after supersession, rather than requiring
it to equal the corrected tool. Adversarial scanner tests retain findings for invented
digests, wrong paths and identical-looking entries outside the governed manifests.

This supersedes the original tool for **destructive operational use only**. The
archived original is retained for audit and must not be executed against personal
stores. The rest of the M084 frozen baseline remains governed by its original identity.

## Exact adversarial evidence

- `tests/unit/test_destructive_database_safety.py`: B/C names, quoted/case/URI/DSN/
  percent-encoded/SQL-injection names, overlength names, host aliases, actual endpoint
  mismatch, personal markers, absent/ambiguous markers and missing actual metadata;
  asserts no destructive SQL, no connection where preflight is sufficient, and no
  migration subprocess on refusal.
- `tests/integration/test_destructive_database_safety_postgres.py`: actual corrected
  tool against isolated PostgreSQL; durable canary survives each refused marker;
  SQLAlchemy/libpq dbname override plus localhost/IPv4 alias cannot enable TRUNCATE;
  exact TEST marker permits real schema reset and real Alembic migration to the
  reviewed current head; marker survives and no DROP DATABASE is emitted by the tool.
- `tests/architecture/test_database_safety_supersession.py`: original identities,
  exact scope, corrected baseline, detection of subsequent tool mutation, and
  fail-closed historical archive protection.
- Existing M084 unit/integration, full suite, architecture, destructive-tool and
  release deployment/backup checks are rerun. Local result logs live in
  `.generated/v1-safety-correction/`; PR #26 CI provides the committed-head checks.

## V1 loss closure boundary

This correction closes the legacy-tool blocker identified in
`docs/v1-database-loss-closure.md`. Real Store B/C remain uninitialized and the local
PERSONAL_PAPER manifest remains LOSS_DETECTED. No real database reset/migration,
restore, acceptance-console boot, synthesized historical row or broker write is
part of this correction. The previous guarded clean-initialization plans remain
review-only; readiness permits a later separately authorized initialization.
