"""Corporate-action domain: stock splits, reverse splits, and symbol
changes, keyed by the stable M064 `InstrumentId`.

MILESTONE-065. A `CorporateActionManifest` is the immutable, hashable
record of every declared corporate action for one dataset snapshot's own
instrument universe. Only three action types are supported: `SPLIT`,
`REVERSE_SPLIT`, `SYMBOL_CHANGE`. Dividend / total-return handling is
explicitly NOT implemented -- see `dataset_snapshot.py`'s
`DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED` constant. No new instrument
identity is ever created for a symbol change; the stable `InstrumentId`
persists across the rename, exactly as M064 already requires for
membership continuity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.market_data import Instrument


class CorporateActionType(StrEnum):
    """Closed corporate-action vocabulary. `DIVIDEND` is deliberately
    absent -- see `DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED`."""

    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"


@dataclass(frozen=True, slots=True)
class SplitAction:
    """One immutable split or reverse-split event.

    `ratio_new_shares : ratio_old_shares` states that every
    `ratio_old_shares` held immediately before `effective_timestamp` become
    `ratio_new_shares` immediately at/after it -- e.g. a "2-for-1" split is
    `ratio_new_shares=2, ratio_old_shares=1`; a "1-for-5" reverse split is
    `ratio_new_shares=1, ratio_old_shares=5`. `action_type` must agree with
    the ratio's own direction (`SPLIT` requires `new > old`, `REVERSE_SPLIT`
    requires `new < old`) -- this is validated, not merely labeled.
    """

    instrument_id: InstrumentId
    action_type: CorporateActionType
    effective_timestamp: datetime
    ratio_new_shares: int
    ratio_old_shares: int
    source_kind: str

    def __post_init__(self) -> None:
        if self.action_type not in (CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT):
            raise ValueError("SplitAction.action_type must be SPLIT or REVERSE_SPLIT")
        if (
            not isinstance(self.effective_timestamp, datetime)
            or self.effective_timestamp.tzinfo is None
        ):
            raise ValueError("effective_timestamp must be a timezone-aware datetime")
        if self.ratio_new_shares <= 0 or self.ratio_old_shares <= 0:
            raise ValueError("split ratio components must be positive integers")
        if self.ratio_new_shares == self.ratio_old_shares:
            raise ValueError("a split ratio of 1-for-1 is not a corporate action")
        if (
            self.action_type is CorporateActionType.SPLIT
            and self.ratio_new_shares <= self.ratio_old_shares
        ):
            raise ValueError("SPLIT requires ratio_new_shares > ratio_old_shares")
        if (
            self.action_type is CorporateActionType.REVERSE_SPLIT
            and self.ratio_new_shares >= self.ratio_old_shares
        ):
            raise ValueError("REVERSE_SPLIT requires ratio_new_shares < ratio_old_shares")
        if not self.source_kind.strip():
            raise ValueError("source_kind must be non-empty")

    @property
    def adjustment_factor(self) -> Decimal:
        """Multiply a PRE-`effective_timestamp` raw price by this factor to
        express it in POST-split-comparable (adjusted) terms."""
        return Decimal(self.ratio_old_shares) / Decimal(self.ratio_new_shares)

    @property
    def volume_adjustment_factor(self) -> Decimal:
        """Multiply a PRE-`effective_timestamp` raw share volume by this
        factor to express it in POST-split-comparable (adjusted) terms --
        the exact inverse of the price adjustment factor, since total
        traded notional value is invariant under a pure split."""
        return Decimal(self.ratio_new_shares) / Decimal(self.ratio_old_shares)


@dataclass(frozen=True, slots=True)
class SymbolChangeAction:
    """One immutable symbol-rename event. The stable `InstrumentId` is
    unchanged; only which ticker symbol is in effect changes."""

    instrument_id: InstrumentId
    action_type: CorporateActionType
    effective_timestamp: datetime
    old_symbol: Instrument
    new_symbol: Instrument
    source_kind: str

    def __post_init__(self) -> None:
        if self.action_type is not CorporateActionType.SYMBOL_CHANGE:
            raise ValueError("SymbolChangeAction.action_type must be SYMBOL_CHANGE")
        if (
            not isinstance(self.effective_timestamp, datetime)
            or self.effective_timestamp.tzinfo is None
        ):
            raise ValueError("effective_timestamp must be a timezone-aware datetime")
        if self.old_symbol == self.new_symbol:
            raise ValueError("a symbol change must declare two distinct symbols")
        if not self.source_kind.strip():
            raise ValueError("source_kind must be non-empty")


CorporateAction = SplitAction | SymbolChangeAction


@dataclass(frozen=True, slots=True)
class CorporateActionManifest:
    """The immutable, hashable set of every declared corporate action for
    one dataset snapshot's own instrument universe."""

    dataset_id: str
    dataset_version: str
    actions: tuple[CorporateAction, ...]

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "dataset_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")

        seen: set[tuple[InstrumentId, datetime, CorporateActionType]] = set()
        for action in self.actions:
            key = (action.instrument_id, action.effective_timestamp, action.action_type)
            if key in seen:
                raise ValueError(
                    f"duplicate corporate action for {action.instrument_id} at "
                    f"{action.effective_timestamp.isoformat()} ({action.action_type.value})"
                )
            seen.add(key)

        # Canonicalize storage order to (instrument_id, effective_timestamp,
        # action_type) -- the same order the Postgres repository's own
        # retrieval query uses -- so that two manifests built from the same
        # semantic actions in any input order always compare equal, and a
        # construct-then-persist-then-retrieve round trip is exact.
        canonical_order = tuple(
            sorted(
                self.actions,
                key=lambda action: (
                    str(action.instrument_id),
                    action.effective_timestamp.isoformat(),
                    action.action_type.value,
                ),
            )
        )
        object.__setattr__(self, "actions", canonical_order)

        symbol_changes_by_instrument: dict[InstrumentId, list[SymbolChangeAction]] = {}
        for action in self.actions:
            if isinstance(action, SymbolChangeAction):
                symbol_changes_by_instrument.setdefault(action.instrument_id, []).append(action)

        for instrument_id, changes in symbol_changes_by_instrument.items():
            ordered = sorted(changes, key=lambda change: change.effective_timestamp)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if previous.new_symbol != current.old_symbol:
                    raise ValueError(
                        f"{instrument_id} has a conflicting symbol-change chain: "
                        f"{previous.new_symbol} then {current.old_symbol}"
                    )

    def splits_for(self, instrument_id: InstrumentId) -> tuple[SplitAction, ...]:
        return tuple(
            action
            for action in self.actions
            if isinstance(action, SplitAction) and action.instrument_id == instrument_id
        )

    def symbol_changes_for(self, instrument_id: InstrumentId) -> tuple[SymbolChangeAction, ...]:
        return tuple(
            sorted(
                (
                    action
                    for action in self.actions
                    if isinstance(action, SymbolChangeAction)
                    and action.instrument_id == instrument_id
                ),
                key=lambda action: action.effective_timestamp,
            )
        )


