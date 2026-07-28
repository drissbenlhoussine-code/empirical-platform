"""Application-layer command handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_CommandT_contra = TypeVar("_CommandT_contra", contravariant=True)
_ResultT_co = TypeVar("_ResultT_co", covariant=True)


class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
    """Structural contract for a single application-layer command handler.

    A handler receives exactly one command instance and returns exactly one
    result. This Protocol makes no assumption about what a command or result
    type is, how a handler is constructed, how it is registered or
    dispatched, or what it does internally -- all of that is explicitly out
    of scope for this milestone.
    """

    def handle(self, command: _CommandT_contra) -> _ResultT_co:
        """Handle one command instance and return its result."""
        ...


if TYPE_CHECKING:

    class _ExampleCommand: ...

    class _ExampleResult: ...

    class _ExampleHandler:
        def handle(self, command: _ExampleCommand) -> _ExampleResult: ...

    _typed_conformance_check: CommandHandler[_ExampleCommand, _ExampleResult] = _ExampleHandler()

    class _NarrowExampleCommand(_ExampleCommand): ...

    class _NarrowExampleResult(_ExampleResult): ...

    class _WiderInputExampleHandler:
        """Accepts the wider _ExampleCommand; must still satisfy a narrower slot
        (proves _CommandT_contra's contravariance)."""

        def handle(self, command: _ExampleCommand) -> _ExampleResult: ...

    _contravariant_input_check: CommandHandler[_NarrowExampleCommand, _ExampleResult] = (
        _WiderInputExampleHandler()
    )

    class _NarrowerOutputExampleHandler:
        """Returns the narrower _NarrowExampleResult; must still satisfy a wider
        result slot (proves _ResultT_co's covariance)."""

        def handle(self, command: _ExampleCommand) -> _NarrowExampleResult: ...

    _covariant_output_check: CommandHandler[_ExampleCommand, _ExampleResult] = (
        _NarrowerOutputExampleHandler()
    )
