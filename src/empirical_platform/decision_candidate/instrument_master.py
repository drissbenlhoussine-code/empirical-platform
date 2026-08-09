"""Stable, cross-time instrument identity.

MILESTONE-064. The existing M057 `Instrument` value object (a bare ticker
symbol) is sufficient for one-cutoff evaluation but is not, by itself, a
stable key for historical *membership* records: a ticker can in principle be
reused across time (out of scope here, but the identity model must not
assume otherwise). `InstrumentId` adds one additional, deliberately minimal
stable-identity layer that `MembershipRecord` (see `membership.py`) keys on.
`Instrument` itself is unmodified and remains the sole identity used by
every frozen M057-M063 execution path.

This is not a global cross-tenant security master: no corporate-action
history, no symbol-rename tracking, one row per instrument for the lifetime
of this milestone's fixture (see `CORPORATE_ACTION_HANDLING_NOT_EXERCISED`
in `survivorship_study.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from empirical_platform.decision_candidate.market_data import Instrument

_INSTRUMENT_ID_PATTERN = re.compile(r"^INSTR-[A-Z]{1,5}-\d{3}$")


class InstrumentType(StrEnum):
    """Closed, deliberately narrow instrument-type vocabulary -- matches
    the M057 scope boundary (US-listed equities and ETFs only)."""

    EQUITY = "EQUITY"
    ETF = "ETF"


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """A stable, opaque, cross-time instrument identifier.

    Format `INSTR-{SYMBOL}-{NNN}`, e.g. `INSTR-AAPL-001` -- distinct from
    the generic `Identifier` base (`identifiers/types.py`), whose pattern
    (`PREFIX-\\d{4}`) cannot embed a ticker symbol.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _INSTRUMENT_ID_PATTERN.match(self.value):
            raise ValueError("InstrumentId must match ^INSTR-[A-Z]{1,5}-\\d{3}$")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class InstrumentMasterEntry:
    """One stable instrument's identity record: its `InstrumentId`, its
    current canonical `Instrument` ticker, its instrument type, and
    optional venue/external identity fields (never empty strings when
    present -- `None` means "not recorded")."""

    instrument_id: InstrumentId
    canonical_symbol: Instrument
    instrument_type: InstrumentType
    exchange_or_venue: str | None = None
    external_identifier: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise TypeError("instrument_id must be an InstrumentId")
        if not isinstance(self.canonical_symbol, Instrument):
            raise TypeError("canonical_symbol must be an Instrument")
        if not isinstance(self.instrument_type, InstrumentType):
            raise TypeError("instrument_type must be an InstrumentType")
        if self.exchange_or_venue is not None and not self.exchange_or_venue.strip():
            raise ValueError("exchange_or_venue must not be an empty string when set")
        if self.external_identifier is not None and not self.external_identifier.strip():
            raise ValueError("external_identifier must not be an empty string when set")


@dataclass(frozen=True, slots=True)
class InstrumentMaster:
    """An immutable, deterministic registry of stable instrument identities.

    One entry per `instrument_id` for the lifetime of this milestone's
    fixture (no symbol-rename / re-identification history)."""

    entries: tuple[InstrumentMasterEntry, ...]

    def __post_init__(self) -> None:
        if len(self.entries) < 1:
            raise ValueError("an instrument master must contain at least 1 entry")
        ids = [entry.instrument_id for entry in self.entries]
        if len(set(ids)) != len(ids):
            raise ValueError("instrument_id values must be unique within an instrument master")
        symbols = [entry.canonical_symbol for entry in self.entries]
        if len(set(symbols)) != len(symbols):
            raise ValueError("canonical_symbol values must be unique within an instrument master")

    def entry_for(self, instrument_id: InstrumentId) -> InstrumentMasterEntry:
        for entry in self.entries:
            if entry.instrument_id == instrument_id:
                return entry
        raise KeyError(f"unknown instrument_id: {instrument_id}")

    def contains(self, instrument_id: InstrumentId) -> bool:
        return any(entry.instrument_id == instrument_id for entry in self.entries)

    @property
    def symbol_by_instrument_id(self) -> dict[InstrumentId, Instrument]:
        return {entry.instrument_id: entry.canonical_symbol for entry in self.entries}


class InstrumentMasterRepository(Protocol):
    """Persistence-neutral repository contract for the write-once
    instrument-master reference table."""

    def add_all(self, master: InstrumentMaster) -> None:
        """Persist every entry in `master` (idempotent -- already-known
        instrument_ids are left untouched, never duplicated or errored
        on)."""
        ...
