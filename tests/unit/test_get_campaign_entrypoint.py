"""MILESTONE-050 behavioral tests for `entrypoints.get_campaign`'s CLI wrapper.

Proves `main()`'s own argument-count validation and correct delegation to
`run_get_campaign()`, without touching real persistence: `run_get_campaign`
is monkeypatched at the module level with a deterministic stub, mirroring
this project's own established preference for real fakes/stubs over mocks.
Real end-to-end composition (against real PostgreSQL) is proven separately
by this milestone's own integration test.
"""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from empirical_platform.campaign.aggregate import CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.entrypoints import get_campaign as get_campaign_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_campaign import CampaignSnapshot

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


def _snapshot() -> CampaignSnapshot:
    identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )
    return CampaignSnapshot(
        identity=identity,
        scope_statement=CampaignScopeStatement("a real scope statement"),
        state=CampaignLifecycleState.DRAFT,
    )


def test_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-campaign"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-campaign"):
        get_campaign_module.main()


def test_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE, "extra"]
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-campaign"):
        get_campaign_module.main()


def test_main_calls_run_get_campaign_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run_get_campaign(
        *, campaign_governance_id: str, campaign_runtime_id: str
    ) -> CampaignSnapshot:
        calls.append(
            {
                "campaign_governance_id": campaign_governance_id,
                "campaign_runtime_id": campaign_runtime_id,
            }
        )
        return _snapshot()

    monkeypatch.setattr(get_campaign_module, "run_get_campaign", fake_run_get_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    get_campaign_module.main()

    assert calls == [
        {"campaign_governance_id": "CAMP-0001", "campaign_runtime_id": _RUNTIME_ID_VALUE}
    ]


def test_main_prints_exact_snapshot_payload_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(get_campaign_module, "run_get_campaign", lambda **_: _snapshot())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    get_campaign_module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {
        "governance_id": "CAMP-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "scope_statement": "a real scope statement",
        "state": "DRAFT",
    }


def test_main_propagates_run_get_campaign_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_get_campaign(**_: str) -> CampaignSnapshot:
        raise sentinel

    monkeypatch.setattr(get_campaign_module, "run_get_campaign", failing_run_get_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    with pytest.raises(RuntimeError) as excinfo:
        get_campaign_module.main()

    assert excinfo.value is sentinel


def test_snapshot_payload_shape() -> None:
    payload = get_campaign_module._snapshot_payload(_snapshot())
    assert set(payload.keys()) == {"governance_id", "runtime_id", "scope_statement", "state"}
    assert payload["governance_id"] == "CAMP-0001"
    assert payload["runtime_id"] == _RUNTIME_ID_VALUE
    assert payload["scope_statement"] == "a real scope statement"
    assert payload["state"] == "DRAFT"


def test_run_get_campaign_accepts_optional_config_override() -> None:
    """Structural proof that the testability seam (an explicit `config`
    parameter) exists, without constructing real persistence."""
    import inspect

    signature = inspect.signature(get_campaign_module.run_get_campaign)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None


def test_run_get_campaign_closes_service_when_initialize_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for M050-Y-1: `service.close()` must be attempted even
    when `service.initialize()` itself raises, and no downstream composition
    step (repository runtime, handler, entry point) may run against a
    never-initialized service."""
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
        get_campaign_module, "PostgresPersistenceService", _FailingInitializeService
    )
    monkeypatch.setattr(
        get_campaign_module, "PostgresRepositoryRuntime", _unexpected_runtime_construction
    )

    with pytest.raises(RuntimeError) as excinfo:
        get_campaign_module.run_get_campaign(
            campaign_governance_id="CAMP-0001",
            campaign_runtime_id=_RUNTIME_ID_VALUE,
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
    assert runtime_constructed == []


def test_run_get_campaign_closes_service_exactly_once_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion coverage: the success path still closes the service exactly
    once, preserving the pre-fix guarantee for the already-covered case."""
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
        return lambda query: _snapshot()

    monkeypatch.setattr(get_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(get_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(get_campaign_module, "GetCampaignHandler", _stub_handler)
    monkeypatch.setattr(get_campaign_module, "QueryEntryPoint", _stub_entry_point)

    snapshot = get_campaign_module.run_get_campaign(
        campaign_governance_id="CAMP-0001",
        campaign_runtime_id=_RUNTIME_ID_VALUE,
        config=_dummy_config(),
    )

    assert snapshot == _snapshot()
    assert close_calls == [None]


def test_run_get_campaign_closes_service_when_query_handler_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion coverage: a post-initialize failure (e.g. inside the query
    handler) must still close the service exactly once -- the case already
    correctly handled before this correction, kept as an explicit regression
    guard alongside the new initialize()-failure coverage above."""
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

        def _raise(query: object) -> object:
            del query
            raise sentinel

        return _raise

    monkeypatch.setattr(get_campaign_module, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(get_campaign_module, "PostgresRepositoryRuntime", _StubRuntime)
    monkeypatch.setattr(get_campaign_module, "GetCampaignHandler", _stub_handler)
    monkeypatch.setattr(get_campaign_module, "QueryEntryPoint", _failing_entry_point)

    with pytest.raises(RuntimeError) as excinfo:
        get_campaign_module.run_get_campaign(
            campaign_governance_id="CAMP-0001",
            campaign_runtime_id=_RUNTIME_ID_VALUE,
            config=_dummy_config(),
        )

    assert excinfo.value is sentinel
    assert close_calls == [None]
