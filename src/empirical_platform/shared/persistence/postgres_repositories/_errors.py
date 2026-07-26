"""Shared PostgreSQL repository-adapter error-translation helper (MILESTONE-023).

Structural-fact-only translation from real PostgreSQL failures (never parsed
message text) to the constraint name a unique-violation failure names, for a
caller to map onto the frozen MILESTONE-020 `RepositoryContractError`
vocabulary. See MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md
Section 9.2.
"""

from __future__ import annotations

from empirical_platform.shared.errors import FoundationError

_UNIQUE_VIOLATION_SQLSTATE = "23505"


def unique_violation_constraint_name(error: FoundationError) -> str | None:
    """Return the constraint name a real unique-violation failure names, else None.

    Returns `None` whenever `error` does not represent a PostgreSQL
    unique-violation failure (SQLSTATE 23505) with a structured
    `constraint_name` diagnostic available; callers must treat that as an
    unclassified failure and leave it untranslated rather than guess.
    """
    cause = error.__cause__
    orig = getattr(cause, "orig", None)
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    if getattr(diag, "sqlstate", None) != _UNIQUE_VIOLATION_SQLSTATE:
        return None
    constraint_name = getattr(diag, "constraint_name", None)
    return constraint_name if isinstance(constraint_name, str) else None
