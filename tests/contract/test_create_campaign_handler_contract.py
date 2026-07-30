"""MILESTONE-030 contract test: `CreateCampaignHandler` conforms to the
frozen MILESTONE-027 `CommandHandler` Protocol.

Structural conformance (no inheritance, no `@runtime_checkable`) is
verified two ways: a mypy-checked typed assignment (the actual proof,
exercised by the strict mypy gate) and a runtime structural-shape check
documenting the same fact for readers who are not running a type checker,
mirroring the `assert_conforms_to_*` documentation pattern already
established in `tests/contract/_fakes.py` for the frozen repository
Protocols.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.command import CommandHandler


class _FakeCampaignRepository:
    def get(self, identity: object) -> object:
        raise AssertionError

    def add(self, aggregate: object) -> object:
        return None

    def save(self, aggregate: object, *, expected_persisted_version: object) -> object:
        raise AssertionError


def _assert_conforms_to_command_handler(
    handler: CommandHandler[CreateCampaignCommand, DomainIdentity[CampaignId]],
) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def test_typed_assignment_proves_protocol_conformance() -> None:
    """Mypy-checked proof: assigning a CreateCampaignHandler instance to a
    CommandHandler[CreateCampaignCommand, DomainIdentity[CampaignId]]-typed
    variable only type-checks if CreateCampaignHandler structurally
    satisfies the frozen Protocol."""
    handler = CreateCampaignHandler(
        campaign_repository=_FakeCampaignRepository(),  # type: ignore[arg-type]
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["12345678-1234-4321-8765-1234567890ab"]
        ),
    )
    _assert_conforms_to_command_handler(handler)
    assert handler is not None


def test_handle_method_has_the_frozen_single_parameter_shape() -> None:
    """Runtime documentation of the same structural fact: `handle` accepts
    exactly one positional parameter beyond `self`, matching the frozen
    `CommandHandler.handle(self, command) -> result` shape."""
    signature = inspect.signature(CreateCampaignHandler.handle)
    parameters = list(signature.parameters)
    assert parameters == ["self", "command"]


def test_no_inheritance_from_any_command_handler_base_class() -> None:
    """CommandHandler is a Protocol; CreateCampaignHandler must satisfy it
    structurally, not through inheritance -- matching M027's own frozen
    design intent (no base class, no marker interface)."""
    assert CreateCampaignHandler.__bases__ == (object,)
