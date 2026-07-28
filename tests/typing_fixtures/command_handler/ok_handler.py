"""Positive fixture: a correctly-shaped handler, proving the mypy
subprocess invocation itself works."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Cmd:
    pass


class Res:
    pass


class GoodHandler:
    def handle(self, command: Cmd) -> Res:
        return Res()


handler: CommandHandler[Cmd, Res] = GoodHandler()
