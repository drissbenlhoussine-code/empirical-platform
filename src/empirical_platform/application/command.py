"""Application-layer command invocation boundary (MILESTONE-029)."""

from __future__ import annotations

from empirical_platform.shared.contracts.command import CommandHandler


class CommandEntryPoint[CommandT, ResultT]:
    """Application invocation boundary for one command use case.

    Binds exactly one conforming `CommandHandler` at construction time.
    Invocation supplies only the command; the bound handler is called
    exactly once, receives the command instance unchanged, and its result
    or exception propagates to the caller unchanged. Performs no handler
    discovery, no transaction management, no error wrapping, and no
    runtime Protocol introspection.
    """

    __slots__ = ("_handler",)

    def __init__(self, handler: CommandHandler[CommandT, ResultT]) -> None:
        self._handler = handler

    def __call__(self, command: CommandT) -> ResultT:
        return self._handler.handle(command)
