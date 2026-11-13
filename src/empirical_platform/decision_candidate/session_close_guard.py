"""Refuse an ENTRY whose mandatory liquidation cannot be started before the session closes.

THE DEFECT THIS CLOSES (Audit A, P1-2). The mandatory liquidation is a fixed wall-clock
time of day (policy: entry window 10:00-15:30 ET, liquidate 15:45 ET). Nothing compared it
with the broker's `next_close`. On an early-close day (13:00 ET close, e.g. 2026-11-27 and
2026-12-24, or any unscheduled early close) a 12:30 entry was accepted although the
mandatory-exit deadline (15:43) falls AFTER the close; the plan manager then finds the market
closed, sends nothing, and the position is held overnight against
`overnight_positions_permitted=False`.

THE RULE. The instant by which the system must already have STARTED exiting is
`mandatory_liquidation_at - MANDATORY_EXIT_SAFETY_BUFFER_SECONDS` (the plan manager's
`ApprovedPlan.mandatory_exit_deadline`; the constant is imported, never copied). An entry
is refused unless

    mandatory_exit_deadline  <  next_close - SESSION_CLOSE_ENTRY_BUFFER

STRICTLY before: equality refuses. A missing (`None`) or naive `next_close` refuses (fail
closed). On a regular 16:00 ET close with the 15:45 liquidation the deadline is 15:43 and the
limit is 15:55, so the entry is allowed.

OWNER DECISION, NOT MADE HERE. On a 13:00 ET early-close day with the configured 15:45
liquidation time EVERY entry is refused for that day, because the deadline is after the close
at every possible entry time. Permitting entries on those days requires the Owner to move the
configured liquidation time earlier (before 12:53 ET). No configured threshold is changed by
this module; it can only make entries MORE conservative. Risk-reducing exits never pass
through here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.approved_plan import (
    MANDATORY_EXIT_SAFETY_BUFFER_SECONDS,
)

__all__ = [
    "SESSION_CLOSE_ENTRY_BUFFER_SECONDS",
    "session_close_before_liquidation_refusal",
]

#: Margin kept between the mandatory-exit deadline and the broker's session close: the exit
#: must have been started at least this long before the close, so a late order, a slow broker
#: acknowledgement or a clock disagreement cannot push the exit past the closing bell.
SESSION_CLOSE_ENTRY_BUFFER_SECONDS = 300


def session_close_before_liquidation_refusal(
    *,
    mandatory_liquidation_at: datetime,
    market_next_close: datetime | None,
    operator_timezone: str,
) -> str | None:
    """A refusal sentence, or None when the mandatory exit can start before the close."""
    if market_next_close is None or market_next_close.tzinfo is None:
        return (
            "the broker's market close time is unknown; an entry whose mandatory "
            "liquidation cannot be placed before the close is refused"
        )
    if mandatory_liquidation_at.tzinfo is None:
        return "the mandatory liquidation time is not timezone-aware"
    exit_deadline = mandatory_liquidation_at - timedelta(
        seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS
    )
    limit = market_next_close - timedelta(seconds=SESSION_CLOSE_ENTRY_BUFFER_SECONDS)
    if exit_deadline < limit:
        return None
    zone = ZoneInfo(operator_timezone)
    return (
        f"the market closes at {market_next_close.astimezone(zone):%H:%M} ET, before the "
        f"mandatory liquidation time {mandatory_liquidation_at.astimezone(zone):%H:%M} ET; "
        "no entry today"
    )
