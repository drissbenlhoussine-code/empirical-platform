"""Reviewed XHEL equity schedule; unsupported years and uncertain days fail closed.

Source: https://www.nasdaq.com/european-market-activity/trading-hours
Reviewed 2026-10-03. Helsinki has no listed equity half-days in the 2026 table.
18:25–18:30 is the closing auction, never a continuous-entry window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.market_identity import aware

_HOLIDAYS_2026 = frozenset(
    date.fromisoformat(value)
    for value in (
        "2026-01-01",
        "2026-01-06",
        "2026-04-03",
        "2026-04-06",
        "2026-05-01",
        "2026-05-14",
        "2026-06-19",
        "2026-12-24",
        "2026-12-25",
        "2026-12-31",
    )
)
ZONE = ZoneInfo("Europe/Helsinki")


@dataclass(frozen=True, slots=True)
class VenueSession:
    venue: str
    opens_at: datetime
    continuous_close: datetime
    closes_at: datetime
    status: str
    calendar_version: str = "XHEL-NASDAQ-2026-reviewed-20261003"


def helsinki_session(now: datetime) -> VenueSession:
    aware(now)
    local = now.astimezone(ZONE)
    day = local.date()
    opens = datetime.combine(day, time(10), ZONE)
    continuous_close = datetime.combine(day, time(18, 25), ZONE)
    closes = datetime.combine(day, time(18, 30), ZONE)
    if day.year != 2026:
        status = "UNVERIFIED_CALENDAR"
    elif day.weekday() >= 5 or day in _HOLIDAYS_2026:
        status = "CLOSED"
    elif opens <= local < continuous_close:
        status = "OPEN"
    elif continuous_close <= local < closes:
        status = "CLOSING_AUCTION"
    else:
        status = "CLOSED"
    return VenueSession("XHEL", opens, continuous_close, closes, status)


def require_helsinki_open(
    now: datetime, *, broker_liquid_open: datetime | None, broker_liquid_close: datetime | None
) -> VenueSession:
    """Both exchange schedule and resolved contract liquid hours must permit trading."""
    if broker_liquid_open is None or broker_liquid_close is None:
        raise ValueError("broker does not publish a verified liquid session for this date")
    aware(broker_liquid_open)
    aware(broker_liquid_close)
    session = helsinki_session(now)
    if session.status != "OPEN" or not broker_liquid_open <= now < broker_liquid_close:
        raise ValueError("Helsinki continuous session closed or broker hours disagree")
    if broker_liquid_open >= broker_liquid_close:
        raise ValueError("invalid broker liquid-hours interval")
    return session
