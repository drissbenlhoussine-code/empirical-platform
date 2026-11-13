"""Supply explicit TEST identities to old secondary-database fixture addresses.

Only these named disposable probes are handled. Connection and migration safety
are never disabled. A pre-existing unmarked/personal target refuses before DROP.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine

from empirical_platform.shared.persistence.database_safety import (
    TEST_IDENTITY,
    DatabaseSafetyError,
    require_test_target,
)

_PROBES = {
    "test_m079_operator_evidence_availability_lifecycle.py": (
        "_PROBE_DATABASE",
        "m079_leak_probe_test",
    ),
    "test_m080_asserted_round_trip_lifecycle.py": ("_PROBE_DATABASE", "m080_leak_probe_test"),
    "test_m081_asserted_round_trip_ratio_lifecycle.py": (None, "m081_firewall_probe_test"),
    "test_m081_asserted_round_trip_ratio_second_pass.py": ("_DATABASE", "m081_second_pass_test"),
    "test_m082_operator_event_receipt_lifecycle.py": (None, "m082_probe_test"),
    "test_m082_operator_event_receipt_second_pass.py": ("_DATABASE", "m082_second_pass_test"),
    "test_m083_evaluation_evidence_watermark_second_pass.py": (
        "_DATABASE",
        "m083_second_pass_test",
    ),
}


@pytest.fixture(scope="module", autouse=True)
def isolated_secondary_database(request: pytest.FixtureRequest) -> Iterator[None]:
    spec = _PROBES.get(request.path.name)
    if spec is None:
        yield
        return
    attribute, name = spec

    def before(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, parameters, context, executemany
        if statement.startswith("DROP DATABASE") and f'"{name}"' in statement:
            require_test_target(name, connection.engine.url.port)
            rows = connection.exec_driver_sql(
                "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s",
                (name,),
            ).all()
            if rows and rows[0][0] != TEST_IDENTITY:
                raise DatabaseSafetyError("secondary fixture target is not independently TEST")

    def after(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, parameters, context, executemany
        if statement == f'CREATE DATABASE "{name}"':
            require_test_target(name, connection.engine.url.port)
            connection.exec_driver_sql(f"COMMENT ON DATABASE \"{name}\" IS 'EMPIRICAL:TEST'")

    with pytest.MonkeyPatch.context() as patch:
        if attribute:
            patch.setattr(request.module, attribute, name)
        event.listen(Engine, "before_cursor_execute", before)
        event.listen(Engine, "after_cursor_execute", after)
        try:
            yield
        finally:
            event.remove(Engine, "before_cursor_execute", before)
            event.remove(Engine, "after_cursor_execute", after)
