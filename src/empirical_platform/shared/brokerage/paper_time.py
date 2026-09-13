"""M085 operation-local time: bounded uncertainty, not assumed agreement.

WHAT THE PREVIOUS MODEL GOT WRONG. It required the broker's clock reading to
fall inside the local request interval -- `requested_at <= timestamp <=
received_at`. That condition is exactly "zero host/broker offset is still
plausible". It is not a test of whether time is *known well enough to act*; it
is a test of whether the two clocks appear to agree, and it fails whenever the
host wall clock is off by more than the round trip happens to allow. Measured on
a Windows 11 host synchronising against `time.windows.com`, a host offset of
0.086 s was enough to refuse every attempt while the true uncertainty was under
half a second. A safety gate that refuses for a reason the operator cannot
observe, and that a correct implementation need not refuse, is a defect.

WHAT REPLACES IT, DERIVED EXACTLY. Let the request leave at monotonic `m0` and
the response be read at `m1`. The broker sampled its own clock at some instant in
between, and reported that sample as `timestamp`. Write the unknown sampling
instant as `s`, with `m0 <= s <= m1`. At `m1` the broker's clock therefore reads
`timestamp + (m1 - s)`, which is smallest when `s = m1` and largest when `s = m0`:

    broker_clock(m1)  in  [ timestamp , timestamp + (m1 - m0) ]

That is the whole derivation. Its width is the measured round trip. Projecting to
any later monotonic `m` adds `(m - m1)` to both ends, so the width never grows.

WHAT THIS INTERVAL IS, AND THE FOUR THINGS IT IS NOT. It bounds ONE quantity:
the reading of THE BROKER'S OWN CLOCK, expressed on the broker's timeline. It
assumes only that `m0 <= s <= m1` -- that the broker sampled during the exchange
-- and that the local monotonic clock measures elapsed duration. It makes no
assumption about where in the round trip the sample fell and none about the two
legs being equal. It does NOT:

  1. bound this HOST's clock skew. Host and broker time are never differenced
     here, so host error is neither measured nor needed.
  2. bound the BROKER's clock error against true time. If Alpaca's clock is
     itself wrong, every deadline derived from it is wrong by the same amount and
     nothing in this module would notice.
  3. bound the difference between the MARKET-DATA host's clock and the trading
     host's. Quote freshness is evaluated on the broker timeline under the stated
     assumption that `data.alpaca.markets` and `paper-api.alpaca.markets` share a
     time base; that assumption is recorded in `build_submission_preview`, is not
     verified here, and cannot be verified from one observation.
  4. detect a replayed or rewound broker clock from a SINGLE observation. One
     sample is consistent with any clock. `observe_broker_clock` compares each
     observation against the previous one, so the protection exists only where an
     operation observes more than once. THE MEASURED BOUNDARY: the current
     preview and dispatch paths observe the broker clock exactly ONCE per
     operation, so within one operation this check does not fire. It is unit
     tested directly against multiple observations, and it is what a future
     multi-observation flow would rely on -- it is not evidence that a single
     forged timestamp would be caught.

TWO TIMELINES, EACH JUDGED ON ITS OWN. Deadlines are not interchangeable. An
intent expiry and an authorization expiry were written by THIS host's clock; a
market close and a broker timestamp come from the BROKER's. Comparing one
against the other is what forced the two clocks to agree in the first place.
Here each deadline is evaluated on the timeline that produced it, so no
cross-clock agreement is required anywhere.

HOW PERSISTED DEADLINES KEEP THEIR MEANING. `ApprovedOrderIntent.expires_at`,
`mandatory_liquidation_at` and `ExecutionAuthorization.expires_at` are stored as
absolute instants written by this host's `datetime.now(UTC)`. They are compared
against `now()` -- this host's clock -- and never converted onto the broker
timeline, because converting them would require the host/broker offset, which is
exactly the unknown this module refuses to guess. A stored expiry therefore means
precisely what it meant when it was written: an instant on the clock that wrote
it. Validity is never extended: `now()` is an UPPER bound, built from the larger
of the current wall reading and `first_reading + monotonic_elapsed`, so elapsed
work always ages a permission and a stalled or slewed wall clock cannot hold one
open. An operation whose uncertainty straddles an expiry is refused, because the
conservative end of the host interval is the one every deadline is tested against.

ELAPSED TIME IS MONOTONIC, ALWAYS. Both timelines are projected forward with
`time.monotonic`, never by re-reading a wall clock, so a stalled, stepped or
slewed wall clock cannot extend a permission. Backward movement of either the
wall clock or the monotonic clock is refused rather than silently corrected.

WHAT IS STILL REFUSED. Time evidence that is absent, not timezone-aware, not
finite, internally inconsistent (a broker clock that moves backwards between
observations), or too uncertain to decide the question being asked. The last one
is not a new constant: the caller states the tightest margin the answer feeds --
the quote freshness ceiling -- and evidence whose uncertainty is not smaller than
that margin cannot decide it.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

__all__ = [
    "BoundedInstant",
    "PaperTimeReading",
    "PaperTimeSource",
    "PaperTimeUncertainError",
    "PaperTimeWindow",
    "SystemPaperTimeSource",
]


@dataclass(frozen=True, slots=True)
class PaperTimeReading:
    utc: datetime
    monotonic: float


class PaperTimeSource(Protocol):
    def read(self) -> PaperTimeReading: ...


class SystemPaperTimeSource:
    def read(self) -> PaperTimeReading:
        return PaperTimeReading(datetime.now(UTC), time.monotonic())


class PaperTimeUncertainError(ValueError):
    """No order may be sent using this operation's uncertain time."""


