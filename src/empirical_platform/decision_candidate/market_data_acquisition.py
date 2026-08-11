"""Real market-data acquisition domain: a `MarketDataSource` adapter
boundary plus one genuine, network-capable adapter.

MILESTONE-069. Every prior milestone (M057-M068) is genuinely rigorous,
but every one of them has only ever been exercised against synthetic or
hand-authored local fixture files -- confirmed by a fresh repository
search: `historical_import.py`'s own docstring states "No network fetch.
No hidden vendor call." This module closes that gap: it fetches real
historical daily bars from a real, freely-accessible, no-authentication
market-data endpoint and feeds them into the unmodified, frozen M065
`historical_import.import_raw_historical_dataset_snapshot()` pipeline --
so every downstream capability (strategy, ranking, risk, sizing,
backtesting, holdout validation, walk-forward robustness, statistical
uncertainty, portfolio capital accounting, cross-instrument dependence)
becomes usable against genuinely real market data for the first time.

Design boundary: a `MarketDataSource` Protocol separates "how bytes are
obtained" from "how bytes are validated and normalized" -- the frozen
`parse_source_csv`/`import_raw_historical_dataset_snapshot` functions are
reused byte-for-byte, never duplicated or reimplemented. Two adapters are
provided: `FakeMarketDataSource` (deterministic, offline, zero network --
used for every canonical/CI-required test) and
`YahooFinanceChartMarketDataSource` (a real, network-capable adapter over
Yahoo Finance's unofficial `/v8/finance/chart/` JSON endpoint -- the same
widely-used, no-authentication, no-bot-challenge endpoint the
open-source `yfinance` library itself relies on for read-only historical
price data). The real adapter is exercised only in an explicitly opt-in
integration test, gated behind `EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`,
mirroring the established `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS` opt-in
pattern -- canonical CI/build acceptance remains fully offline and
deterministic.

Explicitly out of scope: no live/streaming quotes, no order execution, no
broker connectivity, no API key or credential of any kind, no attempt to
bypass any bot-detection/CAPTCHA challenge (a real attempt against a
different, unrelated vendor endpoint was abandoned specifically because
it returned a JavaScript bot-verification challenge -- see the M069
scope-and-design document for the full record). This module fetches
read-only, publicly-published historical price data only.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.shared.interfaces.clock import WallClock

_PRICE_QUANTUM = Decimal("0.0001")

#: The real adapter's own honest source-name constant -- deliberately
#: includes "UNOFFICIAL" so no downstream consumer of a persisted
#: `DatasetSnapshotAuthority.source_name` can mistake this for a
#: licensed/authoritative vendor relationship.
YAHOO_FINANCE_SOURCE_NAME = "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"
FAKE_SOURCE_NAME = "FAKE_OFFLINE_FIXTURE"

#: The exact CSV column shape the frozen M065 `parse_source_csv` already
#: requires -- every adapter's own vendor-specific format is translated
#: into this shape, never the other way around.
_PIPELINE_CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class MarketDataAcquisitionError(ValueError):
    """Raised when a real or fake adapter cannot honestly produce bars
    for the requested symbol/range -- never silently substituted with
    partial or fabricated data."""


@dataclass(frozen=True, slots=True)
class MarketDataFetchRequest:
    """One immutable request for one instrument's own historical bars
    over an explicit, caller-supplied date range."""

    symbol: str
    start_date: date
    end_date: date
    interval: BarInterval

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be strictly before end_date")


@dataclass(frozen=True, slots=True)
class MarketDataFetchResult:
    """One immutable adapter response: the exact raw bytes as received
    (or synthesized, for the Fake adapter), tagged with the adapter's own
    format identifier so the orchestration layer knows how to translate
    it, plus honest provenance (when it was fetched, and from where)."""

    symbol: str
    source_format: str
    raw_bytes: bytes
    source_reference: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not self.source_format.strip():
            raise ValueError("source_format must be non-empty")
        if not self.raw_bytes:
            raise ValueError(f"empty raw_bytes for symbol {self.symbol!r}")
        if not self.source_reference.strip():
            raise ValueError("source_reference must be non-empty")
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")


class MarketDataSource(Protocol):
    """Persistence-neutral, network-neutral adapter boundary: given one
    fetch request, return one raw response. Implementations decide *how*
    bytes are obtained (network call, in-memory fixture, or otherwise) --
    never *whether* the response is validated, that is the orchestration
    layer's own, single responsibility (mission Phase: one boundary, one
    job)."""

    @property
    def source_name(self) -> str:
        """This adapter's own honest, closed-vocabulary identity."""
        ...

    def fetch(self, request: MarketDataFetchRequest) -> MarketDataFetchResult:
        """Return one instrument's own historical bars for the requested
        range. Raises `MarketDataAcquisitionError` if genuinely
        unavailable -- never returns a fabricated or partial substitute."""
        ...


class FakeMarketDataSource:
    """Deterministic, offline, zero-network test double. Constructed
    with an explicit `{symbol: csv_bytes}` fixture map, already in the
    exact pipeline CSV shape (`timestamp,open,high,low,close,volume`) --
    no translation is required, mirroring the established
    `shared/persistence/fake.py`/`shared/object_storage/fake.py`
    precedent for every other real I/O boundary in this codebase."""

    __slots__ = ("_fixtures", "_clock")

    def __init__(self, fixtures: dict[str, bytes], *, clock: WallClock) -> None:
        self._fixtures = dict(fixtures)
        self._clock = clock

    @property
    def source_name(self) -> str:
        return FAKE_SOURCE_NAME

    def fetch(self, request: MarketDataFetchRequest) -> MarketDataFetchResult:
        raw_bytes = self._fixtures.get(request.symbol)
        if raw_bytes is None:
            raise MarketDataAcquisitionError(
                f"no fixture bars registered for symbol {request.symbol!r}"
            )
        return MarketDataFetchResult(
            symbol=request.symbol,
            source_format="EMPIRICAL_PLATFORM_NORMALIZED_CSV",
            raw_bytes=raw_bytes,
            source_reference=f"fake://offline-fixture/{request.symbol}",
            fetched_at=self._clock.now(),
        )


