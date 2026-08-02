"""MILESTONE-034 contract test: `GetRunHandler` conforms to the
frozen MILESTONE-028 `QueryHandler` Protocol.

Structural conformance (no inheritance, no `@runtime_checkable`) is
verified two ways: a mypy-checked typed assignment (the actual proof,
exercised by the strict mypy gate) and a runtime structural-shape check
documenting the same fact for readers who are not running a type checker,
mirroring the identical pattern already established in
`tests/contract/test_get_campaign_handler_contract.py` for the M031
read-side handler.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from empirical_platform.usecases.get_run import GetRunHandler, GetRunQuery, RunSnapshot

if TYPE_CHECKING:
    from empirical_platform.shared.contracts.query import QueryHandler


class _FakeRunRepository:
    def get(self, identity: object) -> object:
        raise AssertionError

    def add(self, aggregate: object) -> object:
        raise AssertionError

    def save(self, aggregate: object, *, expected_persisted_version: object) -> object:
        raise AssertionError


def _assert_conforms_to_query_handler(
    handler: QueryHandler[GetRunQuery, RunSnapshot],
) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def test_typed_assignment_proves_protocol_conformance() -> None:
    """Mypy-checked proof: assigning a GetRunHandler instance to a
    QueryHandler[GetRunQuery, RunSnapshot]-typed variable only type-checks
    if GetRunHandler structurally satisfies the frozen Protocol."""
    handler = GetRunHandler(run_repository=_FakeRunRepository())  # type: ignore[arg-type]
    _assert_conforms_to_query_handler(handler)
    assert handler is not None


def test_handle_method_has_the_frozen_single_parameter_shape() -> None:
    """Runtime documentation of the same structural fact: `handle` accepts
    exactly one positional parameter beyond `self`, matching the frozen
    `QueryHandler.handle(self, query) -> result` shape."""
    signature = inspect.signature(GetRunHandler.handle)
    parameters = list(signature.parameters)
    assert parameters == ["self", "query"]


def test_no_inheritance_from_any_query_handler_base_class() -> None:
    """QueryHandler is a Protocol; GetRunHandler must satisfy it
    structurally, not through inheritance -- matching M028's own frozen
    design intent (no base class, no marker interface)."""
    assert GetRunHandler.__bases__ == (object,)