@dataclass(frozen=True, slots=True)
class BoundedInstant:
    """A closed interval that provably contains one clock's current reading.

    `earliest` and `latest` are both real candidates for "now" on that clock.
    A check is treated as holding only when it holds at BOTH ends, which is what
    "holds throughout the justified uncertainty interval" means in practice.
    """

    earliest: datetime
    latest: datetime

    def __post_init__(self) -> None:
        if self.latest < self.earliest:
            raise PaperTimeUncertainError("a bounded instant cannot end before it starts")

    @property
    def uncertainty_seconds(self) -> float:
        return (self.latest - self.earliest).total_seconds()

    def definitely_at_or_after(self, moment: datetime) -> bool:
        """True when this instant has certainly reached `moment`."""
        return self.earliest >= moment

    def possibly_at_or_after(self, moment: datetime) -> bool:
        """True when this instant may already have reached `moment`.

        Deadlines use this: a deadline that MIGHT have passed is treated as
        passed, because acting past a deadline is the unsafe direction.
        """
        return self.latest >= moment

    def age_of(self, captured_at: datetime) -> tuple[float, float]:
        """Bounds on the age of something stamped `captured_at`, in seconds.

        Returned smallest-first. The larger value is the one a freshness ceiling
        must be tested against.
        """
        return (
            (self.earliest - captured_at).total_seconds(),
            (self.latest - captured_at).total_seconds(),
        )


def _validated(reading: PaperTimeReading) -> PaperTimeReading:
    if reading.utc.tzinfo is None or reading.utc.utcoffset() is None:
        raise PaperTimeUncertainError("time source must provide aware UTC")
    if not math.isfinite(reading.monotonic):
        raise PaperTimeUncertainError("monotonic time is not finite")
    return reading


