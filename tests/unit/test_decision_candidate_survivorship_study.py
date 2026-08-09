"""MILESTONE-064 unit tests for survivorship-aware historical robustness
studies: the real committed fixture's canonical study, the future-membership
firewall, window-order independence, the CURRENT_UNIVERSE_BIAS_STRESS
diagnostic, and degenerate (zero-eligible-instrument) window handling.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalBacktestRun,
    HistoricalInstrumentSeries,
    dataset_sha256,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
)
from empirical_platform.decision_candidate.position_plan import PositionSizingContext
from empirical_platform.decision_candidate.robustness_study import (
    HistoricalRobustnessStudy,
    RobustnessDatasetBundle,
    RobustnessDatasetBundleAuthority,
    RobustnessUniverseAuthority,
    RobustnessWindowSpec,
)
from empirical_platform.decision_candidate.survivorship_study import (
    BiasStressComparison,
    SurvivorshipAwareRobustnessStudy,
    SurvivorshipClassification,
    build_survivorship_aware_robustness_study,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    DatasetId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "m064_survivorship_aware"
_DATASET_BUNDLE_PATH = _FIXTURE_DIR / "survivorship_aware_dataset_bundle.json"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MEMBERSHIP_MANIFEST_PATH = _FIXTURE_DIR / "membership_manifest.json"
_EXPECTED_DATASET_SHA256 = "af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff"
_EXPECTED_MANIFEST_HASH = "caa9fa899ea26816101a0a494c4977fed75849d4ac19b65ac6410e561f232fda"

_LoadedFixture = tuple[RobustnessDatasetBundle, InstrumentMaster, MembershipManifest]


@pytest.fixture(scope="module")
def loaded_fixture() -> tuple[RobustnessDatasetBundle, InstrumentMaster, MembershipManifest]:
    from empirical_platform.usecases.survivorship_study_io import (
        parse_instrument_master_file,
        parse_membership_manifest_file,
        parse_survivorship_dataset_bundle_file,
    )

    bundle = parse_survivorship_dataset_bundle_file(
        str(_DATASET_BUNDLE_PATH), expected_sha256=_EXPECTED_DATASET_SHA256
    )
    master = parse_instrument_master_file(str(_INSTRUMENT_MASTER_PATH))
    manifest = parse_membership_manifest_file(
        str(_MEMBERSHIP_MANIFEST_PATH), expected_hash=_EXPECTED_MANIFEST_HASH
    )
    return bundle, master, manifest


def _gen() -> DeterministicRuntimeIdentifierGenerator:
    return DeterministicRuntimeIdentifierGenerator(
        [f"{i:08d}-0000-4000-8000-000000000001" for i in range(94000001, 94002000)]
    )


def _backtest_id_for(base: int) -> Callable[[str], DomainIdentity[BacktestRunId]]:
    def _identity(window_id: str) -> DomainIdentity[BacktestRunId]:
        sequence_index = int(window_id[1:]) - 1
        return DomainIdentity(
            governance_id=BacktestRunId(f"BTRUN-{base + sequence_index + 1:04d}"),
            runtime_id=UuidRuntimeIdentifierGenerator().generate(),
        )

    return _identity


def _build(
    bundle: RobustnessDatasetBundle,
    master: InstrumentMaster,
    manifest: MembershipManifest,
    *,
    study_number: int = 9001,
    stress_number: int = 9002,
) -> tuple[
    SurvivorshipAwareRobustnessStudy,
    tuple[HistoricalBacktestRun, ...],
    HistoricalRobustnessStudy,
    tuple[HistoricalBacktestRun, ...],
]:
    generator = _gen()
    return build_survivorship_aware_robustness_study(
        identity=DomainIdentity(
            governance_id=SurvivorshipStudyId(f"SURV-{study_number}"),
            runtime_id=generator.generate(),
        ),
        stress_study_identity=DomainIdentity(
            governance_id=RobustnessStudyId(f"ROBUST-{stress_number}"),
            runtime_id=generator.generate(),
        ),
        bundle=bundle,
        instrument_master=master,
        membership_manifest=manifest,
        sizing_context=PositionSizingContext(
            account_equity=Decimal("100000"), risk_percent=Decimal("0.01")
        ),
        runtime_identifier_generator=generator,
        backtest_run_identity_for=_backtest_id_for(8000),
        stress_backtest_run_identity_for=_backtest_id_for(8500),
    )


class TestCanonicalFixtureStudy:
    def test_classification_and_window_count(self, loaded_fixture: _LoadedFixture) -> None:
        bundle, master, manifest = loaded_fixture
        study, canonical_runs, stress_study, stress_runs = _build(bundle, master, manifest)
        assert study.window_count == 10
        assert (
            study.classification
            == SurvivorshipClassification.SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN
        )
        assert len(canonical_runs) == 10
        assert len(stress_runs) == 10
        assert stress_study.window_count == 10

    def test_eligible_counts_match_designed_membership_timeline(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        expected = [4, 5, 6, 6, 5, 4, 4, 3, 3, 3]
        actual = [result.snapshot.eligible_count for result in study.window_results]
        assert actual == expected

    def test_amzn_later_entrant_not_eligible_before_join(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        amzn = InstrumentId("INSTR-AMZN-001")
        w01, w02, w03 = study.window_results[0], study.window_results[1], study.window_results[2]
        assert amzn not in w01.snapshot.eligible_instrument_ids
        assert amzn not in w02.snapshot.eligible_instrument_ids
        assert amzn in w03.snapshot.eligible_instrument_ids

    def test_tsla_inactive_like_excluded_but_no_bar_deletion(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        tsla = InstrumentId("INSTR-TSLA-001")
        w04, w05 = study.window_results[3], study.window_results[4]
        assert tsla in w04.snapshot.eligible_instrument_ids
        assert tsla not in w05.snapshot.eligible_instrument_ids
        tsla_symbol = master.entry_for(tsla).canonical_symbol
        assert any(str(series.instrument) == str(tsla_symbol) for series in bundle.series)

    def test_excluding_best_window_sensitivity_math(self, loaded_fixture: _LoadedFixture) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        expected = study.all_window_net_pnl_total - study.best_window_by_net_pnl.value
        assert study.excluding_best_window_net_pnl_total == expected

    def test_concentration_none_safe_when_computable(self, loaded_fixture: _LoadedFixture) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        if study.positive_net_pnl_window_count > 0:
            assert study.largest_positive_window_share_of_positive_pnl is not None
        if study.negative_net_pnl_window_count > 0:
            assert study.largest_negative_window_share_of_absolute_negative_pnl is not None


class TestCurrentUniverseBiasStress:
    def test_stress_forces_full_universe_every_window(self, loaded_fixture: _LoadedFixture) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        full_size = len(bundle.universe_authority.constituents)
        assert study.current_universe_bias_stress.full_universe_size == full_size
        for comparison in study.stress_window_comparisons():
            assert comparison.stress_eligible_count == full_size
            assert comparison.stress_evaluated_count == full_size

    def test_stress_and_canonical_genuinely_differ_on_this_fixture(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        assert (
            study.current_universe_bias_stress.comparison
            == BiasStressComparison.CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS
        )
        assert (
            study.current_universe_bias_stress.canonical_total_executed_trade_count
            != study.current_universe_bias_stress.stress_total_executed_trade_count
        )

    def test_stress_study_is_frozen_m063_type_reused_unmodified(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        from empirical_platform.decision_candidate.robustness_study import (
            HistoricalRobustnessStudy,
            RobustnessStudyClassification,
        )

        bundle, master, manifest = loaded_fixture
        study, _, stress_study, _ = _build(bundle, master, manifest)
        assert isinstance(stress_study, HistoricalRobustnessStudy)
        assert isinstance(stress_study.classification, RobustnessStudyClassification)
        assert stress_study.dataset_bundle_id == study.dataset_bundle_id
        assert stress_study.dataset_bundle_sha256 == study.dataset_bundle_sha256
        # stress evaluates the bundle's own full declared universe, always:
        assert len(stress_study.instrument_universe) == len(bundle.universe_authority.constituents)

    def test_no_forbidden_overclaim_vocabulary_anywhere(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study, *_ = _build(bundle, master, manifest)
        forbidden = (
            "SURVIVORSHIP_BIAS_ELIMINATED",
            "MARKET_REPRESENTATIVE",
            "REAL_HISTORICAL_UNIVERSE",
            "PROFITABLE",
            "PROVEN_EDGE",
            "LIVE_READY",
        )
        haystacks = [
            study.classification.value,
            study.current_universe_bias_stress.comparison.value,
            study.corporate_action_handling,
        ]
        for term in forbidden:
            for haystack in haystacks:
                assert term not in haystack


class TestWindowOrderIndependence:
    def test_shuffled_window_spec_declaration_order_same_result(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        shuffled_bundle = RobustnessDatasetBundle(
            authority=bundle.authority,
            universe_authority=bundle.universe_authority,
            window_specs=tuple(reversed(bundle.window_specs)),
            series=bundle.series,
        )
        study_a, *_ = _build(bundle, master, manifest, study_number=9101, stress_number=9102)
        study_b, *_ = _build(
            shuffled_bundle, master, manifest, study_number=9101, stress_number=9102
        )
        assert study_a.window_count == study_b.window_count
        assert [r.snapshot.window_id for r in study_a.window_results] == [
            r.snapshot.window_id for r in study_b.window_results
        ]
        assert study_a.all_window_net_pnl_total == study_b.all_window_net_pnl_total
        assert study_a.classification == study_b.classification


def _tiny_bundle_and_master() -> tuple[RobustnessDatasetBundle, InstrumentMaster]:
    """A minimal 1-instrument, 2-window synthetic bundle used only for the
    future-membership firewall and zero-eligible-window tests below --
    small and fast, independent of the large canonical fixture."""
    start = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    bars = []
    price = Decimal("100.00")
    for minute in range(32):
        if minute % 4 == 0:
            price += Decimal("2.00")
        bars.append(
            Bar(
                instrument=Instrument("AAPL"),
                interval=BarInterval.ONE_MINUTE,
                timestamp=start + timedelta(minutes=minute),
                open=price,
                high=price + Decimal("0.50"),
                low=price - Decimal("0.50"),
                close=price,
                volume=1000 + minute,
            )
        )
    series = (HistoricalInstrumentSeries(instrument=Instrument("AAPL"), bars=tuple(bars)),)
    fingerprint = "|".join(f"AAPL:{bar.timestamp.isoformat()}:{bar.close}" for bar in bars).encode(
        "utf-8"
    )
    authority = RobustnessDatasetBundleAuthority(
        dataset_bundle_id=DatasetId("DATASET-9401"),
        dataset_bundle_version="1",
        source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        sha256=dataset_sha256(fingerprint),
        interval=BarInterval.ONE_MINUTE,
        instrument_count=1,
        total_bars_per_instrument=32,
    )
    universe_authority = RobustnessUniverseAuthority(
        universe_id="UNIVERSE-9401",
        universe_version="1",
        membership_model="HISTORICAL_MEMBERSHIP",
        constituents=(Instrument("AAPL"),),
    )
    window_specs = (
        RobustnessWindowSpec(
            window_id="W01",
            sequence_index=0,
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        ),
        RobustnessWindowSpec(
            window_id="W02",
            sequence_index=1,
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        ),
    )
    bundle = RobustnessDatasetBundle(
        authority=authority,
        universe_authority=universe_authority,
        window_specs=window_specs,
        series=series,
    )
    master = InstrumentMaster(
        entries=(
            InstrumentMasterEntry(
                InstrumentId("INSTR-AAPL-001"), Instrument("AAPL"), InstrumentType.EQUITY
            ),
        )
    )
    return bundle, master


class TestFutureMembershipFirewall:
    def test_future_only_membership_edit_does_not_change_earlier_window(self) -> None:
        bundle, master = _tiny_bundle_and_master()
        # W01 scoring_start = minute 5; W02 scoring_start = minute 21.
        w2_cutoff = datetime(2024, 1, 1, 9, 21, tzinfo=UTC)
        base_manifest = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        # A future-only variant: AAPL becomes INACTIVE_LIKE starting exactly
        # at W02's own cutoff -- a change that belongs entirely to the
        # LATER window.
        mutated_manifest = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=w2_cutoff,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=w2_cutoff,
                    effective_to=None,
                    membership_status=MembershipStatus.INACTIVE_LIKE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        study_a, *_ = _build(bundle, master, base_manifest, study_number=9501, stress_number=9502)
        study_b, *_ = _build(
            bundle, master, mutated_manifest, study_number=9501, stress_number=9502
        )
        w1_a, w1_b = study_a.window_results[0], study_b.window_results[0]
        assert w1_a.snapshot.eligible_instrument_ids == w1_b.snapshot.eligible_instrument_ids
        assert w1_a.executed_trade_count == w1_b.executed_trade_count
        assert w1_a.net_pnl == w1_b.net_pnl
        assert w1_a.total_r == w1_b.total_r
        # The later window DOES change (proving the mutation had an effect
        # at all -- this is not a vacuous "nothing ever changes" test).
        w2_a, w2_b = study_a.window_results[1], study_b.window_results[1]
        assert w2_a.snapshot.eligible_count == 1
        assert w2_b.snapshot.eligible_count == 0

    def test_zero_eligible_window_recorded_not_dropped(self) -> None:
        bundle, master = _tiny_bundle_and_master()
        all_inactive_manifest = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=datetime(2024, 1, 1, 9, 10, tzinfo=UTC),
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        study, canonical_runs, _, _ = _build(
            bundle, master, all_inactive_manifest, study_number=9601, stress_number=9602
        )
        assert study.window_count == 2
        w2 = study.window_results[1]
        assert w2.snapshot.eligible_count == 0
        assert w2.executed_trade_count == 0
        assert w2.backtest_run_id is None
        assert w2.backtest_run_runtime_id is None
        assert w2.net_pnl == Decimal("0")
        assert w2.win_rate is None
        # W01 still had 1 eligible instrument and produced a real run.
        assert len(canonical_runs) == 1

    def test_retroactive_removal_of_a_future_record_does_not_change_earlier_windows(self) -> None:
        bundle, master = _tiny_bundle_and_master()
        w2_cutoff = datetime(2024, 1, 1, 9, 21, tzinfo=UTC)
        with_future_exit = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=w2_cutoff,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        without_future_exit = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        study_a, *_ = _build(
            bundle, master, with_future_exit, study_number=9701, stress_number=9702
        )
        study_b, *_ = _build(
            bundle, master, without_future_exit, study_number=9701, stress_number=9702
        )
        w1_a, w1_b = study_a.window_results[0], study_b.window_results[0]
        assert w1_a.snapshot.eligible_instrument_ids == w1_b.snapshot.eligible_instrument_ids
        assert w1_a.net_pnl == w1_b.net_pnl
        assert w1_a.executed_trade_count == w1_b.executed_trade_count
        # The later window differs (removing the future exit restored eligibility there).
        assert study_a.window_results[1].snapshot.eligible_count == 0
        assert study_b.window_results[1].snapshot.eligible_count == 1


class TestMissingDataExclusion:
    def test_eligible_instrument_without_bar_data_is_excluded_not_evaluated(self) -> None:
        bundle, master = _tiny_bundle_and_master()
        wider_master = InstrumentMaster(
            entries=(
                *master.entries,
                InstrumentMasterEntry(
                    InstrumentId("INSTR-MSFT-001"), Instrument("MSFT"), InstrumentType.EQUITY
                ),
            )
        )
        manifest = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
                # MSFT is eligible per membership but has NO bars in this
                # dataset bundle at all -- must be excluded, not evaluated,
                # and recorded in missing_data_excluded_instrument_ids.
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-MSFT-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        study, *_ = _build(bundle, wider_master, manifest, study_number=9801, stress_number=9802)
        w1 = study.window_results[0]
        msft = InstrumentId("INSTR-MSFT-001")
        assert msft in w1.snapshot.eligible_instrument_ids
        assert msft in w1.snapshot.missing_data_excluded_instrument_ids
        assert msft not in w1.snapshot.evaluated_instrument_ids


class TestDeterministicReplay:
    def test_same_inputs_produce_semantically_identical_results(
        self, loaded_fixture: _LoadedFixture
    ) -> None:
        bundle, master, manifest = loaded_fixture
        study_a, *_ = _build(bundle, master, manifest, study_number=9901, stress_number=9902)
        study_b, *_ = _build(bundle, master, manifest, study_number=9901, stress_number=9902)
        assert study_a.classification == study_b.classification
        assert study_a.all_window_net_pnl_total == study_b.all_window_net_pnl_total
        assert study_a.all_window_total_r_total == study_b.all_window_total_r_total
        assert [r.snapshot.eligible_count for r in study_a.window_results] == [
            r.snapshot.eligible_count for r in study_b.window_results
        ]
        assert [r.executed_trade_count for r in study_a.window_results] == [
            r.executed_trade_count for r in study_b.window_results
        ]
        assert (
            study_a.current_universe_bias_stress.comparison
            == study_b.current_universe_bias_stress.comparison
        )


class TestMultipleUniversesCoexist:
    def test_two_distinct_universe_versions_both_construct_independently(self) -> None:
        bundle_v1, master = _tiny_bundle_and_master()
        manifest_v1 = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        manifest_v2 = MembershipManifest(
            universe_id="UNIVERSE-9401",
            universe_version="2",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-9401",
                    universe_version="2",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        study_v1, *_ = _build(bundle_v1, master, manifest_v1, study_number=9911, stress_number=9912)
        assert study_v1.universe_version == "1"
        # A second, distinct universe_version can be constructed
        # independently against the same bundle (a different
        # RobustnessUniverseAuthority.universe_version), proving no
        # singleton/global universe state anywhere in this module.
        from empirical_platform.decision_candidate.robustness_study import (
            RobustnessDatasetBundle as _Bundle,
        )
        from empirical_platform.decision_candidate.robustness_study import (
            RobustnessUniverseAuthority,
        )

        bundle_v2 = _Bundle(
            authority=bundle_v1.authority,
            universe_authority=RobustnessUniverseAuthority(
                universe_id="UNIVERSE-9401",
                universe_version="2",
                membership_model="HISTORICAL_MEMBERSHIP",
                constituents=bundle_v1.universe_authority.constituents,
            ),
            window_specs=bundle_v1.window_specs,
            series=bundle_v1.series,
        )
        study_v2, *_ = _build(bundle_v2, master, manifest_v2, study_number=9921, stress_number=9922)
        assert study_v2.universe_version == "2"
        assert study_v1.universe_version != study_v2.universe_version


class TestDatasetMembershipUniverseMismatch:
    def test_mismatched_universe_id_rejected(self) -> None:
        bundle, master = _tiny_bundle_and_master()
        wrong_universe_manifest = MembershipManifest(
            universe_id="UNIVERSE-WRONG",
            universe_version="1",
            records=(
                MembershipRecord(
                    universe_id="UNIVERSE-WRONG",
                    universe_version="1",
                    instrument_id=InstrumentId("INSTR-AAPL-001"),
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    membership_status=MembershipStatus.ACTIVE,
                    source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
                ),
            ),
        )
        with pytest.raises(ValueError, match="universe_id"):
            _build(bundle, master, wrong_universe_manifest, study_number=9931, stress_number=9932)
