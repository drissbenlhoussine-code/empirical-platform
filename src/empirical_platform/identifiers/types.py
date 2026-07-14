"""Generic identifier propagation primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Identifier:
    """Base canonical identifier value object."""

    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        pattern = rf"^{self.prefix}-\d{{4}}$"
        if not re.match(pattern, self.value):
            raise ValueError(f"Identifier must match {pattern}")

    def __str__(self) -> str:
        return self.value


class CampaignId(Identifier):
    """Campaign identifier."""

    prefix = "CAMP"


class RunId(Identifier):
    """Run identifier."""

    prefix = "RUN"


class DatasetId(Identifier):
    """Dataset identifier."""

    prefix = "DATASET"


class EvidencePackageId(Identifier):
    """Evidence package identifier."""

    prefix = "EVID"


class ReviewId(Identifier):
    """Review identifier."""

    prefix = "REVIEW"


class AuditId(Identifier):
    """Audit identifier."""

    prefix = "AUD"


class DecisionCandidateId(Identifier):
    """Decision candidate identifier."""

    prefix = "DCAND"
