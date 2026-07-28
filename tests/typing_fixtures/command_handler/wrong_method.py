"""Negative fixture: wrong method name (no `handle` method at all)."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Cmd:
    pass


class Res:
    pass


class BadHandler:
    def process(self, command: Cmd) -> Res:
        return Res()


handler: CommandHandler[Cmd, Res] = BadHandler()
