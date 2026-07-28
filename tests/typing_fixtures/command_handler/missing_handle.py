"""Negative fixture: no `handle` method at all."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class Cmd:
    pass


class Res:
    pass


class NoHandleAtAll:
    pass


handler: CommandHandler[Cmd, Res] = NoHandleAtAll()
