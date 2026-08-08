"""MILESTONE-052 behavioral tests for `entrypoints.create_campaign`'s CLI
wrapper and resource-lifecycle shape.

Proves `main()`'s own argument-count validation and correct delegation to
`run_create_campaign()`, without touching real persistence: `run_create_campaign`
is monkeypatched at the module level with a deterministic stub for the
CLI-behavior tests, mirroring this project's own established preference for
real fakes/stubs over mocks. Also proves `run_create_campaign()`'s own
resource-lifecycle shape directly, applying the M050-Y-1 lesson from the
start: `service.close()` must be attempted whether `service.initialize()`
succeeds or fails, and no downstream composition step may run against a
never-initialized service. Real end-to-end composition (against real
PostgreSQL, including a genuine `AggregateAlreadyExists`) is proven
separately by this milestone's own integration test.
"""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from empirical_platform.entrypoints import create_campaign as create_campaign_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


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


def _identity() -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId("CAMP-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def test_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-campaign", "CAMP-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-campaign"):
        create_campaign_module.main()


def test_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-create-campaign", "CAMP-0001", "a scope statement", "extra"],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-campaign"):
        create_campaign_module.main()


def test_main_calls_run_create_campaign_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run_create_campaign(
        *, campaign_governance_id: str, scope_statement: str
    ) -> DomainIdentity[CampaignId]:
        calls.append(
            {"campaign_governance_id": campaign_governance_id, "scope_statement": scope_statement}
        )
        return _identity()

    monkeypatch.setattr(create_campaign_module, "run_create_campaign", fake_run_create_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-campaign", "CAMP-0001", "a scope statement"]
    )

    create_campaign_module.main()

    assert calls == [
        {"campaign_governance_id": "CAMP-0001", "scope_statement": "a scope statement"}
    ]


def test_main_prints_exact_identity_payload_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(create_campaign_module, "run_create_campaign", lambda **_: _identity())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-campaign", "CAMP-0001", "a scope statement"]
    )
    import io
    import sys as sys_module

    captured = io.StringIO()
    monkeypatch.setattr(sys_module, "stdout", captured)

    create_campaign_module.main()

    payload = json.loads(captured.getvalue())
    assert payload == {"governance_id": "CAMP-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_main_propagates_run_create_campaign_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_create_campaign(**_: str) -> DomainIdentity[CampaignId]:
        raise sentinel

    monkeypatch.setattr(create_campaign_module, "run_create_campaign", failing_run_create_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-campaign", "CAMP-0001", "a scope statement"]
    )

    with pytest.raises(RuntimeError) as excinfo:
        create_campaign_module.main()

    assert excinfo.value is sentinel


def test_identity_payload_shape() -> None:
    payload = create_campaign_module._identity_payload(_identity())
    assert payload == {"governance_id": "CAMP-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_run_create_campaign_accepts_optional_config_override() -> None:
    """Structural proof that the testability seam (an explicit `config`
    parameter) exists, without constructing real persistence."""
    import inspect

    signature = inspect.signature(create_campaign_module.run_create_campaign)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None


def test_run_create_campaign_accepts_optional_identifier_generator_override() -> None:
    """Structural proof that the identifier-generator testability seam
    exists, without constructing a real UUID generator."""
    import inspect

    signature = inspect.signature(create_campaign_module.run_create_campaign)
    assert "identifier_generator" in signature.parameters
    assert signature.parameters["identifier_generator"].default is None


def test_run_create_campaign_closes_service_when_initialize_raises(
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
        create_campaign_module, "PostgresPersistenceService", _FailingInitializeService
    )
    monkeypatch.setattr(
        create_campaign_module, "PostgresRepositoryRuntime", _unexpected_runtime_construction
    )

    with pytest.raises(RuntimeError) as excinfo:
        create_campaign_module.run_create_campaign(
            campaign_governance_id="CAMP-0001",
            scope_statement="a scope statement",
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
    assert runtime_constructed == []


def test_run_create_campaign_closes_service_exactly_once_on_success(
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

    def _stub_handler(
        *, campaign_repository: object, runtime_identifier_generator: object
    ) -> object:
        del campaign_repository, runtime_identifier_generator
        return object()

    def _stub_entry_point(handler: object) -> object:
        del handler
        return lambda command: _identity()

    monkeypatch.setattr(create_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(create_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(create_campaign_module, "CreateCampaignHandler", _stub_handler)
    monkeypatch.setattr(create_campaign_module, "CommandEntryPoint", _stub_entry_point)

    identity = create_campaign_module.run_create_campaign(
        campaign_governance_id="CAMP-0001",
        scope_statement="a scope statement",
        config=_dummy_config(),
    )

    assert identity == _identity()
    assert close_calls == [None]


def test_run_create_campaign_closes_service_when_command_handler_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion coverage: a post-initialize failure (e.g. inside the command
    handler, such as a genuine AggregateAlreadyExists) must still close the
    service exactly once."""
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

    def _stub_handler(
        *, campaign_repository: object, runtime_identifier_generator: object
    ) -> object:
        del campaign_repository, runtime_identifier_generator
        return object()

    def _failing_entry_point(handler: object) -> object:
        del handler

        def _raise(command: object) -> object:
            del command
            raise sentinel

        return _raise

    monkeypatch.setattr(create_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(create_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(create_campaign_module, "CreateCampaignHandler", _stub_handler)
    monkeypatch.setattr(create_campaign_module, "CommandEntryPoint", _failing_entry_point)

    with pytest.raises(RuntimeError) as excinfo:
        create_campaign_module.run_create_campaign(
            campaign_governance_id="CAMP-0001",
            scope_statement="a scope statement",
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
