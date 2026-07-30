"""Application service orchestration boundary (MILESTONE-029).

Exposes the two composition-bound invocation entry points that separate
external callers from the frozen `CommandHandler` (MILESTONE-027) and
`QueryHandler` (MILESTONE-028) Protocols. See
`MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md` for the
frozen architecture this package implements.
"""

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.application.query import QueryEntryPoint

__all__ = ["CommandEntryPoint", "QueryEntryPoint"]
