"""MILESTONE-082 -- argument handling for the receipt-label-cutoff view CLI.

Pure functions only: no database, no composition root. The cutoff is required
and must carry an offset, because defaulting it or accepting a naive timestamp
would choose an epistemic stance for the caller.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from empirical_platform.entrypoints.get_attested_evidence_report import (
    _USAGE,
    _argument,
    _cutoff,
)


def test_a_missing_flag_yields_no_value() -> None:
    assert _argument(["--json"], "--receipt-label-cutoff") is None


def test_a_present_flag_yields_the_following_argument() -> None:
    args = ["--json", "--receipt-label-cutoff", "2026-08-10T16:00:00+00:00"]
    assert _argument(args, "--receipt-label-cutoff") == "2026-08-10T16:00:00+00:00"


def test_a_trailing_flag_with_no_value_is_refused() -> None:
    with pytest.raises(SystemExit) as exc:
        _argument(["--receipt-label-cutoff"], "--receipt-label-cutoff")
    assert _USAGE in str(exc.value)


def test_the_cutoff_is_required() -> None:
    with pytest.raises(SystemExit) as exc:
        _cutoff(None, "--receipt-label-cutoff")
    assert "is required" in str(exc.value)


def test_a_malformed_timestamp_is_refused() -> None:
    with pytest.raises(SystemExit) as exc:
        _cutoff("not-a-timestamp", "--receipt-label-cutoff")
    assert "not a valid ISO-8601 timestamp" in str(exc.value)


def test_a_naive_timestamp_is_refused() -> None:
    """A naive datetime has no instant, so it cannot select anything."""
    with pytest.raises(SystemExit) as exc:
        _cutoff("2026-08-10T16:00:00", "--receipt-label-cutoff")
    assert "must carry a UTC offset" in str(exc.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-10T16:00:00+00:00", datetime(2026, 8, 10, 16, 0, tzinfo=UTC)),
        (
            "2026-08-10T16:00:00+02:00",
            datetime(2026, 8, 10, 16, 0, tzinfo=timezone(timedelta(hours=2))),
        ),
        ("2026-08-10T16:00:00Z", datetime(2026, 8, 10, 16, 0, tzinfo=UTC)),
    ],
)
def test_an_offset_bearing_timestamp_is_accepted(raw: str, expected: datetime) -> None:
    assert _cutoff(raw, "--receipt-label-cutoff") == expected
