"""MILESTONE-041 contract test: `SealEvidencePackageHandler` conforms to
the frozen MILESTONE-027 `CommandHandler` Protocol.

Structural conformance (no inheritance, no `@runtime_checkable`) is verified two
ways: a mypy-checked typed assignment (the actual proof, exercised by the strict
mypy gate) and a runtime structural-shape check documenting the same fact for
readers who are not running a type checker, mirroring the identical pattern
already established in
`tests/contract/test_start_evidence_package_collection_handler_contract.py`.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.usecases.seal_evidence_package import (
    SealEvidencePackageCommand,
    SealEvidencePackageHandler,
)

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.command import CommandHandler


class _FakeEvidencePackageRepository:
    def get(self, identity: object) -> object:
        raise AssertionError

    def add(self, aggregate: object) -> object:
        raise AssertionError

    def save(self, aggregate: object, *, expected_persisted_version: object) -> object:
        raise AssertionError


def _assert_conforms_to_command_handler(
    handler: CommandHandler[SealEvidencePackageCommand, SaveResult],
) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def test_typed_assignment_proves_protocol_conformance() -> None:
    """Mypy-checked proof: assigning a SealEvidencePackageHandler instance to a
    CommandHandler[SealEvidencePackageCommand, SaveResult]-typed variable
    only type-checks if the handler structurally satisfies the frozen
    Protocol."""
    handler = SealEvidencePackageHandler(
        evidence_package_repository=_FakeEvidencePackageRepository()  # type: ignore[arg-type]
    )
    _assert_conforms_to_command_handler(handler)
    assert handler is not None


def test_handle_method_has_the_frozen_single_parameter_shape() -> None:
    """Runtime documentation of the same structural fact: `handle` accepts
    exactly one positional parameter beyond `self`, matching the frozen
    `CommandHandler.handle(self, command) -> result` shape."""
    signature = inspect.signature(SealEvidencePackageHandler.handle)
    parameters = list(signature.parameters)
    assert parameters == ["self", "command"]


def test_no_inheritance_from_any_command_handler_base_class() -> None:
    """CommandHandler is a Protocol; SealEvidencePackageHandler must satisfy
    it structurally, not through inheritance -- matching M027's own frozen
    design intent (no base class, no marker interface)."""
    assert SealEvidencePackageHandler.__bases__ == (object,)
