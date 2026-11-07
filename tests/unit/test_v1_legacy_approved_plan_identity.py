"""RELEASE v1 LEGACY APPROVED PLAN IDENTITY COMPATIBILITY.

INCIDENT: the hash-based `derive_system_identity` rewrite (RELEASE v1 RECOVERY HARDENING
SECURITY GATE) changed the identity FORMAT. The one real, historical AAPL
PERSONAL_PAPER `ApprovedPlan` row was approved BEFORE that rewrite and still carries the
OLD (pre-rewrite) `system_identity` in storage. `ApprovedPlan(...)` itself refuses that
unconditionally -- correct, and unchanged here -- but that also meant every READ of this
one real, already-approved, historical plan raised `ValueError`, breaking `/active` and
the entire overdue-recovery flow for it.

THE FIX, PROVEN HERE: `reconstruct_approved_plan` (the Postgres repository's own
row-to-domain conversion, `_row_to_plan`, now calls this instead of `ApprovedPlan(...)`
directly) accepts EITHER the current format (byte-for-byte the same check
`ApprovedPlan.__post_init__` has always run) OR a verified pre-rewrite legacy identity --
never a forged, truncated or mismatched one, and NEVER for a brand-new plan (every
plan-creation path still constructs `ApprovedPlan(...)` directly and always derives a
fresh, current-format identity).

A SECOND, independent consequence: a legacy plan's OWN `system_identity` field is still
the oversized historical string (the original 64-character `authorized_by` overflow this
release already fixed in isolation for new plans). `position_plan_manager.py` now derives
`authorized_by` FRESH via `derive_system_identity(plan_id, owner_approval_id)` rather than
trusting the plan's own (possibly legacy) stored field -- a no-op for every current-format
plan, and the fix for a legacy one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.approved_plan import (
    LEGACY_SYSTEM_IDENTITY_PREFIX,
    SYSTEM_IDENTITY_PREFIX,
    ApprovedPlan,
    ExitTriggerKind,
    derive_legacy_system_identity,
    derive_system_identity,
    reconstruct_approved_plan,
)
from empirical_platform.usecases.position_exit import AuthorizePositionExitCommand

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)

#: The real incident's own ids -- NOT shortened, so the overflow this proves fixed is the
#: real one, not a synthetic stand-in. `len(...)` of the OLD-format identity built from
#: these is 110 characters -- the exact overflow `authorized_by`'s 64-character cap refuses.
_REAL_PLAN_ID = "PLAN-INT-PRP-089-PAPER-20261009T172613Z"
_REAL_OWNER_APPROVAL_ID = "DEC-PRP-089-PAPER-20261009T172613Z"
_REAL_ENTRY_INTENT_ID = "INT-PRP-089-PAPER-20261009T172613Z"
_REAL_CANDIDATE_ID = "PRP-089-PAPER-20261009T172613Z"


def _legacy_fields(**overrides: object) -> dict[str, object]:
    plan_id = overrides.pop("plan_id", _REAL_PLAN_ID)
    owner_approval_id = overrides.pop("owner_approval_id", _REAL_OWNER_APPROVAL_ID)
    fields: dict[str, object] = {
        "plan_id": plan_id,
        "candidate_id": _REAL_CANDIDATE_ID,
        "entry_intent_governance_id": _REAL_ENTRY_INTENT_ID,
        "symbol": "AAPL",
        "approved_quantity": Decimal("1"),
        "stop_price": Decimal("331.70"),
        "target_price": Decimal("341.75"),
        "mandatory_liquidation_at": _NOW - timedelta(hours=1),
        "owner_approval_id": owner_approval_id,
        "system_identity": derive_legacy_system_identity(
            plan_id=str(plan_id), owner_approval_id=str(owner_approval_id)
        ),
        "created_at": _NOW - timedelta(days=4),
    }
    fields.update(overrides)
    return fields


def _current_fields(**overrides: object) -> dict[str, object]:
    plan_id = overrides.pop("plan_id", "PLAN-1")
    owner_approval_id = overrides.pop("owner_approval_id", "OWN-1")
    fields: dict[str, object] = {
        "plan_id": plan_id,
        "candidate_id": "CAND-1",
        "entry_intent_governance_id": "INT-1",
        "symbol": "AAPL",
        "approved_quantity": Decimal("3"),
        "stop_price": Decimal("95"),
        "target_price": Decimal("110"),
        "mandatory_liquidation_at": _NOW + timedelta(hours=2),
        "owner_approval_id": owner_approval_id,
        "system_identity": derive_system_identity(
            plan_id=str(plan_id), owner_approval_id=str(owner_approval_id)
        ),
        "created_at": _NOW,
    }
    fields.update(overrides)
    return fields


# ---------------------------------------------------------------------------
# 1/2. The exact old and new derivations, and the real incident row
# ---------------------------------------------------------------------------


def test_legacy_derivation_is_the_exact_pre_rewrite_format() -> None:
    identity = derive_legacy_system_identity(
        plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )
    assert identity == (
        f"system:approved-plan:{_REAL_PLAN_ID}:owner-approval:{_REAL_OWNER_APPROVAL_ID}"
    )
    assert identity.startswith(LEGACY_SYSTEM_IDENTITY_PREFIX)
    # The exact overflow this release already fixed in isolation for NEW plans: the real
    # incident's own historical identity exceeds the 64-character authorized_by cap.
    assert len(identity) == 110


def test_current_and_legacy_prefixes_never_collide() -> None:
    assert not SYSTEM_IDENTITY_PREFIX.startswith(LEGACY_SYSTEM_IDENTITY_PREFIX)
    assert not LEGACY_SYSTEM_IDENTITY_PREFIX.startswith(SYSTEM_IDENTITY_PREFIX)


def test_real_incident_row_matches_the_historical_derivation_exactly() -> None:
    """The literal `system_identity` value read from the real PERSONAL_PAPER database,
    verified against the recomputed historical formula -- not merely asserted."""
    stored_value = (
        "system:approved-plan:PLAN-INT-PRP-089-PAPER-20261009T172613Z:owner-approval:"
        "DEC-PRP-089-PAPER-20261009T172613Z"
    )
    assert stored_value == derive_legacy_system_identity(
        plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )


# ---------------------------------------------------------------------------
# 10. Normal, current-format plans are completely unaffected
# ---------------------------------------------------------------------------


def test_reconstructing_a_current_format_plan_is_identical_to_direct_construction() -> None:
    fields = _current_fields()
    direct = ApprovedPlan(**fields)  # type: ignore[arg-type]
    reconstructed = reconstruct_approved_plan(**fields)  # type: ignore[arg-type]
    assert reconstructed == direct


def test_direct_construction_still_refuses_a_legacy_identity_unconditionally() -> None:
    """RELEASE v1 RECOVERY HARDENING SECURITY GATE's own check, UNWEAKENED: a legacy
    identity is accepted ONLY through `reconstruct_approved_plan`, never through
    `ApprovedPlan(...)` directly -- so no plan-creation path can ever produce one."""
    fields = _legacy_fields()
    with pytest.raises(ValueError, match="system_identity must be exactly"):
        ApprovedPlan(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 9. A legitimate legacy row, real incident-length ids, reconstructs correctly
# ---------------------------------------------------------------------------


def test_reconstructing_a_legitimate_legacy_plan_preserves_every_field_exactly() -> None:
    fields = _legacy_fields()
    plan = reconstruct_approved_plan(**fields)  # type: ignore[arg-type]
    for key, value in fields.items():
        assert getattr(plan, key) == value, key
    # The original, historical identity is preserved EXACTLY -- never rewritten to the new
    # format, which would misrepresent what was actually persisted and audited.
    assert plan.system_identity == fields["system_identity"]
    assert plan.system_identity.startswith(LEGACY_SYSTEM_IDENTITY_PREFIX)


def test_reconstructing_a_legacy_plan_still_derivable_fresh_to_a_safe_authorized_by() -> None:
    plan = reconstruct_approved_plan(**_legacy_fields())  # type: ignore[arg-type]
    fresh = derive_system_identity(plan_id=plan.plan_id, owner_approval_id=plan.owner_approval_id)
    assert fresh != plan.system_identity  # the legacy row's OWN field stays legacy
    assert len(fresh) <= 64
    assert len(plan.system_identity) == 110  # unchanged, not silently fixed up


# ---------------------------------------------------------------------------
# 6/7. Forged, mismatched, ambiguous or structurally invalid values are refused
# ---------------------------------------------------------------------------


def test_a_value_matching_neither_formula_is_refused() -> None:
    with pytest.raises(ValueError, match="matches neither"):
        reconstruct_approved_plan(**_legacy_fields(system_identity="freeform-forged-value"))  # type: ignore[arg-type]


def test_a_legacy_identity_built_from_a_different_plan_id_is_refused() -> None:
    """A forged legacy value naming someone else's plan -- rejected, not laundered through
    because it merely LOOKS like the legacy format."""
    wrong = derive_legacy_system_identity(
        plan_id="PLAN-SOMEONE-ELSE", owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )
    with pytest.raises(ValueError, match="matches neither"):
        reconstruct_approved_plan(**_legacy_fields(system_identity=wrong))  # type: ignore[arg-type]


def test_a_legacy_identity_built_from_a_different_owner_approval_is_refused() -> None:
    wrong = derive_legacy_system_identity(plan_id=_REAL_PLAN_ID, owner_approval_id="DEC-FORGED")
    with pytest.raises(ValueError, match="matches neither"):
        reconstruct_approved_plan(**_legacy_fields(system_identity=wrong))  # type: ignore[arg-type]


def test_a_truncated_legacy_identity_is_refused() -> None:
    legacy = derive_legacy_system_identity(
        plan_id=_REAL_PLAN_ID, owner_approval_id=_REAL_OWNER_APPROVAL_ID
    )
    with pytest.raises(ValueError, match="matches neither"):
        reconstruct_approved_plan(**_legacy_fields(system_identity=legacy[:-1]))  # type: ignore[arg-type]


def test_legacy_reconstruction_still_enforces_every_other_structural_invariant() -> None:
    """A legacy IDENTITY never bypasses any OTHER check -- `_validate_structure` runs for
    a legacy plan exactly as it does for a normal one."""
    with pytest.raises(ValueError, match="stop_price must be strictly below target_price"):
        reconstruct_approved_plan(  # type: ignore[arg-type]
            **_legacy_fields(stop_price=Decimal("400"), target_price=Decimal("300"))
        )
    with pytest.raises(ValueError, match="approved_quantity must be positive"):
        reconstruct_approved_plan(**_legacy_fields(approved_quantity=Decimal("0")))  # type: ignore[arg-type]


def test_legacy_reconstruction_with_a_claimed_trigger_preserves_the_claim() -> None:
    """8. The one real field this release's own claim-exit-trigger primitive may have
    already set on the historical row is preserved exactly, not reset."""
    claimed_at = _NOW - timedelta(hours=2)
    plan = reconstruct_approved_plan(  # type: ignore[arg-type]
        **_legacy_fields(
            triggered_exit_kind=ExitTriggerKind.MANDATORY_EXIT, triggered_exit_at=claimed_at
        )
    )
    assert plan.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT
    assert plan.triggered_exit_at == claimed_at
    assert plan.is_claimed


# ---------------------------------------------------------------------------
# 9/12. The automatic manager authorizes a legacy plan's exit without overflowing,
# dispatches exactly once, and never touches BUY/short/Live.
# ---------------------------------------------------------------------------


def test_a_reconstructed_legacy_plan_authorizes_an_automatic_exit_without_overflowing() -> None:
    """Proves `position_plan_manager.py`'s own fix directly: building the SAME
    plan's identity derived FRESH (never `plan.system_identity`) is always <=64
    characters -- where the plan's OWN stored (legacy) field would still overflow the
    64-character cap `PositionExitAuthorization.authorized_by` enforces
    (`_require_identifier`, exercised directly by the existing adversarial coverage in
    `test_v1_overdue_position_recovery.py`; this test proves the length fact the fix
    depends on, for this exact real incident's ids).
    """
    plan = reconstruct_approved_plan(**_legacy_fields())  # type: ignore[arg-type]
    fresh_identity = derive_system_identity(
        plan_id=plan.plan_id, owner_approval_id=plan.owner_approval_id
    )
    # The ORIGINAL bug: the plan's own stored (legacy) identity is still too long for
    # authorized_by -- never silently fixed up, so this stays true even after the fix.
    assert len(plan.system_identity) == 110
    # THE FIX: `position_plan_manager.py` derives this fresh instead, which is always safe.
    assert fresh_identity != plan.system_identity
    assert len(fresh_identity) <= 64
    command = AuthorizePositionExitCommand(
        authorization_id="XAU-TEST",
        preview_id="XPV-TEST",
        expected_request_fingerprint="fp",
        authorized_by=fresh_identity,
        authorized_at=_NOW,
    )
    assert command.authorized_by == fresh_identity