class YahooFinanceChartMarketDataSource:
    """Real, network-capable adapter over Yahoo Finance's unofficial
    `/v8/finance/chart/` JSON endpoint. No API key, no authentication, no
    bot-detection/CAPTCHA challenge encountered (unlike an alternative
    vendor endpoint that was tried first and abandoned for exactly that
    reason -- see the M069 scope-and-design document). Read-only GET
    request; stdlib `urllib.request` only, no new dependency."""

    __slots__ = ("_base_url", "_clock", "_timeout_seconds")

    def __init__(
        self,
        *,
        clock: WallClock,
        base_url: str = "https://query1.finance.yahoo.com/v8/finance/chart",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    @property
    def source_name(self) -> str:
        return YAHOO_FINANCE_SOURCE_NAME

    def fetch(self, request: MarketDataFetchRequest) -> MarketDataFetchResult:
        if request.interval is not BarInterval.ONE_DAY:
            raise MarketDataAcquisitionError(
                "YahooFinanceChartMarketDataSource only supports BarInterval.ONE_DAY -- "
                "Yahoo's own intraday history is severely range-limited and would silently "
                "produce a materially incomplete series for any real research use"
            )
        period1 = int(
            datetime(
                request.start_date.year,
                request.start_date.month,
                request.start_date.day,
                tzinfo=UTC,
            ).timestamp()
        )
        period2 = int(
            datetime(
                request.end_date.year, request.end_date.month, request.end_date.day, tzinfo=UTC
            ).timestamp()
        )
        url = f"{self._base_url}/{request.symbol}?period1={period1}&period2={period2}&interval=1d"
        http_request = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                http_request, timeout=self._timeout_seconds
            ) as response:
                raw_bytes = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise MarketDataAcquisitionError(
                f"network fetch failed for symbol {request.symbol!r}: {exc}"
            ) from exc
        return MarketDataFetchResult(
            symbol=request.symbol,
            source_format="YAHOO_FINANCE_CHART_JSON",
            raw_bytes=raw_bytes,
            source_reference=url,
            fetched_at=self._clock.now(),
        )


def _quantize_price(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def translate_yahoo_chart_json_to_pipeline_csv(raw_bytes: bytes, *, symbol: str) -> bytes:
    """Pure, independently-testable translation: Yahoo's own chart JSON
    shape (`chart.result[0].timestamp`/`indicators.quote[0].{open,high,
    low,close,volume}`) into the exact CSV bytes the frozen M065
    `parse_source_csv` already expects. A row with any `None` OHLCV field
    (Yahoo emits these for genuinely missing/incomplete sessions) is
    skipped, never fabricated. Bar timestamps are UTC midnight of the
    exchange-local trading date Yahoo itself reports -- an explicit,
    honest choice for end-of-day granularity, never claiming intraday
    precision the source data does not have."""
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise MarketDataAcquisitionError(
            f"Yahoo chart response for {symbol!r} is not valid JSON"
        ) from exc
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        raise MarketDataAcquisitionError(
            f"Yahoo chart API returned an error for {symbol!r}: {chart['error']}"
        )
    results = chart.get("result") or []
    if not results:
        raise MarketDataAcquisitionError(f"Yahoo chart response for {symbol!r} has no result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    opens = quotes.get("open") or []
    highs = quotes.get("high") or []
    lows = quotes.get("low") or []
    closes = quotes.get("close") or []
    volumes = quotes.get("volume") or []
    if not timestamps:
        raise MarketDataAcquisitionError(f"Yahoo chart response for {symbol!r} has zero bars")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(_PIPELINE_CSV_COLUMNS))
    writer.writeheader()
    rows_written = 0
    for i, epoch_seconds in enumerate(timestamps):
        o, h, low, c, v = opens[i], highs[i], lows[i], closes[i], volumes[i]
        if None in (o, h, low, c, v):
            continue
        trading_date = datetime.fromtimestamp(epoch_seconds, tz=UTC).date()
        bar_timestamp = datetime(
            trading_date.year, trading_date.month, trading_date.day, tzinfo=UTC
        )
        writer.writerow(
            {
                "timestamp": bar_timestamp.isoformat(),
                "open": str(_quantize_price(o)),
                "high": str(_quantize_price(h)),
                "low": str(_quantize_price(low)),
                "close": str(_quantize_price(c)),
                "volume": int(v),
            }
        )
        rows_written += 1
    if rows_written == 0:
        raise MarketDataAcquisitionError(
            f"Yahoo chart response for {symbol!r} contained only incomplete/null rows"
        )
    return buffer.getvalue().encode("utf-8")


def translate_fetch_result_to_pipeline_csv(result: MarketDataFetchResult) -> bytes:
    """Dispatch a fetch result's own raw bytes to the translator matching
    its declared `source_format` -- an explicit, closed registry, never a
    silent fallback that could misinterpret an unrecognized vendor
    format as already-normalized."""
    if result.source_format == "EMPIRICAL_PLATFORM_NORMALIZED_CSV":
        return result.raw_bytes
    if result.source_format == "YAHOO_FINANCE_CHART_JSON":
        return translate_yahoo_chart_json_to_pipeline_csv(result.raw_bytes, symbol=result.symbol)
    raise MarketDataAcquisitionError(
        f"no translator registered for source_format {result.source_format!r}"
    )
