from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError

import pytest

from empirical_platform.identifiers import CampaignId, DomainIdentity, RunId, pair_identity
from empirical_platform.shared.identifiers import RuntimeIdentifier


def test_domain_identity_pairs_governance_id_with_runtime_uuid_without_replacement() -> None:
    runtime_id = RuntimeIdentifier(str(uuid.uuid4()))
    identity = pair_identity(CampaignId("CAMP-0001"), runtime_id)

    assert isinstance(identity, DomainIdentity)
    assert str(identity.governance_id) == "CAMP-0001"
    assert identity.runtime_id == runtime_id
    assert str(identity.runtime_id) != str(identity.governance_id)


def test_domain_identity_is_typed_and_immutable() -> None:
    identity = pair_identity(RunId("RUN-0001"), RuntimeIdentifier(str(uuid.uuid4())))

    with pytest.raises(FrozenInstanceError):
        identity.governance_id = RunId("RUN-0002")  # type: ignore[misc]


def test_domain_identity_rejects_interchanged_identifier_types() -> None:
    runtime_id = RuntimeIdentifier(str(uuid.uuid4()))

    with pytest.raises(TypeError):
        DomainIdentity(governance_id=runtime_id, runtime_id=runtime_id)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DomainIdentity(  # type: ignore[arg-type]
            governance_id=CampaignId("CAMP-0001"),
            runtime_id=CampaignId("CAMP-0001"),
        )
