"""MILESTONE-051 behavioral tests for `entrypoints.cancel_campaign`'s CLI
wrapper and resource-lifecycle shape.

Proves `main()`'s own argument-count/parsing validation and correct
delegation to `run_cancel_campaign()`, without touching real persistence:
`run_cancel_campaign` is monkeypatched at the module level with a
deterministic stub for the CLI-behavior tests, mirroring this project's own
established preference for real fakes/stubs over mocks. Also proves
`run_cancel_campaign()`'s own resource-lifecycle shape directly, applying
the M050-Y-1 lesson from the start: `service.close()` must be attempted
whether `service.initialize()` succeeds or fails, and no downstream
composition step may run against a never-initialized service. Real
end-to-end composition (against real PostgreSQL, including a genuine
`OptimisticConcurrencyConflict`) is proven separately by this milestone's
own integration test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from empirical_platform.entrypoints import cancel_campaign as cancel_campaign_module
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveOperation, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT_ISO = "2026-01-01T00:00:00+00:00"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _dummy_config() -> PostgreSQLConfigSnapshot:
    """A structurally valid config for tests that patch `PostgresPersistenceService`
    entirely and never actually connect to a database."""
    return PostgreSQLConfigSnapshot(
        host="unused",
        port=1,
        database="unused",
        user="unused",
        password=SecretStr("unused"),
        pool_size=1,
        max_overflow=0,
        connection_timeout_seconds=1,
        application_name="unit-test-dummy",
    )


def _result() -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))


def test_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-cancel-campaign", "CAMP-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-cancel-campaign"):
        cancel_campaign_module.main()


def test_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-campaign",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "tester",
            _OCCURRED_AT_ISO,
            "reason",
            "corr-1",
            "extra",
        ],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-cancel-campaign"):
        cancel_campaign_module.main()


def test_main_calls_run_cancel_campaign_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_cancel_campaign(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _result()

    monkeypatch.setattr(cancel_campaign_module, "run_cancel_campaign", fake_run_cancel_campaign)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-campaign",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "tester",
            _OCCURRED_AT_ISO,
            "scope abandoned",
            "corr-1",
        ],
    )

    cancel_campaign_module.main()

    assert calls == [
        {
            "campaign_governance_id": "CAMP-0001",
            "campaign_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "actor": "tester",
            "occurred_at": _OCCURRED_AT,
            "reason": "scope abandoned",
            "correlation_id": "corr-1",
        }
    ]


def test_main_defaults_optional_reason_and_correlation_id_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_cancel_campaign(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _result()

    monkeypatch.setattr(cancel_campaign_module, "run_cancel_campaign", fake_run_cancel_campaign)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-campaign",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "tester",
            _OCCURRED_AT_ISO,
        ],
    )

    cancel_campaign_module.main()

    assert calls[0]["reason"] is None
    assert calls[0]["correlation_id"] is None


def test_main_prints_exact_result_payload_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cancel_campaign_module, "run_cancel_campaign", lambda **_: _result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-campaign",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "tester",
            _OCCURRED_AT_ISO,
        ],
    )
    import io
    import sys as sys_module

    captured = io.StringIO()
    monkeypatch.setattr(sys_module, "stdout", captured)

    cancel_campaign_module.main()

    payload = json.loads(captured.getvalue())
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_main_propagates_run_cancel_campaign_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_cancel_campaign(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(cancel_campaign_module, "run_cancel_campaign", failing_run_cancel_campaign)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-campaign",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "tester",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        cancel_campaign_module.main()

    assert excinfo.value is sentinel


def test_result_payload_shape() -> None:
    payload = cancel_campaign_module._result_payload(_result())
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_run_cancel_campaign_accepts_optional_config_override() -> None:
    """Structural proof that the testability seam (an explicit `config`
    parameter) exists, without constructing real persistence."""
    import inspect

    signature = inspect.signature(cancel_campaign_module.run_cancel_campaign)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None


def test_run_cancel_campaign_closes_service_when_initialize_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Applies the M050-Y-1 lesson from the start: `service.close()` must be
    attempted even when `service.initialize()` itself raises, and no
    downstream composition step (repository runtime, handler, entry point)
    may run against a never-initialized service."""
    close_calls: list[None] = []
    runtime_constructed: list[None] = []
    sentinel = RuntimeError("adversarial initialize failure")

    class _FailingInitializeService:
        def __init__(self, config: object) -> None:
            del config

        def initialize(self) -> None:
            raise sentinel

        def close(self) -> None:
            close_calls.append(None)

    def _unexpected_runtime_construction(service: object) -> None:
        del service
        runtime_constructed.append(None)
        raise AssertionError("PostgresRepositoryRuntime must not be constructed")

    monkeypatch.setattr(
        cancel_campaign_module, "PostgresPersistenceService", _FailingInitializeService
    )
    monkeypatch.setattr(
        cancel_campaign_module, "PostgresRepositoryRuntime", _unexpected_runtime_construction
    )

    with pytest.raises(RuntimeError) as excinfo:
        cancel_campaign_module.run_cancel_campaign(
            campaign_governance_id="CAMP-0001",
            campaign_runtime_id=_RUNTIME_ID_VALUE,
            expected_persisted_version=0,
            actor="tester",
            occurred_at=_OCCURRED_AT,
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
    assert runtime_constructed == []


def test_run_cancel_campaign_closes_service_exactly_once_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion coverage: the success path closes the service exactly once."""
    close_calls: list[None] = []

    class _SucceedingService:
        def __init__(self, config: object) -> None:
            del config

        def initialize(self) -> None:
            return None

        def close(self) -> None:
            close_calls.append(None)

    class _StubRuntime:
        def __init__(self, service: object) -> None:
            del service
            self.campaigns = object()

    def _stub_handler(*, campaign_repository: object) -> object:
        del campaign_repository
        return object()

    def _stub_entry_point(handler: object) -> object:
        del handler
        return lambda command: _result()

    monkeypatch.setattr(cancel_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(cancel_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(cancel_campaign_module, "CancelCampaignHandler", _stub_handler)
    monkeypatch.setattr(cancel_campaign_module, "CommandEntryPoint", _stub_entry_point)

    result = cancel_campaign_module.run_cancel_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=_RUNTIME_ID_VALUE,
        expected_persisted_version=0,
        actor="tester",
        occurred_at=_OCCURRED_AT,
        config=_dummy_config(),
    )

    assert result == _result()
    assert close_calls == [None]


def test_run_cancel_campaign_closes_service_when_command_handler_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion coverage: a post-initialize failure (e.g. inside the command
    handler, such as a genuine OptimisticConcurrencyConflict) must still
    close the service exactly once."""
    close_calls: list[None] = []
    sentinel = RuntimeError("adversarial handler failure")

    class _SucceedingService:
        def __init__(self, config: object) -> None:
            del config

        def initialize(self) -> None:
            return None

        def close(self) -> None:
            close_calls.append(None)

    class _StubRuntime:
        def __init__(self, service: object) -> None:
            del service
            self.campaigns = object()

    def _stub_handler(*, campaign_repository: object) -> object:
        del campaign_repository
        return object()

    def _failing_entry_point(handler: object) -> object:
        del handler

        def _raise(command: object) -> object:
            del command
            raise sentinel

        return _raise

    monkeypatch.setattr(cancel_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(cancel_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(cancel_campaign_module, "CancelCampaignHandler", _stub_handler)
    monkeypatch.setattr(cancel_campaign_module, "CommandEntryPoint", _failing_entry_point)

    with pytest.raises(RuntimeError) as excinfo:
        cancel_campaign_module.run_cancel_campaign(
            campaign_governance_id="CAMP-0001",
            campaign_runtime_id=_RUNTIME_ID_VALUE,
            expected_persisted_version=0,
            actor="tester",
            occurred_at=_OCCURRED_AT,
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
