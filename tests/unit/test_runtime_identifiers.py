from __future__ import annotations

import uuid

import pytest

from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
    UuidRuntimeIdentifierGenerator,
    is_valid_runtime_identifier,
)


def test_uuid_runtime_identifier_generation_and_validation() -> None:
    identifier = UuidRuntimeIdentifierGenerator().generate()

    assert is_valid_runtime_identifier(str(identifier))
    assert str(identifier).count("-") == 4
    assert not str(identifier).startswith(("CAMP", "RUN", "EVID", "AUD", "DCAND"))


def test_runtime_identifier_rejects_malformed_or_governance_values() -> None:
    with pytest.raises(ValueError):
        RuntimeIdentifier("CAMP-0001")
    with pytest.raises(ValueError):
        RuntimeIdentifier(str(uuid.uuid4()).upper())
    assert not is_valid_runtime_identifier("RUN-0001")


def test_deterministic_runtime_identifier_substitute() -> None:
    value = str(uuid.uuid4())
    generator = DeterministicRuntimeIdentifierGenerator([value])

    assert str(generator.generate()) == value
    with pytest.raises(FoundationError):
        generator.generate()
