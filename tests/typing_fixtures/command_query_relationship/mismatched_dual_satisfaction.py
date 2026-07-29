"""Negative fixture: structural compatibility between CommandHandler and
QueryHandler is conditional on actual type alignment, not universal. A
handler typed for Value must still be correctly rejected when assigned to
a CommandHandler slot declared for an unrelated, mismatched type."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Value:
    pass


class Outcome:
    pass


class UnrelatedValue:
    pass


class DualCapableHandler:
    def handle(self, value: Value) -> Outcome:
        return Outcome()


mismatched: CommandHandler[UnrelatedValue, Outcome] = DualCapableHandler()
