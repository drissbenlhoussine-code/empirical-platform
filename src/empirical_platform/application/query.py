"""Application-layer query invocation boundary (MILESTONE-029)."""

from __future__ import annotations

from empirical_platform.shared.contracts.query import QueryHandler


class QueryEntryPoint[QueryT, QueryResultT]:
    """Application invocation boundary for one query use case.

    Binds exactly one conforming `QueryHandler` at construction time.
    Invocation supplies only the query; the bound handler is called
    exactly once, receives the query instance unchanged, and its result
    or exception propagates to the caller unchanged. Performs no handler
    discovery, no transaction management, no error wrapping, and no
    runtime Protocol introspection.
    """

    __slots__ = ("_handler",)

    def __init__(self, handler: QueryHandler[QueryT, QueryResultT]) -> None:
        self._handler = handler

    def __call__(self, query: QueryT) -> QueryResultT:
        return self._handler.handle(query)
