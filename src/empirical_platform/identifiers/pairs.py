"""Pair governance identifiers with opaque runtime identifiers."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers.types import Identifier
from empirical_platform.shared.identifiers import RuntimeIdentifier


@dataclass(frozen=True, slots=True)
class DomainIdentity[GovernanceIdentifierT: Identifier]:
    """Typed pairing of a governance identifier and runtime UUID."""

    governance_id: GovernanceIdentifierT
    runtime_id: RuntimeIdentifier

    def __post_init__(self) -> None:
        if not isinstance(self.governance_id, Identifier):
            raise TypeError("governance_id must be a governance Identifier")
        if not isinstance(self.runtime_id, RuntimeIdentifier):
            raise TypeError("runtime_id must be a RuntimeIdentifier")


def pair_identity[GovernanceIdentifierT: Identifier](
    governance_id: GovernanceIdentifierT,
    runtime_id: RuntimeIdentifier,
) -> DomainIdentity[GovernanceIdentifierT]:
    """Create a typed governance/runtime identity pair."""
    return DomainIdentity(governance_id=governance_id, runtime_id=runtime_id)
