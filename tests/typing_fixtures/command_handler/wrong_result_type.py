"""Negative fixture: `handle` returns an unrelated result type."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Cmd:
    pass


class Res:
    pass


class OtherRes:
    pass


class WrongResultHandler:
    def handle(self, command: Cmd) -> OtherRes:
        return OtherRes()


handler: CommandHandler[Cmd, Res] = WrongResultHandler()
