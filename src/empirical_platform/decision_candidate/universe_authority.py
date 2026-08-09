"""Versioned universe authority identity.

MILESTONE-064. `UniverseAuthority` is deliberately bare: it carries only the
identity of one versioned instrument universe (its `universe_id` /
`universe_version` / `source_kind`). The actual time-varying constituents
live in `membership.py`'s `MembershipManifest`, keyed by the same
`(universe_id, universe_version)` pair. Multiple universe versions can
coexist -- there is no singleton/global universe state anywhere in this
module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UniverseAuthority:
    """Immutable identity record for one versioned instrument universe."""

    universe_id: str
    universe_version: str
    source_kind: str

    def __post_init__(self) -> None:
        for field_name in ("universe_id", "universe_version", "source_kind"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
