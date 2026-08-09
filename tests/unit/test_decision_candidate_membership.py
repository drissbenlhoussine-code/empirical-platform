"""MILESTONE-064 unit tests for effective-dated universe membership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
    canonical_membership_payload,
    membership_manifest_hash,
)

_T0 = datetime(2020, 1, 1, tzinfo=UTC)
_T1 = datetime(2021, 1, 1, tzinfo=UTC)
_T2 = datetime(2022, 1, 1, tzinfo=UTC)
_AAPL = InstrumentId("INSTR-AAPL-001")
_TSLA = InstrumentId("INSTR-TSLA-001")
_SOURCE = "SURVIVORSHIP_AWARE_MECHANICS_FIXTURE"


def _record(
    instrument_id: InstrumentId,
    effective_from: datetime,
    effective_to: datetime | None,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> MembershipRecord:
    return MembershipRecord(
        universe_id="UNIVERSE-1",
        universe_version="1",
        instrument_id=instrument_id,
        effective_from=effective_from,
        effective_to=effective_to,
        membership_status=status,
        source_kind=_SOURCE,
    )


class TestMembershipRecord:
    def test_open_ended_record_valid(self) -> None:
        record = _record(_AAPL, _T0, None)
        assert record.covers(_T0) is True
        assert record.covers(_T0 - timedelta(days=1)) is False

    def test_effective_to_must_be_after_effective_from(self) -> None:
        with pytest.raises(ValueError, match="strictly after"):
            _record(_AAPL, _T1, _T0)

    def test_effective_to_equal_effective_from_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictly after"):
            _record(_AAPL, _T0, _T0)

    def test_naive_effective_from_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _record(_AAPL, datetime(2020, 1, 1), None)

    def test_covers_exact_from_boundary_inclusive(self) -> None:
        record = _record(_AAPL, _T0, _T1)
        assert record.covers(_T0) is True

    def test_covers_exact_to_boundary_exclusive(self) -> None:
        record = _record(_AAPL, _T0, _T1)
        assert record.covers(_T1) is False
        assert record.covers(_T1 - timedelta(microseconds=1)) is True


class TestMembershipManifest:
    def test_empty_manifest_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1 record"):
            MembershipManifest(universe_id="UNIVERSE-1", universe_version="1", records=())

    def test_duplicate_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate membership record"):
            MembershipManifest(
                universe_id="UNIVERSE-1",
                universe_version="1",
                records=(_record(_AAPL, _T0, _T1), _record(_AAPL, _T0, _T2)),
            )

    def test_overlapping_intervals_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlapping"):
            MembershipManifest(
                universe_id="UNIVERSE-1",
                universe_version="1",
                records=(_record(_AAPL, _T0, _T2), _record(_AAPL, _T1, None)),
            )

    def test_abutting_status_transition_allowed(self) -> None:
        manifest = MembershipManifest(
            universe_id="UNIVERSE-1",
            universe_version="1",
            records=(
                _record(_TSLA, _T0, _T1, MembershipStatus.ACTIVE),
                _record(_TSLA, _T1, None, MembershipStatus.INACTIVE_LIKE),
            ),
        )
        assert len(manifest.records) == 2

    def test_open_ended_followed_by_another_rejected(self) -> None:
        with pytest.raises(ValueError, match="open-ended record followed"):
            MembershipManifest(
                universe_id="UNIVERSE-1",
                universe_version="1",
                records=(_record(_AAPL, _T0, None), _record(_AAPL, _T1, _T2)),
            )

    def test_wrong_universe_id_on_record_rejected(self) -> None:
        mismatched = MembershipRecord(
            universe_id="OTHER-UNIVERSE",
            universe_version="1",
            instrument_id=_AAPL,
            effective_from=_T0,
            effective_to=None,
            membership_status=MembershipStatus.ACTIVE,
            source_kind=_SOURCE,
        )
        with pytest.raises(ValueError, match="universe_id"):
            MembershipManifest(
                universe_id="UNIVERSE-1", universe_version="1", records=(mismatched,)
            )

    def test_validate_against_master_rejects_unknown_instrument(self) -> None:
        manifest = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=(_record(_AAPL, _T0, None),)
        )
        master = InstrumentMaster(
            entries=(InstrumentMasterEntry(_TSLA, Instrument("TSLA"), InstrumentType.EQUITY),)
        )
        with pytest.raises(ValueError, match="unknown instrument"):
            manifest.validate_against_master(master)

    def test_validate_against_master_accepts_known_instrument(self) -> None:
        manifest = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=(_record(_AAPL, _T0, None),)
        )
        master = InstrumentMaster(
            entries=(InstrumentMasterEntry(_AAPL, Instrument("AAPL"), InstrumentType.EQUITY),)
        )
        manifest.validate_against_master(master)  # must not raise


class TestMembershipManifestHash:
    def test_input_order_independence(self) -> None:
        records = (_record(_AAPL, _T0, _T1), _record(_TSLA, _T0, None))
        forward = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=records
        )
        reversed_manifest = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=tuple(reversed(records))
        )
        assert membership_manifest_hash(forward) == membership_manifest_hash(reversed_manifest)

    def test_semantic_change_changes_hash(self) -> None:
        base = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=(_record(_AAPL, _T0, _T1),)
        )
        changed = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=(_record(_AAPL, _T0, _T2),)
        )
        assert membership_manifest_hash(base) != membership_manifest_hash(changed)

    def test_hash_is_64_hex_chars(self) -> None:
        manifest = MembershipManifest(
            universe_id="UNIVERSE-1", universe_version="1", records=(_record(_AAPL, _T0, None),)
        )
        digest = membership_manifest_hash(manifest)
        assert len(digest) == 64
        int(digest, 16)  # must be valid hex

    def test_canonical_payload_sorted_by_instrument_then_effective_from(self) -> None:
        manifest = MembershipManifest(
            universe_id="UNIVERSE-1",
            universe_version="1",
            records=(_record(_TSLA, _T0, None), _record(_AAPL, _T0, None)),
        )
        payload = canonical_membership_payload(manifest)
        assert [entry["instrument_id"] for entry in payload] == [
            "INSTR-AAPL-001",
            "INSTR-TSLA-001",
        ]
