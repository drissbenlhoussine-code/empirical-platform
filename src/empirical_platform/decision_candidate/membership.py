"""Effective-dated universe membership authority.

MILESTONE-064. `MembershipRecord` states that one `InstrumentId` held one
`membership_status` for one half-open time interval
`[effective_from, effective_to)` within one `(universe_id, universe_version)`
universe. `effective_from` is inclusive; `effective_to` is exclusive (or
open-ended, `None`, meaning "still in effect"). A `MembershipManifest` is
the immutable, hashable collection of every record for one universe version.

Only `ACTIVE` records make an instrument *eligible* at a cutoff (see
`historical_universe.universe_at`) -- `INACTIVE` / `DELISTED_LIKE` /
`INACTIVE_LIKE` records exist so that a formerly-active instrument's
historical status is explicitly recorded (and its bars remain queryable),
never so it can silently re-enter eligibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from empirical_platform.decision_candidate.instrument_master import InstrumentId, InstrumentMaster
from empirical_platform.decision_candidate.universe_authority import UniverseAuthority


class MembershipStatus(StrEnum):
    """Closed membership-status vocabulary. Only `ACTIVE` contributes
    eligibility in `universe_at()`; the other three values are honest
    historical labels, not different flavors of eligibility."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DELISTED_LIKE = "DELISTED_LIKE"
    INACTIVE_LIKE = "INACTIVE_LIKE"


@dataclass(frozen=True, slots=True)
class MembershipRecord:
    """One immutable effective-dated membership fact."""

    universe_id: str
    universe_version: str
    instrument_id: InstrumentId
    effective_from: datetime
    effective_to: datetime | None
    membership_status: MembershipStatus
    source_kind: str

    def __post_init__(self) -> None:
        for field_name in ("universe_id", "universe_version", "source_kind"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if not isinstance(self.instrument_id, InstrumentId):
            raise TypeError("instrument_id must be an InstrumentId")
        if not isinstance(self.membership_status, MembershipStatus):
            raise TypeError("membership_status must be a MembershipStatus")
        if not isinstance(self.effective_from, datetime) or self.effective_from.tzinfo is None:
            raise ValueError("effective_from must be a timezone-aware datetime")
        if self.effective_to is not None:
            if not isinstance(self.effective_to, datetime) or self.effective_to.tzinfo is None:
                raise ValueError("effective_to must be a timezone-aware datetime when set")
            if self.effective_to <= self.effective_from:
                raise ValueError("effective_to must be strictly after effective_from")

    def covers(self, cutoff: datetime) -> bool:
        """Whether `cutoff` falls within this record's own
        `[effective_from, effective_to)` interval, regardless of status."""
        if cutoff < self.effective_from:
            return False
        if self.effective_to is not None and cutoff >= self.effective_to:
            return False
        return True


@dataclass(frozen=True, slots=True)
class MembershipManifest:
    """The immutable, hashable set of every membership record for one
    `(universe_id, universe_version)` universe."""

    universe_id: str
    universe_version: str
    records: tuple[MembershipRecord, ...]

    def __post_init__(self) -> None:
        for field_name in ("universe_id", "universe_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.records) < 1:
            raise ValueError("a membership manifest must contain at least 1 record")
        for record in self.records:
            if record.universe_id != self.universe_id:
                raise ValueError("every record's universe_id must match the manifest's own")
            if record.universe_version != self.universe_version:
                raise ValueError("every record's universe_version must match the manifest's own")

        seen_starts: set[tuple[InstrumentId, datetime]] = set()
        by_instrument: dict[InstrumentId, list[MembershipRecord]] = {}
        for record in self.records:
            key = (record.instrument_id, record.effective_from)
            if key in seen_starts:
                raise ValueError(
                    f"duplicate membership record for {record.instrument_id} starting at "
                    f"{record.effective_from.isoformat()}"
                )
            seen_starts.add(key)
            by_instrument.setdefault(record.instrument_id, []).append(record)

        for instrument_id, instrument_records in by_instrument.items():
            ordered = sorted(instrument_records, key=lambda record: record.effective_from)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if previous.effective_to is None:
                    raise ValueError(
                        f"{instrument_id} has an open-ended record followed by another record"
                    )
                if current.effective_from < previous.effective_to:
                    raise ValueError(
                        f"{instrument_id} has overlapping membership intervals "
                        f"({previous.effective_from.isoformat()} and "
                        f"{current.effective_from.isoformat()})"
                    )

    def instruments_referenced(self) -> tuple[InstrumentId, ...]:
        seen: list[InstrumentId] = []
        for record in self.records:
            if record.instrument_id not in seen:
                seen.append(record.instrument_id)
        return tuple(seen)

    def validate_against_master(self, instrument_master: InstrumentMaster) -> None:
        """Reject any record referencing an `InstrumentId` absent from the
        supplied instrument master."""
        for instrument_id in self.instruments_referenced():
            if not instrument_master.contains(instrument_id):
                raise ValueError(
                    f"membership manifest references unknown instrument: {instrument_id}"
                )


def canonical_membership_payload(manifest: MembershipManifest) -> list[dict[str, str]]:
    """Canonical, stable-order JSON-serializable representation of every
    record in `manifest`, sorted by `(instrument_id, effective_from)` --
    independent of the manifest's own input order. Used as the exact input
    to `membership_manifest_hash()`."""
    ordered = sorted(
        manifest.records, key=lambda record: (str(record.instrument_id), record.effective_from)
    )
    return [
        {
            "universe_id": record.universe_id,
            "universe_version": record.universe_version,
            "instrument_id": str(record.instrument_id),
            "effective_from": record.effective_from.isoformat(),
            "effective_to": record.effective_to.isoformat() if record.effective_to else "",
            "membership_status": record.membership_status.value,
            "source_kind": record.source_kind,
        }
        for record in ordered
    ]


def membership_manifest_hash(manifest: MembershipManifest) -> str:
    """SHA-256 of the canonical JSON payload -- same semantic membership in
    any input order produces the same hash; any semantic change produces a
    different hash."""
    payload = canonical_membership_payload(manifest)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class UniverseMembershipRepository(Protocol):
    """Persistence-neutral repository contract for the write-once
    `universe_authority` / `membership_record` reference tables."""

    def add_universe(self, authority: UniverseAuthority) -> None:
        """Persist one universe authority identity (idempotent)."""
        ...

    def add_membership(self, manifest: MembershipManifest) -> None:
        """Persist every record in `manifest` (idempotent)."""
        ...
