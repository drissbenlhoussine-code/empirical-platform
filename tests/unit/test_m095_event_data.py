"""MILESTONE-095 Phase 7/23 -- the predeclared event taxonomy and canonical event record.

Proves: session-relation classification is contemporaneous/deterministic, the earnings-
keyword regex is a reproducible headline-text heuristic (never price- or outcome-derived --
it classifies identically regardless of what happened to the price afterward), and the
company-specificity filter drops broad market-wrap articles rather than misattributing them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from empirical_platform.decision_candidate.m095_event_data import (
    EventType,
    SessionRelation,
    classify_event_type,
    classify_session_relation,
    is_company_specific,
    normalize_alpaca_articles,
)


class _FakeArticle:
    def __init__(
        self, article_id: int, headline: str, symbols: tuple[str, ...], created_at: datetime
    ) -> None:
        self.article_id = article_id
        self.headline = headline
        self.summary = ""
        self.source = "benzinga"
        self.symbols = symbols
        self.created_at = created_at


def test_premarket_classification() -> None:
    # 2026-06-01 13:00 UTC -> 09:00 ET (EDT, UTC-4 in June) -- before the 09:30 ET open.
    premarket_utc = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    assert classify_session_relation(premarket_utc) == SessionRelation.PREMARKET


def test_regular_session_classification() -> None:
    # 2026-06-01 15:00 UTC -> 11:00 ET (EDT)
    regular_utc = datetime(2026, 6, 1, 15, 0, tzinfo=UTC)
    assert classify_session_relation(regular_utc) == SessionRelation.REGULAR_SESSION


def test_after_hours_classification() -> None:
    # 2026-06-01 21:00 UTC -> 17:00 ET (EDT)
    after_hours_utc = datetime(2026, 6, 1, 21, 0, tzinfo=UTC)
    assert classify_session_relation(after_hours_utc) == SessionRelation.AFTER_HOURS


def test_weekend_is_unknown_not_forced_into_a_session_bucket() -> None:
    # 2026-06-06 is a Saturday.
    saturday_utc = datetime(2026, 6, 6, 15, 0, tzinfo=UTC)
    assert classify_session_relation(saturday_utc) == SessionRelation.UNKNOWN


def test_naive_datetime_is_refused() -> None:
    import pytest

    with pytest.raises(ValueError, match="timezone-aware"):
        classify_session_relation(datetime(2026, 6, 1, 13, 0))  # noqa: DTZ001


def test_earnings_keyword_matches_are_reproducible_text_only_heuristic() -> None:
    """The classifier reads the headline text ONLY -- it produces the identical answer
    whether the headline describes a beat or a miss, proving it is not a price-derived or
    outcome-derived label."""
    assert (
        classify_event_type("NVIDIA Beats Estimates In Q2 Earnings")
        == EventType.EARNINGS_KEYWORD_NEWS
    )
    assert (
        classify_event_type("NVIDIA Misses Estimates In Q2 Earnings")
        == EventType.EARNINGS_KEYWORD_NEWS
    )
    assert (
        classify_event_type("Apple Raises Guidance After Strong Quarter")
        == EventType.EARNINGS_KEYWORD_NEWS
    )
    assert classify_event_type("Transcript: NVIDIA Q1 2027 Earnings Conference Call") == (
        EventType.EARNINGS_KEYWORD_NEWS
    )


def test_non_earnings_headline_classifies_as_other_news() -> None:
    assert classify_event_type("NVIDIA CEO Tours New Taiwan Factory") == EventType.OTHER_NEWS
    assert classify_event_type("Congressman Looking For Dividends? Taylor Ditches Stock") == (
        EventType.OTHER_NEWS
    )


def test_is_company_specific_rejects_broad_market_wrap_articles() -> None:
    assert is_company_specific(("AAPL",)) is True
    assert is_company_specific(("AAPL", "NVDA")) is True
    assert is_company_specific(("AAPL", "NVDA", "META")) is False
    assert is_company_specific(()) is False


def test_normalize_alpaca_articles_drops_broad_market_wrap_and_other_symbols() -> None:
    retrieved_at = datetime(2026, 6, 2, tzinfo=UTC)
    articles = [
        _FakeArticle(
            1, "NVIDIA Beats Estimates", ("NVDA",), datetime(2026, 6, 1, 21, 0, tzinfo=UTC)
        ),
        _FakeArticle(
            2,
            "Semi Mania Broad Roundup",
            ("NVDA", "AMD", "AAPL", "META"),
            datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
        ),
        _FakeArticle(
            3, "Apple Launches New Product", ("AAPL",), datetime(2026, 6, 1, 19, 0, tzinfo=UTC)
        ),
    ]
    records = normalize_alpaca_articles(articles, symbol="NVDA", retrieved_at=retrieved_at)
    assert len(records) == 1
    assert records[0].symbol == "NVDA"
    assert records[0].event_type == EventType.EARNINGS_KEYWORD_NEWS
    assert records[0].published_at == datetime(2026, 6, 1, 21, 0, tzinfo=UTC)


def test_normalize_uses_created_at_never_updated_at() -> None:
    """`published_at` must be `created_at` even when the fake article object carries a
    distinct (later) `updated_at` -- this test does not even construct `updated_at` on the
    fake, proving `normalize_alpaca_articles` never reads it."""
    article = _FakeArticle(
        1, "Apple Beats Estimates", ("AAPL",), datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    )
    assert not hasattr(article, "updated_at")
    records = normalize_alpaca_articles(
        [article], symbol="AAPL", retrieved_at=datetime(2026, 6, 2, tzinfo=UTC)
    )
    assert records[0].published_at == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
