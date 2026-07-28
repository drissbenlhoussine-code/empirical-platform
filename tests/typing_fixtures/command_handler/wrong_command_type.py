"""Negative fixture: `handle` accepts an unrelated command type."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Cmd:
    pass


class OtherCmd:
    pass


class Res:
    pass


class TypedHandler:
    def handle(self, command: OtherCmd) -> Res:
        return Res()


handler: CommandHandler[Cmd, Res] = TypedHandler()
