"""MILESTONE-065 pure unit tests: corporate-action domain.

Split/reverse-split ratio validation, symbol-change chain validation,
manifest de-duplication and canonical ordering, `symbol_at` /
`split_adjustment_factor_at` / `volume_adjustment_factor_at` boundary
semantics, and corporate-action-manifest hash determinism/order-
independence/tamper-sensitivity.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.decision_candidate.corporate_actions import (
    CorporateActionManifest,
    CorporateActionType,
    SplitAction,
    SymbolChangeAction,
    corporate_action_manifest_hash,
    split_adjustment_factor_at,
    symbol_at,
    volume_adjustment_factor_at,
)
from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.market_data import Instrument

_T0 = datetime(2024, 3, 1, 9, 45, tzinfo=UTC)
_BEFORE = datetime(2024, 3, 1, 9, 44, tzinfo=UTC)
_AFTER = datetime(2024, 3, 1, 9, 46, tzinfo=UTC)
_BETA = InstrumentId("INSTR-BETA-001")
_GAMA = InstrumentId("INSTR-GAMA-001")
_DELT = InstrumentId("INSTR-DELT-001")


def _split(
    *,
    instrument_id: InstrumentId = _BETA,
    action_type: CorporateActionType = CorporateActionType.SPLIT,
    effective_timestamp: datetime = _T0,
    ratio_new_shares: int = 2,
    ratio_old_shares: int = 1,
) -> SplitAction:
    return SplitAction(
        instrument_id=instrument_id,
        action_type=action_type,
        effective_timestamp=effective_timestamp,
        ratio_new_shares=ratio_new_shares,
        ratio_old_shares=ratio_old_shares,
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
    )


def _symbol_change(
    *,
    instrument_id: InstrumentId = _DELT,
    effective_timestamp: datetime = _T0,
    old_symbol: str = "OLDD",
    new_symbol: str = "DELT",
) -> SymbolChangeAction:
    return SymbolChangeAction(
        instrument_id=instrument_id,
        action_type=CorporateActionType.SYMBOL_CHANGE,
        effective_timestamp=effective_timestamp,
        old_symbol=Instrument(old_symbol),
        new_symbol=Instrument(new_symbol),
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
    )


# --------------------------------------------------------------------------
# SplitAction
# --------------------------------------------------------------------------


def test_split_action_two_for_one_adjustment_factors() -> None:
    action = _split(ratio_new_shares=2, ratio_old_shares=1)
    from decimal import Decimal

    assert action.adjustment_factor == Decimal("0.5")
    assert action.volume_adjustment_factor == Decimal("2")
    assert action.adjustment_factor * action.volume_adjustment_factor == 1


def test_reverse_split_one_for_five_adjustment_factors() -> None:
    action = _split(
        instrument_id=_GAMA,
        action_type=CorporateActionType.REVERSE_SPLIT,
        ratio_new_shares=1,
        ratio_old_shares=5,
    )
    from decimal import Decimal

    assert action.adjustment_factor == Decimal("5")
    assert action.volume_adjustment_factor == Decimal("0.2")


def test_split_action_rejects_symbol_change_type() -> None:
    with pytest.raises(ValueError, match="SPLIT or REVERSE_SPLIT"):
        _split(action_type=CorporateActionType.SYMBOL_CHANGE)


def test_split_action_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _split(effective_timestamp=datetime(2024, 3, 1, 9, 45))  # noqa: DTZ001


def test_split_action_rejects_one_for_one_ratio() -> None:
    with pytest.raises(ValueError, match="1-for-1"):
        _split(ratio_new_shares=3, ratio_old_shares=3)


@pytest.mark.parametrize("ratio_new_shares,ratio_old_shares", [(0, 1), (1, 0), (-2, 1), (2, -1)])
def test_split_action_rejects_non_positive_ratio_components(
    ratio_new_shares: int, ratio_old_shares: int
) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        _split(ratio_new_shares=ratio_new_shares, ratio_old_shares=ratio_old_shares)


def test_split_action_rejects_ratio_direction_mismatch_for_split() -> None:
    with pytest.raises(ValueError, match="SPLIT requires ratio_new_shares > ratio_old_shares"):
        _split(action_type=CorporateActionType.SPLIT, ratio_new_shares=1, ratio_old_shares=5)


def test_split_action_rejects_ratio_direction_mismatch_for_reverse_split() -> None:
    with pytest.raises(
        ValueError, match="REVERSE_SPLIT requires ratio_new_shares < ratio_old_shares"
    ):
        _split(
            action_type=CorporateActionType.REVERSE_SPLIT, ratio_new_shares=2, ratio_old_shares=1
        )


def test_split_action_rejects_empty_source_kind() -> None:
    with pytest.raises(ValueError, match="source_kind"):
        SplitAction(
            instrument_id=_BETA,
            action_type=CorporateActionType.SPLIT,
            effective_timestamp=_T0,
            ratio_new_shares=2,
            ratio_old_shares=1,
            source_kind="   ",
        )


# --------------------------------------------------------------------------
# SymbolChangeAction
# --------------------------------------------------------------------------


def test_symbol_change_action_rejects_non_symbol_change_type() -> None:
    with pytest.raises(ValueError, match="must be SYMBOL_CHANGE"):
        SymbolChangeAction(
            instrument_id=_DELT,
            action_type=CorporateActionType.SPLIT,
            effective_timestamp=_T0,
            old_symbol=Instrument("OLDD"),
            new_symbol=Instrument("DELT"),
            source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        )


def test_symbol_change_action_rejects_identical_symbols() -> None:
    with pytest.raises(ValueError, match="two distinct symbols"):
        _symbol_change(old_symbol="DELT", new_symbol="DELT")


def test_symbol_change_action_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _symbol_change(effective_timestamp=datetime(2024, 3, 1, 9, 45))  # noqa: DTZ001


# --------------------------------------------------------------------------
# CorporateActionManifest
# --------------------------------------------------------------------------


def test_manifest_rejects_duplicate_action() -> None:
    action = _split()
    with pytest.raises(ValueError, match="duplicate corporate action"):
        CorporateActionManifest(
            dataset_id="DATASET-1", dataset_version="1", actions=(action, action)
        )


def test_manifest_canonicalizes_order_independent_of_input_order() -> None:
    split = _split()
    reverse_split = _split(
        instrument_id=_GAMA,
        action_type=CorporateActionType.REVERSE_SPLIT,
        ratio_new_shares=1,
        ratio_old_shares=5,
    )
    symbol_change = _symbol_change()

    manifest_a = CorporateActionManifest(
        dataset_id="DATASET-1",
        dataset_version="1",
        actions=(split, reverse_split, symbol_change),
    )
    manifest_b = CorporateActionManifest(
        dataset_id="DATASET-1",
        dataset_version="1",
        actions=(symbol_change, split, reverse_split),
    )
    manifest_c = CorporateActionManifest(
        dataset_id="DATASET-1",
        dataset_version="1",
        actions=(reverse_split, symbol_change, split),
    )
    assert manifest_a == manifest_b == manifest_c
    assert manifest_a.actions == manifest_b.actions == manifest_c.actions


def test_manifest_rejects_conflicting_symbol_change_chain() -> None:
    first = _symbol_change(effective_timestamp=_T0, old_symbol="OLDD", new_symbol="MIDD")
    conflicting_second = _symbol_change(
        effective_timestamp=_AFTER, old_symbol="ZZZZ", new_symbol="DELT"
    )
    with pytest.raises(ValueError, match="conflicting symbol-change chain"):
        CorporateActionManifest(
            dataset_id="DATASET-1", dataset_version="1", actions=(first, conflicting_second)
        )


def test_manifest_accepts_valid_chained_symbol_changes() -> None:
    first = _symbol_change(effective_timestamp=_T0, old_symbol="OLDD", new_symbol="MIDD")
    second = _symbol_change(
        effective_timestamp=datetime(2024, 4, 1, tzinfo=UTC), old_symbol="MIDD", new_symbol="DELT"
    )
    manifest = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(second, first)
    )
    assert manifest.symbol_changes_for(_DELT) == (first, second)


def test_manifest_rejects_empty_dataset_id_or_version() -> None:
    with pytest.raises(ValueError, match="dataset_id"):
        CorporateActionManifest(dataset_id="  ", dataset_version="1", actions=())
    with pytest.raises(ValueError, match="dataset_version"):
        CorporateActionManifest(dataset_id="DATASET-1", dataset_version=" ", actions=())


def test_manifest_splits_for_filters_by_instrument_and_type() -> None:
    beta_split = _split()
    gama_reverse = _split(
        instrument_id=_GAMA,
        action_type=CorporateActionType.REVERSE_SPLIT,
        ratio_new_shares=1,
        ratio_old_shares=5,
    )
    manifest = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(beta_split, gama_reverse)
    )
    assert manifest.splits_for(_BETA) == (beta_split,)
    assert manifest.splits_for(_GAMA) == (gama_reverse,)
    assert manifest.splits_for(_DELT) == ()


# --------------------------------------------------------------------------
# symbol_at / split_adjustment_factor_at / volume_adjustment_factor_at
# --------------------------------------------------------------------------


def _delt_manifest() -> CorporateActionManifest:
    return CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(_symbol_change(),)
    )


def _beta_gama_manifest() -> CorporateActionManifest:
    return CorporateActionManifest(
        dataset_id="DATASET-1",
        dataset_version="1",
        actions=(
            _split(),
            _split(
                instrument_id=_GAMA,
                action_type=CorporateActionType.REVERSE_SPLIT,
                ratio_new_shares=1,
                ratio_old_shares=5,
            ),
        ),
    )


def test_symbol_at_before_boundary_returns_old_symbol() -> None:
    manifest = _delt_manifest()
    assert symbol_at(manifest, _DELT, Instrument("DELT"), _BEFORE) == Instrument("OLDD")


def test_symbol_at_at_boundary_returns_new_symbol() -> None:
    manifest = _delt_manifest()
    assert symbol_at(manifest, _DELT, Instrument("DELT"), _T0) == Instrument("DELT")


def test_symbol_at_after_boundary_returns_new_symbol() -> None:
    manifest = _delt_manifest()
    assert symbol_at(manifest, _DELT, Instrument("DELT"), _AFTER) == Instrument("DELT")


def test_symbol_at_with_no_changes_returns_current_symbol() -> None:
    manifest = CorporateActionManifest(dataset_id="DATASET-1", dataset_version="1", actions=())
    assert symbol_at(manifest, _BETA, Instrument("BETA"), _BEFORE) == Instrument("BETA")


def test_split_adjustment_factor_before_boundary_is_not_one() -> None:
    manifest = _beta_gama_manifest()
    from decimal import Decimal

    assert split_adjustment_factor_at(manifest, _BETA, _BEFORE) == Decimal("0.5")
    assert split_adjustment_factor_at(manifest, _GAMA, _BEFORE) == Decimal("5")


def test_split_adjustment_factor_at_and_after_boundary_is_one() -> None:
    manifest = _beta_gama_manifest()
    assert split_adjustment_factor_at(manifest, _BETA, _T0) == 1
    assert split_adjustment_factor_at(manifest, _BETA, _AFTER) == 1
    assert split_adjustment_factor_at(manifest, _GAMA, _T0) == 1


def test_volume_adjustment_factor_is_exact_inverse_of_price_factor() -> None:
    manifest = _beta_gama_manifest()
    price_factor = split_adjustment_factor_at(manifest, _BETA, _BEFORE)
    volume_factor = volume_adjustment_factor_at(manifest, _BETA, _BEFORE)
    assert price_factor * volume_factor == 1


def test_split_adjustment_factor_with_no_splits_for_instrument_is_one() -> None:
    manifest = _beta_gama_manifest()
    assert split_adjustment_factor_at(manifest, _DELT, _BEFORE) == 1


def test_split_adjustment_factor_compounds_multiple_splits() -> None:
    early = _split(ratio_new_shares=2, ratio_old_shares=1, effective_timestamp=_T0)
    later = _split(
        ratio_new_shares=3,
        ratio_old_shares=1,
        effective_timestamp=datetime(2024, 4, 1, tzinfo=UTC),
    )
    manifest = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(early, later)
    )
    from decimal import Decimal

    factor = split_adjustment_factor_at(manifest, _BETA, _BEFORE)
    assert factor == Decimal("0.5") * (Decimal("1") / Decimal("3"))


# --------------------------------------------------------------------------
# corporate_action_manifest_hash: determinism, order-independence, tamper
# --------------------------------------------------------------------------


def test_manifest_hash_is_order_independent() -> None:
    split = _split()
    reverse_split = _split(
        instrument_id=_GAMA,
        action_type=CorporateActionType.REVERSE_SPLIT,
        ratio_new_shares=1,
        ratio_old_shares=5,
    )
    manifest_a = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(split, reverse_split)
    )
    manifest_b = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(reverse_split, split)
    )
    assert corporate_action_manifest_hash(manifest_a) == corporate_action_manifest_hash(manifest_b)


def test_manifest_hash_changes_when_ratio_changes() -> None:
    original = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(_split(ratio_new_shares=2),)
    )
    tampered = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(_split(ratio_new_shares=3),)
    )
    assert corporate_action_manifest_hash(original) != corporate_action_manifest_hash(tampered)


def test_manifest_hash_changes_when_effective_timestamp_changes() -> None:
    original = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(_split(),)
    )
    tampered = CorporateActionManifest(
        dataset_id="DATASET-1", dataset_version="1", actions=(_split(effective_timestamp=_AFTER),)
    )
    assert corporate_action_manifest_hash(original) != corporate_action_manifest_hash(tampered)


def test_manifest_hash_is_deterministic_across_repeated_calls() -> None:
    manifest = _beta_gama_manifest()
    assert corporate_action_manifest_hash(manifest) == corporate_action_manifest_hash(manifest)
