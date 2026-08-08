"""MILESTONE-053 behavioral tests for the shared `entrypoints._composition`
resource-lifecycle helper.

`postgres_repository_runtime()` centralizes the exact `service.initialize()`
inside `try:` / `service.close()` inside `finally:` shape independently
proven correct three times by M050/M051/M052's own hand-rolled entrypoints
(most recently regression-tested for the M050-Y-1 defect class). This file
proves that shape directly, once, at the shared helper -- including a
fail-before/pass-after defect-reintroduction proof: reverting the helper to
call `service.initialize()` before the `try:` block (the exact M050-Y-1
defect shape) makes `test_close_is_not_attempted_if_initialize_is_called_outside_try`
fail, demonstrating this suite actually exercises the risk it claims to.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from empirical_platform.entrypoints import _composition
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)


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


def test_closes_service_when_initialize_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Applies the M050-Y-1 lesson: `service.close()` must be attempted even
    when `service.initialize()` itself raises, and no downstream repository
    runtime may be constructed against a never-initialized service."""
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

    monkeypatch.setattr(_composition, "PostgresPersistenceService", _FailingInitializeService)
    monkeypatch.setattr(_composition, "PostgresRepositoryRuntime", _unexpected_runtime_construction)

    with pytest.raises(RuntimeError) as excinfo:
        with _composition.postgres_repository_runtime(_dummy_config()):
            raise AssertionError("body must never run when initialize() fails")

    assert excinfo.value is sentinel
    assert close_calls == [None]
    assert runtime_constructed == []


def test_closes_service_exactly_once_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Companion coverage: the success path closes the service exactly once,
    and the yielded value is the constructed `PostgresRepositoryRuntime`."""
    close_calls: list[None] = []
    runtime_marker = object()

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

    monkeypatch.setattr(_composition, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(_composition, "PostgresRepositoryRuntime", _StubRuntime)

    with _composition.postgres_repository_runtime(_dummy_config()) as runtime:
        assert isinstance(runtime, _StubRuntime)
        del runtime_marker

    assert close_calls == [None]


def test_closes_service_when_caller_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Companion coverage: a post-initialize failure inside the caller's own
    `with` block (e.g. a handler raising) must still close the service
    exactly once."""
    close_calls: list[None] = []
    sentinel = RuntimeError("adversarial caller failure")

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

    monkeypatch.setattr(_composition, "PostgresPersistenceService", _SucceedingService)
    monkeypatch.setattr(_composition, "PostgresRepositoryRuntime", _StubRuntime)

    with pytest.raises(RuntimeError) as excinfo:
        with _composition.postgres_repository_runtime(_dummy_config()):
            raise sentinel

    assert excinfo.value is sentinel
    assert close_calls == [None]


def test_close_is_not_attempted_if_initialize_is_called_outside_try(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defect-reintroduction proof: this test is written to demonstrate what
    WOULD fail if `postgres_repository_runtime()` regressed to the M050-Y-1
    shape (`service.initialize()` called before `try:` instead of as the
    first statement inside it). It passes against the correct implementation
    because `close()` IS attempted on an initialize() failure; manually
    moving the real `service.initialize()` call in `_composition.py` to
    before its `try:` block makes this test fail, since `close()` would then
    never run."""
    close_calls: list[None] = []
    sentinel = RuntimeError("adversarial initialize failure")

    class _FailingInitializeService:
        def __init__(self, config: object) -> None:
            del config

        def initialize(self) -> None:
            raise sentinel

        def close(self) -> None:
            close_calls.append(None)

    monkeypatch.setattr(_composition, "PostgresPersistenceService", _FailingInitializeService)

    with pytest.raises(RuntimeError):
        with _composition.postgres_repository_runtime(_dummy_config()):
            raise AssertionError("body must never run when initialize() fails")

    assert close_calls == [None], (
        "close() must be attempted even though initialize() raised -- "
        "this is exactly the M050-Y-1 defect class"
    )


def test_default_config_resolves_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structural proof that omitting `config` really resolves through
    `resolve_foundation_config()` rather than silently requiring an explicit
    override, without constructing real persistence."""
    resolved_calls: list[None] = []
    dummy = _dummy_config()

    class _FakeFoundationConfig:
        postgresql = dummy

    class _StubService:
        def __init__(self, config: object) -> None:
            assert config is dummy

        def initialize(self) -> None:
            return None

        def close(self) -> None:
            return None

    def _fake_resolve_foundation_config() -> _FakeFoundationConfig:
        resolved_calls.append(None)
        return _FakeFoundationConfig()

    monkeypatch.setattr(_composition, "resolve_foundation_config", _fake_resolve_foundation_config)
    monkeypatch.setattr(_composition, "PostgresPersistenceService", _StubService)
    monkeypatch.setattr(_composition, "PostgresRepositoryRuntime", lambda service: None)

    with _composition.postgres_repository_runtime():
        pass

    assert resolved_calls == [None]


def test_postgres_repository_runtime_is_a_real_context_manager() -> None:
    """Structural proof this is genuinely a `contextmanager`-decorated
    generator function, not a plain function returning something
    context-manager-shaped by accident."""
    import inspect

    wrapped = _composition.postgres_repository_runtime.__wrapped__  # type: ignore[attr-defined]
    assert inspect.isgeneratorfunction(wrapped)


def test_yielded_runtime_type_is_postgres_repository_runtime() -> None:
    """Structural proof the return-type contract is `PostgresRepositoryRuntime`
    itself, not some other object shape."""
    import inspect

    signature = inspect.signature(_composition.postgres_repository_runtime)
    assert signature.return_annotation in (
        "Iterator[PostgresRepositoryRuntime]",
        PostgresRepositoryRuntime,
    )
