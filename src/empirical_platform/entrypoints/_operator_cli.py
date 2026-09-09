"""One refusal shape for every M084 operator command.

An operator who mistypes a symbol, or hands a command an inputs file that is
missing a key, should be told what is wrong. Before this module, fourteen of
the fifteen M084 commands answered that with a Python traceback and exit code
1: the message was in there, on the last line, under twenty lines of frames
naming files the operator has never opened. Only
`validate-trading-configuration` printed a clean refusal, so the surface was
also inconsistent -- the same mistake looked like a bug in one command and like
a considered answer in another.

This was found by running the operator walkthrough against an installed wheel,
which is the only place it is visible: every one of these paths is exercised by
unit tests that call the handler directly, and a handler that raises is exactly
what those tests assert. The traceback only exists at the boundary the tests do
not cross.

The rule here is deliberately narrow. Three exception types are operator input
errors and are reported as refusals:

  InputError     a document this command was handed is malformed
  ValueError     a domain invariant refused the request
  NotFoundError  a record this command was asked about does not exist

Everything else is left to propagate with its traceback intact, because
everything else is a defect in this software, and swallowing those would trade
a rough edge for a silent one. A command that fails for a reason the operator
cannot fix should look alarming.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.decision_to_approval_io import InputError

__all__ = ["operator_command"]

#: What counts as "the operator can fix this". Deliberately not `Exception`.
_REFUSALS = (InputError, ValueError, NotFoundError)


def operator_command(body: Callable[[], None]) -> Callable[[], None]:
    """Wrap a command's `main` so operator errors print a refusal, not a trace.

    `SystemExit` passes through untouched: a usage message is already a
    finished answer, and re-wrapping it would print `REFUSED: 2`.
    """

    def main() -> None:
        try:
            body()
        except SystemExit:
            raise
        except _REFUSALS as error:
            print(f"REFUSED: {error}", file=sys.stderr)
            raise SystemExit(1) from error

    return main
