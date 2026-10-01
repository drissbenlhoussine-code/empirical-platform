"""MILESTONE-095 Phase 4/7 -- the canonical event record and the predeclared event taxonomy.

SCOPE, PER PHASE 1/2's OWN QUALIFICATION (`external-review/MILESTONE-095/
data-source-qualification.md`): the only qualified source is Alpaca's News API
(Benzinga-sourced, symbol-tagged, timestamped general news). It supplies NO structured
earnings-surprise, guidance, or analyst-rating fields at any tier -- so the taxonomy here
is deliberately narrower than the mission's full wish-list: `EVENT_PRESENT` (any
qualifying article) is the primary classification, with a reproducible, headline-keyword
regex (`EARNINGS_KEYWORD_PATTERN`, predeclared below, fixed BEFORE any outcome data is
examined) splitting `EARNINGS_KEYWORD_NEWS` from `OTHER_NEWS`. This is a heuristic over
publication-time text, never a price-derived or outcome-derived label -- it would produce
the identical classification for an article whether the subsequent price move was up,
down, or flat, which is what makes it a legitimate predeclared taxonomy rather than a
retrospective price-action label (the thing Phase 7 explicitly forbids).

PREDECLARED, NOT TUNED. `EARNINGS_KEYWORD_PATTERN` and the single-or-dual-symbol
company-specificity filter (`is_company_specific`) are fixed here, in source control,
before `tools/m095_event_study.py` is ever run against outcome data. Neither is adjusted
after seeing results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

__all__ = [
    "EARNINGS_KEYWORD_PATTERN",
    "MARKET_CLOSE_ET",
    "MARKET_OPEN_ET",
    "EventRecord",
    "EventType",
    "SessionRelation",
    "classify_event_type",
    "classify_session_relation",
    "is_company_specific",
    "normalize_alpaca_articles",
]

_EASTERN = ZoneInfo("America/New_York")

#: Regular session bounds, Eastern time. Used only to classify WHEN an article was
#: published relative to the trading day -- never to decide whether it is usable (that is
#: Phase 5's point-in-time rule, `published_at <= T`, applied separately).
MARKET_OPEN_ET = (9, 30)
MARKET_CLOSE_ET = (16, 0)

#: Predeclared, case-insensitive, word-boundary. Matches earnings-report and
#: guidance-adjacent language only -- never a sentiment word ("surges", "soars", "plunges")
#: that would smuggle in a price-derived judgment. Fixed before any M095 outcome data is
#: examined; never edited after seeing results.
EARNINGS_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"earnings|eps|quarterly results|quarterly report|"
    r"q[1-4]\s+results|q[1-4]\s+earnings|"
    r"beats?\s+(estimates?|consensus|expectations?)|"
    r"misses?\s+(estimates?|consensus|expectations?)|"
    r"(revenue|profit|guidance)\s+(beat|miss)|"
    r"raises?\s+guidance|cuts?\s+guidance|lowers?\s+guidance|"
    r"earnings\s+(call|report|preview|results)"
    r")\b",
    re.IGNORECASE,
)


class SessionRelation(StrEnum):
    PREMARKET = "PREMARKET"
    REGULAR_SESSION = "REGULAR_SESSION"
    AFTER_HOURS = "AFTER_HOURS"
    UNKNOWN = "UNKNOWN"


class EventType(StrEnum):
    EARNINGS_KEYWORD_NEWS = "EARNINGS_KEYWORD_NEWS"
    OTHER_NEWS = "OTHER_NEWS"


def classify_session_relation(published_at_utc: datetime) -> SessionRelation:
    """Classify a UTC publication instant by Eastern time-of-day only.

    Weekend timestamps (a market-closed day) are `UNKNOWN` rather than forced into one of
    the three session buckets -- there is no regular session to be pre/post/during on a
    day the market never opens.
    """
    if published_at_utc.tzinfo is None:
        raise ValueError("published_at_utc must be timezone-aware")
    eastern = published_at_utc.astimezone(_EASTERN)
    if eastern.weekday() >= 5:
        return SessionRelation.UNKNOWN
    minutes = eastern.hour * 60 + eastern.minute
    open_minutes = MARKET_OPEN_ET[0] * 60 + MARKET_OPEN_ET[1]
    close_minutes = MARKET_CLOSE_ET[0] * 60 + MARKET_CLOSE_ET[1]
    if minutes < open_minutes:
        return SessionRelation.PREMARKET
    if minutes >= close_minutes:
        return SessionRelation.AFTER_HOURS
    return SessionRelation.REGULAR_SESSION


def classify_event_type(headline: str) -> EventType:
    if EARNINGS_KEYWORD_PATTERN.search(headline):
        return EventType.EARNINGS_KEYWORD_NEWS
    return EventType.OTHER_NEWS


def is_company_specific(symbols: tuple[str, ...], *, maximum_symbols: int = 2) -> bool:
    """Predeclared company-specificity filter (Source 1's own disclosed noise problem in
    `data-source-qualification.md`): a broad market-wrap article tagging many tickers at
    once should not be attributed to any single company's price action. Fixed at 2 before
    any outcome data is examined."""
    return 0 < len(symbols) <= maximum_symbols


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One company-specific, point-in-time-safe news event.

    `published_at` is ALWAYS the article's `created_at` (first-publication instant) from
    the Alpaca/Benzinga feed, never `updated_at` -- see `data-source-qualification.md`'s
    point-in-time-correctness note: an article's `updated_at` can be later than
    `created_at`, and using it as the usability instant would let a later edit's content
    leak into a decision made before the edit happened.
    """

    event_id: str
    symbol: str
    event_type: EventType
    source: str
    published_at: datetime
    session_relation: SessionRelation
    headline: str
    retrieved_at: datetime
    source_version: str


def normalize_alpaca_articles(
    articles: object,
    *,
    symbol: str,
    retrieved_at: datetime,
    source_version: str = "alpaca-news-v1beta1",
) -> tuple[EventRecord, ...]:
    """Normalize raw `_NewsArticleView` objects (duck-typed: `.article_id`, `.headline`,
    `.source`, `.symbols`, `.created_at`) into canonical, company-specific `EventRecord`s
    for ONE target symbol. Articles failing `is_company_specific` are dropped -- not
    relabeled, not kept with a weaker flag -- per the predeclared filter above."""
    records: list[EventRecord] = []
    for article in articles:  # type: ignore[attr-defined]
        if symbol not in article.symbols:
            continue
        if not is_company_specific(article.symbols):
            continue
        published_at = article.created_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        records.append(
            EventRecord(
                event_id=f"{source_version}:{article.article_id}",
                symbol=symbol,
                event_type=classify_event_type(article.headline),
                source=article.source,
                published_at=published_at,
                session_relation=classify_session_relation(published_at),
                headline=article.headline,
                retrieved_at=retrieved_at,
                source_version=source_version,
            )
        )
    return tuple(records)
