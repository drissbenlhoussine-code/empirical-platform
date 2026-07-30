"""MILESTONE-029 tests proving the composition/transport binding pattern.

Demonstrates that a transport-style caller receives a pre-bound entry
point and supplies only the command or query at invocation time -- it
never selects, constructs, or discovers a handler itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.application import CommandEntryPoint, QueryEntryPoint


@dataclass(frozen=True, slots=True)
class _CreateThingCommand:
    name: str


@dataclass(frozen=True, slots=True)
class _ThingId:
    value: str


class _CreateThingHandler:
    def handle(self, command: _CreateThingCommand) -> _ThingId:
        return _ThingId(value=f"thing-{command.name}")


@dataclass(frozen=True, slots=True)
class _GetThingQuery:
    thing_id: str


@dataclass(frozen=True, slots=True)
class _Thing:
    thing_id: str


class _GetThingHandler:
    def handle(self, query: _GetThingQuery) -> _Thing:
        return _Thing(thing_id=query.thing_id)


def _composition_root() -> tuple[CommandEntryPoint, QueryEntryPoint]:
    """Simulates a composition root: constructs handlers and binds them
    to entry points, exactly once, before any transport call happens."""
    command_entry = CommandEntryPoint(_CreateThingHandler())
    query_entry = QueryEntryPoint(_GetThingHandler())
    return command_entry, query_entry


def _transport_style_command_caller(
    entry_point: CommandEntryPoint[_CreateThingCommand, _ThingId], name: str
) -> _ThingId:
    """Simulates a transport adapter: receives a pre-bound entry point and
    supplies only the command it built from transport input -- it has no
    access to, and does not construct, a handler."""
    return entry_point(_CreateThingCommand(name=name))


def _transport_style_query_caller(
    entry_point: QueryEntryPoint[_GetThingQuery, _Thing], thing_id: str
) -> _Thing:
    return entry_point(_GetThingQuery(thing_id=thing_id))


def test_transport_caller_supplies_only_input_not_a_handler() -> None:
    command_entry, query_entry = _composition_root()

    result = _transport_style_command_caller(command_entry, "widget")

    assert result == _ThingId(value="thing-widget")


def test_query_transport_caller_supplies_only_input_not_a_handler() -> None:
    command_entry, query_entry = _composition_root()

    result = _transport_style_query_caller(query_entry, "abc-123")

    assert result == _Thing(thing_id="abc-123")


def test_entry_points_are_reusable_across_multiple_transport_calls() -> None:
    """One composition-time binding serves many invocations; transport
    never rebinds a handler per call."""
    command_entry, _ = _composition_root()

    first = _transport_style_command_caller(command_entry, "alpha")
    second = _transport_style_command_caller(command_entry, "beta")

    assert first == _ThingId(value="thing-alpha")
    assert second == _ThingId(value="thing-beta")