def symbol_at(
    manifest: CorporateActionManifest,
    instrument_id: InstrumentId,
    current_symbol: Instrument,
    timestamp: datetime,
) -> Instrument:
    """Resolve which ticker symbol was in effect for `instrument_id` at
    `timestamp`, given `current_symbol` (the symbol in effect after every
    declared symbol change) and the manifest's own symbol-change chain.
    Deterministic: walks the chain backward from the most recent change."""
    symbol = current_symbol
    for change in reversed(manifest.symbol_changes_for(instrument_id)):
        if timestamp < change.effective_timestamp:
            symbol = change.old_symbol
        else:
            break
    return symbol


def split_adjustment_factor_at(
    manifest: CorporateActionManifest, instrument_id: InstrumentId, bar_timestamp: datetime
) -> Decimal:
    """The cumulative price-adjustment factor to apply to a raw bar at
    `bar_timestamp` so that it becomes comparable to bars observed after
    every split whose `effective_timestamp` is strictly after
    `bar_timestamp` -- the product of each such split's own
    `adjustment_factor`, applied in effective-timestamp order."""
    factor = Decimal("1")
    for split in manifest.splits_for(instrument_id):
        if bar_timestamp < split.effective_timestamp:
            factor *= split.adjustment_factor
    return factor


def volume_adjustment_factor_at(
    manifest: CorporateActionManifest, instrument_id: InstrumentId, bar_timestamp: datetime
) -> Decimal:
    """The cumulative volume-adjustment factor, the exact inverse of
    `split_adjustment_factor_at`."""
    factor = Decimal("1")
    for split in manifest.splits_for(instrument_id):
        if bar_timestamp < split.effective_timestamp:
            factor *= split.volume_adjustment_factor
    return factor


def _action_payload(action: CorporateAction) -> dict[str, str]:
    if isinstance(action, SplitAction):
        return {
            "instrument_id": str(action.instrument_id),
            "action_type": action.action_type.value,
            "effective_timestamp": action.effective_timestamp.isoformat(),
            "ratio_new_shares": str(action.ratio_new_shares),
            "ratio_old_shares": str(action.ratio_old_shares),
            "source_kind": action.source_kind,
        }
    return {
        "instrument_id": str(action.instrument_id),
        "action_type": action.action_type.value,
        "effective_timestamp": action.effective_timestamp.isoformat(),
        "old_symbol": str(action.old_symbol),
        "new_symbol": str(action.new_symbol),
        "source_kind": action.source_kind,
    }


def canonical_corporate_action_payload(manifest: CorporateActionManifest) -> list[dict[str, str]]:
    """Canonical, stable-order JSON-serializable representation of every
    action in `manifest`, sorted by `(instrument_id, effective_timestamp,
    action_type)` -- independent of the manifest's own input order."""
    ordered = sorted(
        manifest.actions,
        key=lambda action: (
            str(action.instrument_id),
            action.effective_timestamp.isoformat(),
            action.action_type.value,
        ),
    )
    return [_action_payload(action) for action in ordered]


def corporate_action_manifest_hash(manifest: CorporateActionManifest) -> str:
    """SHA-256 of the canonical JSON payload -- same semantic manifest in
    any input order produces the same hash; any semantic change produces a
    different hash."""
    payload = canonical_corporate_action_payload(manifest)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
