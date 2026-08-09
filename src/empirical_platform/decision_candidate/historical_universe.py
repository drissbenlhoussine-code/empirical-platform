"""Deterministic historical universe derivation.

MILESTONE-064. `universe_at(manifest, cutoff)` answers: "which instruments
were eligible, according to this membership authority, at this instant?"
Eligibility requires an `ACTIVE` record whose `[effective_from,
effective_to)` interval covers `cutoff`. The result is always canonically
ordered (lexicographic by `instrument_id`) and never depends on the
manifest's own record input order.

This is the ONLY production code path a survivorship-aware study may use to
derive per-window eligibility. A separately-authored verifier (never
importing this function) lives in
`tests/unit/test_independent_universe_derivation.py`, per the mission's own
"independent membership derivation" requirement.
"""

from __future__ import annotations

from datetime import datetime

from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.membership import MembershipManifest, MembershipStatus


def universe_at(manifest: MembershipManifest, cutoff: datetime) -> tuple[InstrumentId, ...]:
    """Return the canonically ordered set of `InstrumentId`s eligible at
    `cutoff`, given `manifest`. Deterministic: same manifest and cutoff
    always produce the same ordered tuple, regardless of the manifest's own
    record declaration order."""
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
        raise ValueError("cutoff must be a timezone-aware datetime")
    eligible: set[InstrumentId] = set()
    for record in manifest.records:
        if record.membership_status is MembershipStatus.ACTIVE and record.covers(cutoff):
            eligible.add(record.instrument_id)
    return tuple(sorted(eligible, key=str))
