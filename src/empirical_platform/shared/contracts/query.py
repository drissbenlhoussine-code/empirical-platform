"""Application-layer query handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_QueryT_contra = TypeVar("_QueryT_contra", contravariant=True)
_QueryResultT_co = TypeVar("_QueryResultT_co", covariant=True)


class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    """Structural contract for a single application-layer query handler.

    A handler receives exactly one query instance and returns exactly one
    result. This Protocol makes no assumption about what a query or result
    type is, how a handler is constructed, how it is registered or
    dispatched, or what it does internally -- all of that is explicitly out
    of scope for this milestone. QueryHandler declares no inheritance,
    import, alias, or shared-base relationship with CommandHandler; Python's
    structural typing may still accept a single concrete class as satisfying
    both Protocols when its method shape and type arguments happen to align
    with both -- this Protocol does not attempt to prevent that.
    """

    def handle(self, query: _QueryT_contra) -> _QueryResultT_co:
        """Handle one query instance and return its result."""
        ...


if TYPE_CHECKING:

    class _ExampleQuery: ...

    class _ExampleQueryResult: ...

    class _ExampleQueryHandler:
        def handle(self, query: _ExampleQuery) -> _ExampleQueryResult: ...

    _typed_conformance_check: QueryHandler[_ExampleQuery, _ExampleQueryResult] = (
        _ExampleQueryHandler()
    )

    class _NarrowExampleQuery(_ExampleQuery): ...

    class _NarrowExampleQueryResult(_ExampleQueryResult): ...

    class _WiderInputExampleQueryHandler:
        """Accepts the wider _ExampleQuery; must still satisfy a narrower slot
        (proves _QueryT_contra's contravariance)."""

        def handle(self, query: _ExampleQuery) -> _ExampleQueryResult: ...

    _contravariant_input_check: QueryHandler[_NarrowExampleQuery, _ExampleQueryResult] = (
        _WiderInputExampleQueryHandler()
    )

    class _NarrowerOutputExampleQueryHandler:
        """Returns the narrower _NarrowExampleQueryResult; must still satisfy
        a wider result slot (proves _QueryResultT_co's covariance)."""

        def handle(self, query: _ExampleQuery) -> _NarrowExampleQueryResult: ...

    _covariant_output_check: QueryHandler[_ExampleQuery, _ExampleQueryResult] = (
        _NarrowerOutputExampleQueryHandler()
    )
