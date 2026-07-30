"""MILESTONE-030 behavioral tests for `CreateCampaignHandler`.

Proves the frozen persistence flow (design freeze Section 10.F): translate
command data into frozen value types, obtain `runtime_id` from the injected
`RuntimeIdentifierGenerator`, construct the `Campaign` aggregate, call
`CampaignRepository.add()` exactly once, and return the resulting
`DomainIdentity[CampaignId]`. Also proves transparent failure propagation
for every collaborator (frozen M029 invariant) and that the handler is
invocable through the frozen `CommandEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.campaign.aggregate import Campaign
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)

if TYPE_CHECKING:
    from empirical_platform.campaign.repository import CampaignRepository
    from empirical_platform.shared.contracts.command import CommandHandler

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


class _RecordingCampaignRepository:
    """Records every `add()` call; conforms structurally to `CampaignRepository`."""

    def __init__(self) -> None:
        self.add_calls: list[Campaign] = []

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called by CreateCampaignHandler")

    def add(self, aggregate: Campaign) -> SaveResult:
        self.add_calls.append(aggregate)
        return SaveResult(operation=SaveOperation.CREATED, persisted_version=aggregate.version)

    def save(self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called by CreateCampaignHandler")


class _FailingCampaignRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.add_calls = 0

    def get(self, identity: object) -> object:
        raise AssertionError("get() must not be called")

    def add(self, aggregate: Campaign) -> SaveResult:
        self.add_calls += 1
        raise self._exc

    def save(self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion) -> object:
        raise AssertionError("save() must not be called")


class _FailingRuntimeIdentifierGenerator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.generate_calls = 0

    def generate(self) -> object:
        self.generate_calls += 1
        raise self._exc


def _handler(repository: object, generator: object | None = None) -> CreateCampaignHandler:
    return CreateCampaignHandler(
        campaign_repository=repository,  # type: ignore[arg-type]
        runtime_identifier_generator=generator  # type: ignore[arg-type]
        or DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
    )


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that CreateCampaignHandler conforms to
    CommandHandler[CreateCampaignCommand, DomainIdentity[CampaignId]]
    without inheritance (structural typing only)."""
    repository: CampaignRepository = _RecordingCampaignRepository()  # type: ignore[assignment]
    handler: CommandHandler[CreateCampaignCommand, DomainIdentity[CampaignId]] = _handler(
        repository
    )
    assert handler is not None


def test_handler_returns_domain_identity_with_caller_supplied_campaign_id() -> None:
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(
        campaign_governance_id="CAMP-0001", scope_statement="initial scope"
    )

    result = handler.handle(command)

    assert isinstance(result, DomainIdentity)
    assert result.governance_id == CampaignId("CAMP-0001")


def test_runtime_id_is_obtained_from_injected_generator() -> None:
    repository = _RecordingCampaignRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    result = handler.handle(command)

    assert str(result.runtime_id) == _RUNTIME_ID_VALUE


def test_campaign_repository_add_is_called_exactly_once() -> None:
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    handler.handle(command)

    assert len(repository.add_calls) == 1


def test_aggregate_supplied_to_add_has_expected_identity_and_scope_statement() -> None:
    repository = _RecordingCampaignRepository()
    generator = DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE])
    handler = _handler(repository, generator)
    command = CreateCampaignCommand(
        campaign_governance_id="CAMP-0042", scope_statement="q3 pricing validation"
    )

    handler.handle(command)

    persisted = repository.add_calls[0]
    assert persisted.identity.governance_id == CampaignId("CAMP-0042")
    assert str(persisted.identity.runtime_id) == _RUNTIME_ID_VALUE
    assert str(persisted.scope_statement) == "q3 pricing validation"


def test_handler_returns_the_persisted_aggregates_identity() -> None:
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    result = handler.handle(command)

    assert result is repository.add_calls[0].identity


def test_no_repository_pre_read_occurs() -> None:
    """get() raises AssertionError in the fake if called; handler must never call it."""
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    handler.handle(command)  # would raise AssertionError if get() were called


def test_malformed_campaign_governance_id_propagates_unchanged() -> None:
    """CampaignId's own frozen format validation (M020) fires; handler adds no
    validation of its own and does not catch this failure."""
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="not-a-valid-id", scope_statement="x")

    with pytest.raises(ValueError, match="Identifier must match"):
        handler.handle(command)

    assert repository.add_calls == []


def test_empty_scope_statement_propagates_unchanged() -> None:
    """CampaignScopeStatement's own frozen non-empty validation (M020) fires."""
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="   ")

    with pytest.raises(ValueError, match="non-empty"):
        handler.handle(command)

    assert repository.add_calls == []


def test_repository_add_failure_propagates_with_identity_preserved() -> None:
    exc = AggregateAlreadyExists(aggregate_kind="Campaign", identity=object())
    repository = _FailingCampaignRepository(exc)
    handler = _handler(repository)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    with pytest.raises(AggregateAlreadyExists) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert repository.add_calls == 1


def test_runtime_identifier_generator_failure_propagates_unchanged() -> None:
    exc = RuntimeError("identifier generation failed")
    generator = _FailingRuntimeIdentifierGenerator(exc)
    repository = _RecordingCampaignRepository()
    handler = _handler(repository, generator)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(command)

    assert excinfo.value is exc
    assert generator.generate_calls == 1
    assert repository.add_calls == []


def test_handler_is_invocable_through_command_entry_point() -> None:
    repository = _RecordingCampaignRepository()
    handler = _handler(repository)
    entry_point = CommandEntryPoint(handler)
    command = CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="scope")

    result = entry_point(command)

    assert isinstance(result, DomainIdentity)
    assert len(repository.add_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    repository = _RecordingCampaignRepository()
    generator = DeterministicRuntimeIdentifierGenerator(
        [_RUNTIME_ID_VALUE, "87654321-4321-4321-8765-0987654321ba"]
    )
    handler = _handler(repository, generator)
    entry_point = CommandEntryPoint(handler)

    entry_point(CreateCampaignCommand(campaign_governance_id="CAMP-0001", scope_statement="a"))
    entry_point(CreateCampaignCommand(campaign_governance_id="CAMP-0002", scope_statement="b"))

    assert len(repository.add_calls) == 2


def test_command_is_a_plain_unvalidated_data_carrier() -> None:
    """No CreateCampaignCommand-level validation exists; malformed data is
    accepted at construction and rejected only by the frozen value objects
    the handler later constructs."""
    command = CreateCampaignCommand(campaign_governance_id="", scope_statement="")
    assert command.campaign_governance_id == ""
    assert command.scope_statement == ""
