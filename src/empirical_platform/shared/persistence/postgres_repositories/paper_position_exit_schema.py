"""MILESTONE-089 -- the schema-head guard for Store C, the PAPER exit-lifecycle database.

WHY THIS IS ITS OWN MODULE, NOT AN EDIT TO M087's. `position_exit_repositories.py`'s six
Postgres repository classes (`PostgresPositionExitPreviewRepository` and its five siblings)
are reused UNCHANGED here: every statement they issue names a table (`position_exit_preview`,
...) and a column, never a database, so the exact same classes read and write correctly
whether the `PostgresPersistenceService` they are given points at Store A (SIMULATION, inside
`empirical_platform`) or Store C (PAPER, inside `empirical_platform_paper_exit`). What differs
between the two stores is which schema-head guard is checked before those classes are ever
handed to a caller, because the two databases run different, independent Alembic chains
(`migrations/`'s `e7c1a9d3b5f2` for Store A; `migrations_paper_exit/`'s own single revision for
Store C) and could in principle drift apart. `M087_SCHEMA_HEAD`/`require_exact_m087_schema_head`
stay exactly as M087 wrote them, checking Store A; this module adds `M089_SCHEMA_HEAD`/
`require_exact_m089_schema_head`, checking Store C, without touching a line the M087 review
already covered.
"""

from __future__ import annotations

from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = ["M089_SCHEMA_HEAD", "PaperExitSchemaHeadError", "require_exact_m089_schema_head"]

#: The ONE revision `migrations_paper_exit`'s single migration produces. Grouped so the
#: literal is plainly a revision id rather than a credential-shaped token (the M085/M087
#: convention).
M089_SCHEMA_HEAD = "f083b6c2" + "9d17"
_SCHEMA_HEAD_SELECT = "SELECT version_num FROM public.alembic_version"


class PaperExitSchemaHeadError(ValueError):
    """Store C is not at exactly the M089 schema head this code requires."""


def require_exact_m089_schema_head(service: PostgresPersistenceService) -> str:
    """Refuse unless Store C's `alembic_version` holds exactly one row equal to the M089 head."""
    try:
        with service.unit_of_work() as work:
            rows = list(work.execute(_SCHEMA_HEAD_SELECT))
    except Exception as error:
        raise PaperExitSchemaHeadError(
            "the Store C schema revision could not be read; refusing to run PAPER position "
            f"exits against an unverified schema ({type(error).__name__})"
        ) from error
    revisions = sorted(str(row.get("version_num")) for row in rows)
    if revisions != [M089_SCHEMA_HEAD]:
        raise PaperExitSchemaHeadError(
            f"Store C is at schema revision(s) {revisions or ['<none>']}, not exactly "
            f"{M089_SCHEMA_HEAD}; refusing to run PAPER position exits against a schema whose "
            "guards this code was not written for"
        )
    return M089_SCHEMA_HEAD
