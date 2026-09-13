"""MILESTONE-085 paper submission authorization CLI -- the command a human must run.

THE FINGERPRINT IS A REQUIRED ARGUMENT. An operator has to read it off the preview
and type it back. That is what makes authorizing an act about ONE exact order
rather than about whatever the latest preview happens to be, and it is why there
is no `--yes`, no `--force`, no `--all` and no default for it.

What this writes is single-use, expires, is bound to one paper account, and
permits exactly one dispatch of exactly one order. This command sends nothing.

`run_authorize_paper_submission` is split out from `main()` so that argument
handling and output formatting can be unit-tested by monkeypatching this one
function.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.entrypoints._operator_cli import operator_command
from empirical_platform.entrypoints._paper_composition import paper_execution_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.decision_to_approval_io import InputError
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    ExecutionAuthorization,
)
from empirical_platform.usecases.paper_execution_io import (
    render_authorization_json,
    render_authorization_text,
)

_USAGE = (
    "usage: empirical-platform-authorize-paper-submission [--json] <authorization_id> "
    "<preview_id> <request_fingerprint> <authorized_by> <validity_seconds>"
)


def run_authorize_paper_submission(
    *,
    authorization_id: str,
    preview_id: str,
    request_fingerprint: str,
    authorized_by: str,
    validity_seconds: int,
    config: PostgreSQLConfigSnapshot | None = None,
) -> ExecutionAuthorization:
    with paper_execution_runtime(config) as context:
        handler = AuthorizePaperSubmissionHandler(
            previews=context.paper.submission_previews,
            authorizations=context.paper.execution_authorizations,
            events=context.paper.paper_execution_events,
            # Read-only `GET /v2/clock`. This command still sends no order; it
            # now records the broker time basis the permission is bound to.
            broker=context.broker,
            time_source=context.time_source,
        )
        return handler.handle(
            AuthorizePaperSubmissionCommand(
                authorization_id=authorization_id,
                preview_id=preview_id,
                expected_request_fingerprint=request_fingerprint,
                authorized_by=authorized_by,
                authorized_at=datetime.now(UTC),
                validity_seconds=validity_seconds,
            )
        )


def _main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    positional = [argument for argument in args if argument != "--json"]
    if len(positional) != 5:
        raise SystemExit(_USAGE)

    authorization_id, preview_id, fingerprint, actor, validity = positional
    if not validity.isdigit() or int(validity) <= 0:
        raise InputError(f"validity_seconds {validity!r} must be a positive whole number")

    authorization = run_authorize_paper_submission(
        authorization_id=authorization_id,
        preview_id=preview_id,
        request_fingerprint=fingerprint,
        authorized_by=actor,
        validity_seconds=int(validity),
    )
    if as_json:
        print(json.dumps(render_authorization_json(authorization), sort_keys=True))
    else:
        print(render_authorization_text(authorization), end="")


main = operator_command(_main)


if __name__ == "__main__":
    main()
