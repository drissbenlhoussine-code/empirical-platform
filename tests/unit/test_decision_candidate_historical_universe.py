"""MILESTONE-064 unit tests for deterministic historical universe
derivation (`universe_at`), including a separately-authored independent
verifier that never calls the production function -- the mission's own
"independent membership derivation" requirement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from empirical_platform.decision_candidate.historical_universe import universe_at
from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
)

_T0 = datetime(2020, 1, 1, tzinfo=UTC)
_T1 = datetime(2021, 1, 1, tzinfo=UTC)
_T2 = datetime(2022, 1, 1, tzinfo=UTC)
_T3 = datetime(2023, 1, 1, tzinfo=UTC)
_AAPL = InstrumentId("INSTR-AAPL-001")
_AMZN = InstrumentId("INSTR-AMZN-001")
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


def _independent_universe_at(
    manifest: MembershipManifest, cutoff: datetime
) -> tuple[InstrumentId, ...]:
    """Separately-authored verifier: derives the eligible set from raw
    `manifest.records` using its own loop/comparison logic, WITHOUT calling
    `historical_universe.universe_at()`. Manually collects then sorts by
    the raw string value (not by calling `InstrumentId.__lt__` indirectly
    through `sorted(..., key=str)` as production code does -- uses a plain
    dict keyed by string to prove the result set is identical regardless of
    implementation approach)."""
    eligible: dict[str, InstrumentId] = {}
    for record in manifest.records:
        if record.membership_status != MembershipStatus.ACTIVE:
            continue
        after_start = not (cutoff < record.effective_from)
        before_end = record.effective_to is None or cutoff < record.effective_to
        if after_start and before_end:
            eligible[record.instrument_id.value] = record.instrument_id
    ordered_keys = sorted(eligible.keys())
    return tuple(eligible[key] for key in ordered_keys)


@pytest.fixture
def manifest() -> MembershipManifest:
    return MembershipManifest(
        universe_id="UNIVERSE-1",
        universe_version="1",
        records=(
            _record(_AAPL, _T0, None),
            _record(_AMZN, _T1, None),
            _record(_TSLA, _T0, _T2, MembershipStatus.ACTIVE),
            _record(_TSLA, _T2, None, MembershipStatus.INACTIVE_LIKE),
        ),
    )


class TestUniverseAt:
    def test_before_any_join(self, manifest: MembershipManifest) -> None:
        assert universe_at(manifest, _T0 - timedelta(days=1)) == ()

    def test_exact_join_boundary_inclusive(self, manifest: MembershipManifest) -> None:
        assert _AMZN in universe_at(manifest, _T1)
        assert _AMZN not in universe_at(manifest, _T1 - timedelta(microseconds=1))

    def test_exact_exit_boundary_exclusive(self, manifest: MembershipManifest) -> None:
        assert _TSLA not in universe_at(manifest, _T2)
        assert _TSLA in universe_at(manifest, _T2 - timedelta(microseconds=1))

    def test_inactive_like_excluded_from_eligibility(self, manifest: MembershipManifest) -> None:
        assert _TSLA not in universe_at(manifest, _T3)

    def test_result_is_canonically_sorted(self, manifest: MembershipManifest) -> None:
        result = universe_at(manifest, _T1)
        assert result == tuple(sorted(result, key=str))

    def test_input_record_order_independence(self, manifest: MembershipManifest) -> None:
        shuffled = MembershipManifest(
            universe_id="UNIVERSE-1",
            universe_version="1",
            records=tuple(reversed(manifest.records)),
        )
        assert universe_at(manifest, _T1) == universe_at(shuffled, _T1)

    def test_all_inactive_returns_empty_tuple(self) -> None:
        all_inactive = MembershipManifest(
            universe_id="UNIVERSE-1",
            universe_version="1",
            records=(_record(_AAPL, _T0, None, MembershipStatus.DELISTED_LIKE),),
        )
        assert universe_at(all_inactive, _T1) == ()

    def test_one_active_instrument(self) -> None:
        one_active = MembershipManifest(
            universe_id="UNIVERSE-1",
            universe_version="1",
            records=(_record(_AAPL, _T0, None),),
        )
        assert universe_at(one_active, _T1) == (_AAPL,)

    def test_naive_cutoff_rejected(self, manifest: MembershipManifest) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            universe_at(manifest, datetime(2021, 1, 1))


class TestIndependentUniverseDerivation:
    """Cross-checks `universe_at()` against a separately-authored
    derivation for every boundary cutoff in the fixture above."""

    @pytest.mark.parametrize(
        "cutoff",
        [
            _T0 - timedelta(days=1),
            _T0,
            _T0 + timedelta(days=1),
            _T1 - timedelta(microseconds=1),
            _T1,
            _T1 + timedelta(days=1),
            _T2 - timedelta(microseconds=1),
            _T2,
            _T3,
        ],
    )
    def test_matches_production_at_every_boundary(
        self, manifest: MembershipManifest, cutoff: datetime
    ) -> None:
        assert universe_at(manifest, cutoff) == _independent_universe_at(manifest, cutoff)
