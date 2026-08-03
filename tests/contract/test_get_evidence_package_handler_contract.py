"""MILESTONE-037 contract test: `GetEvidencePackageHandler` conforms to the
frozen MILESTONE-028 `QueryHandler` Protocol.

Structural conformance (no inheritance, no `@runtime_checkable`) is
verified two ways: a mypy-checked typed assignment (the actual proof,
exercised by the strict mypy gate) and a runtime structural-shape check
documenting the same fact for readers who are not running a type checker,
mirroring the identical pattern already established in
`tests/contract/test_get_run_handler_contract.py` for the M034 read-side
handler.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from empirical_platform.usecases.get_evidence_package import (
    EvidencePackageSnapshot,
    GetEvidencePackageHandler,
    GetEvidencePackageQuery,
)

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.query import QueryHandler


class _FakeEvidencePackageRepository:
    def get(self, identity: object) -> object:
        raise AssertionError

    def add(self, aggregate: object) -> object:
        raise AssertionError

    def save(self, aggregate: object, *, expected_persisted_version: object) -> object:
        raise AssertionError


def _assert_conforms_to_query_handler(
    handler: QueryHandler[GetEvidencePackageQuery, EvidencePackageSnapshot],
) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def test_typed_assignment_proves_protocol_conformance() -> None:
    """Mypy-checked proof: assigning a GetEvidencePackageHandler instance to
    a QueryHandler[GetEvidencePackageQuery, EvidencePackageSnapshot]-typed
    variable only type-checks if GetEvidencePackageHandler structurally
    satisfies the frozen Protocol."""
    handler = GetEvidencePackageHandler(
        evidence_package_repository=_FakeEvidencePackageRepository()  # type: ignore[arg-type]
    )
    _assert_conforms_to_query_handler(handler)
    assert handler is not None


def test_handle_method_has_the_frozen_single_parameter_shape() -> None:
    """Runtime documentation of the same structural fact: `handle` accepts
    exactly one positional parameter beyond `self`, matching the frozen
    `QueryHandler.handle(self, query) -> result` shape."""
    signature = inspect.signature(GetEvidencePackageHandler.handle)
    parameters = list(signature.parameters)
    assert parameters == ["self", "query"]


def test_no_inheritance_from_any_query_handler_base_class() -> None:
    """QueryHandler is a Protocol; GetEvidencePackageHandler must satisfy it
    structurally, not through inheritance -- matching M028's own frozen
    design intent (no base class, no marker interface)."""
    assert GetEvidencePackageHandler.__bases__ == (object,)
