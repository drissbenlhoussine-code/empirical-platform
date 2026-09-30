"""Shared fixtures for the MILESTONE-090 Opportunity Engine integration suite.

Not a test module. `opportunity`/`opportunity_decision` live in the SAME database Track A's
migrations (M057-M073) and M084's own tables already use -- reuses `_m085_support.py`'s
`config()`/`build_engine()`/`postgres_enabled()` directly rather than a new Store, exactly as
`external-review/MILESTONE-090/scope-and-design.md` Section 4 documents. `truncate_all_m090`
only needs to know about the two tables THIS milestone adds; `_m085_support.truncate_all`
already handles M084/M085's own tables when a test also touches those.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

#: The two MILESTONE-090 tables, in dependency order for TRUNCATE (the decision references the
#: opportunity via a real foreign key, so it must be named first).
M090_TABLES = ("opportunity_decision", "opportunity")


def truncate_all_m090(engine: Engine) -> None:
    """Empty every MILESTONE-090 table THAT EXISTS (a downgraded database may lack them)."""
    with engine.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
        existing = [table for table in M090_TABLES if table in present]
        if existing:
            connection.execute(text("TRUNCATE " + ", ".join(existing)))
