"""MILESTONE-078 CLI. Read-only: no append path is reachable from here."""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.config.settings import resolve_foundation_config
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.audit_research_decision_follow_through import (
    AuditResearchDecisionFollowThroughHandler,
    AuditResearchDecisionFollowThroughQuery,
)
from empirical_platform.usecases.research_decision_follow_through_io import (
    render_follow_through_json,
    render_follow_through_text,
)

_USAGE = (
    "usage: empirical-platform-audit-follow-through [--json] "
    "--as-of <ISO-8601 with offset> <session_governance_id> <session_runtime_id>"
)


def _argument(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        raise SystemExit(_USAGE)
    return args[index + 1]


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    raw_as_of = _argument(args, "--as-of")
    if raw_as_of is None:
        # Deliberately required: the answer depends entirely on the window, and
        # the one obvious default is the window guaranteed to show nothing.
        raise SystemExit(_USAGE)

    skip = {"--json", "--as-of", raw_as_of}
    positional = [a for a in args if a not in skip]
    if len(positional) != 2:
        raise SystemExit(_USAGE)

    try:
        as_of = datetime.fromisoformat(raw_as_of)
    except ValueError as exc:
        raise SystemExit(f"{_USAGE}\n  --as-of is not a valid ISO-8601 timestamp") from exc
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        # Surfaced as a request error, never as a claim about the persisted data.
        raise SystemExit(
            f"{_USAGE}\n  --as-of must carry a UTC offset, e.g. 2026-04-17T16:00:00+00:00"
        )
    identity: DomainIdentity[ResearchSessionId] = DomainIdentity(
        governance_id=ResearchSessionId(positional[0]),
        runtime_id=RuntimeIdentifier(positional[1]),
    )

    config = resolve_foundation_config().postgresql
    with postgres_repository_runtime(config) as runtime:
        handler = AuditResearchDecisionFollowThroughHandler(
            research_session_repository=runtime.research_sessions,
            operator_position_ledger_repository=runtime.operator_position_ledger,
        )
        entry_point = QueryEntryPoint(handler)
        audit = entry_point(AuditResearchDecisionFollowThroughQuery(identity=identity, as_of=as_of))

    if as_json:
        print(json.dumps(render_follow_through_json(audit), sort_keys=True))
    else:
        print(render_follow_through_text(audit), end="")