class PaperTimeWindow:
    """One operation's view of time, on both timelines that matter to it."""

    __slots__ = ("_source", "_first", "_last", "_broker", "last_safe_at")

    def __init__(self, source: PaperTimeSource) -> None:
        self._source = source
        self._first = _validated(source.read())
        self._last = self._first
        #: (earliest, latest) broker reading at `_broker_anchor`, and that anchor.
        self._broker: tuple[datetime, datetime, float] | None = None
        self.last_safe_at = self._first.utc

    # -- host timeline ----------------------------------------------------

    def now(self) -> datetime:
        """The conservative CURRENT instant on THIS HOST's clock.

        Upper bound by construction: a wall clock that stalls or runs slow
        cannot hold a deadline open, because elapsed monotonic time is applied
        to the first reading and the larger of the two always wins.

        Used only for deadlines this host recorded -- intent expiry, mandatory
        liquidation, authorization expiry -- never for broker-sourced facts.
        """
        current = _validated(self._source.read())
        if current.utc < self._last.utc or current.monotonic < self._last.monotonic:
            raise PaperTimeUncertainError("clock rollback: execution time is uncertain")
        elapsed = current.monotonic - self._first.monotonic
        upper = max(current.utc, self._first.utc + timedelta(seconds=elapsed))
        self._last = current
        self.last_safe_at = max(self.last_safe_at, upper)
        return self.last_safe_at

    @property
    def last_monotonic(self) -> float:
        return self._last.monotonic

    def read_monotonic(self) -> float:
        """Sample the monotonic clock without advancing the host timeline."""
        return _validated(self._source.read()).monotonic

    # -- broker timeline --------------------------------------------------

    def observe_broker_clock(
        self, timestamp: datetime, sent_monotonic: float, received_monotonic: float
    ) -> BoundedInstant:
        """Bound the broker's clock from one round trip. Agreement is NOT required.

        The broker stamped `timestamp` somewhere between the request leaving and
        the response being read. At `received_monotonic` its clock therefore read
        at least `timestamp` (stamped last) and at most `timestamp + round_trip`
        (stamped first). Nothing here assumes the two legs are equal, and nothing
        here compares the broker's reading to this host's wall clock.
        """
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise PaperTimeUncertainError("the broker clock reading is not timezone-aware")
        if not math.isfinite(sent_monotonic) or not math.isfinite(received_monotonic):
            raise PaperTimeUncertainError(
                "the broker round trip was not measured on a finite clock"
            )
        round_trip = received_monotonic - sent_monotonic
        if round_trip < 0:
            raise PaperTimeUncertainError(
                "the broker response was read before the request was sent; time is uncertain"
            )

        earliest = timestamp
        latest = timestamp + timedelta(seconds=round_trip)

        if self._broker is not None:
            previous_earliest, _, previous_anchor = self._broker
            # Project the earlier observation forward to this anchor. A broker
            # clock that has moved BACKWARDS past its own lower bound is replayed
            # or inconsistent evidence, not a slow network.
            elapsed = received_monotonic - previous_anchor
            if latest < previous_earliest + timedelta(seconds=elapsed):
                raise PaperTimeUncertainError(
                    "the broker clock moved backwards between observations; "
                    "time evidence is inconsistent"
                )

        self._broker = (earliest, latest, received_monotonic)
        return BoundedInstant(earliest=earliest, latest=latest)

    def broker_now(self) -> BoundedInstant:
        """The bounded CURRENT instant on the BROKER's clock.

        Projected from the last observation using monotonic elapsed time only,
        so the width never grows beyond the round trip that produced it and the
        host wall clock cannot widen or narrow it.
        """
        if self._broker is None:
            raise PaperTimeUncertainError(
                "the broker clock has not been observed; broker-sourced deadlines "
                "cannot be evaluated"
            )
        earliest, latest, anchor = self._broker
        elapsed = timedelta(seconds=self.read_monotonic() - anchor)
        return BoundedInstant(earliest=earliest + elapsed, latest=latest + elapsed)

    def require_broker_certainty_within(self, margin_seconds: float) -> None:
        """Refuse broker time too uncertain to decide the margin it feeds.

        `margin_seconds` is the tightest margin the answer is used for -- in this
        product, the quote freshness ceiling. This is not a grace period and not
        a tolerance: when the uncertainty is not strictly smaller than the margin,
        the measurement cannot distinguish inside from outside it, so the evidence
        is refused rather than rounded.
        """
        if margin_seconds <= 0:
            raise PaperTimeUncertainError("the certainty margin must be positive")
        uncertainty = self.broker_now().uncertainty_seconds
        if uncertainty >= margin_seconds:
            raise PaperTimeUncertainError(
                f"broker time is uncertain to {uncertainty:.3f}s, which cannot decide "
                f"a {margin_seconds}s margin; no order may be sent on this evidence"
            )
