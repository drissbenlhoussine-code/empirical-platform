"""Positive fixture: a single concrete class structurally satisfies both
CommandHandler and QueryHandler simultaneously when its handle method's
parameter/return types align with both Protocols' type arguments. This is
an expected property of Python's structural Protocol typing, not a defect
-- CommandHandler and QueryHandler declare no inheritance, import, or
shared-base relationship with each other; this fixture proves the
structural-typing reality that coexists with that declared separation."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler
from empirical_platform.shared.contracts.query import QueryHandler


class Value:
    pass


class Outcome:
    pass


class DualCapableHandler:
    def handle(self, value: Value) -> Outcome:
        return Outcome()


as_command_handler: CommandHandler[Value, Outcome] = DualCapableHandler()
as_query_handler: QueryHandler[Value, Outcome] = DualCapableHandler()
