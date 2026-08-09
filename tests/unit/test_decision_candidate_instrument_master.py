"""MILESTONE-064 unit tests for stable instrument identity."""

from __future__ import annotations

import pytest

from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Instrument


def _entry(symbol: str, *, number: int = 1) -> InstrumentMasterEntry:
    return InstrumentMasterEntry(
        instrument_id=InstrumentId(f"INSTR-{symbol}-{number:03d}"),
        canonical_symbol=Instrument(symbol),
        instrument_type=InstrumentType.EQUITY,
    )


class TestInstrumentId:
    def test_valid_format_accepted(self) -> None:
        assert str(InstrumentId("INSTR-AAPL-001")) == "INSTR-AAPL-001"

    @pytest.mark.parametrize(
        "value",
        [
            "AAPL-001",
            "INSTR-aapl-001",
            "INSTR-AAPL-01",
            "INSTR-AAPL-0001",
            "INSTR-TOOLONGX-001",
            "",
            "INSTR--001",
        ],
    )
    def test_invalid_format_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="InstrumentId"):
            InstrumentId(value)


class TestInstrumentMasterEntry:
    def test_optional_fields_default_none(self) -> None:
        entry = _entry("AAPL")
        assert entry.exchange_or_venue is None
        assert entry.external_identifier is None

    def test_empty_optional_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="exchange_or_venue"):
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-AAPL-001"),
                canonical_symbol=Instrument("AAPL"),
                instrument_type=InstrumentType.EQUITY,
                exchange_or_venue="   ",
            )


class TestInstrumentMaster:
    def test_empty_master_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1 entry"):
            InstrumentMaster(entries=())

    def test_duplicate_instrument_id_rejected(self) -> None:
        duplicate = InstrumentMasterEntry(
            instrument_id=InstrumentId("INSTR-AAPL-001"),
            canonical_symbol=Instrument("MSFT"),
            instrument_type=InstrumentType.EQUITY,
        )
        with pytest.raises(ValueError, match="instrument_id"):
            InstrumentMaster(entries=(_entry("AAPL"), duplicate))

    def test_duplicate_canonical_symbol_rejected(self) -> None:
        duplicate_symbol = InstrumentMasterEntry(
            instrument_id=InstrumentId("INSTR-AAPL-002"),
            canonical_symbol=Instrument("AAPL"),
            instrument_type=InstrumentType.EQUITY,
        )
        with pytest.raises(ValueError, match="canonical_symbol"):
            InstrumentMaster(entries=(_entry("AAPL"), duplicate_symbol))

    def test_entry_for_returns_matching_entry(self) -> None:
        master = InstrumentMaster(entries=(_entry("AAPL"), _entry("MSFT")))
        assert master.entry_for(InstrumentId("INSTR-MSFT-001")).canonical_symbol == Instrument(
            "MSFT"
        )

    def test_entry_for_unknown_instrument_raises_key_error(self) -> None:
        master = InstrumentMaster(entries=(_entry("AAPL"),))
        with pytest.raises(KeyError):
            master.entry_for(InstrumentId("INSTR-TSLA-001"))

    def test_contains_true_and_false(self) -> None:
        master = InstrumentMaster(entries=(_entry("AAPL"),))
        assert master.contains(InstrumentId("INSTR-AAPL-001")) is True
        assert master.contains(InstrumentId("INSTR-TSLA-001")) is False

    def test_symbol_by_instrument_id_mapping(self) -> None:
        master = InstrumentMaster(entries=(_entry("AAPL"), _entry("MSFT")))
        mapping = master.symbol_by_instrument_id
        assert mapping[InstrumentId("INSTR-AAPL-001")] == Instrument("AAPL")
        assert mapping[InstrumentId("INSTR-MSFT-001")] == Instrument("MSFT")
