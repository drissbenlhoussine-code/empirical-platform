"""RELEASE v1 -- the Owner's one durable approval of a complete trade plan.

WHAT THIS IS. Release Blocker 2 requires ONE Owner approval to durably authorize BOTH a
bounded PAPER entry AND the future, automatic, position-reducing exits (stop, target,
mandatory liquidation) that follow it -- without asking the Owner to approve those exits
again. `ApprovedPlan` is the durable record of exactly those frozen terms: it is written
once, at approval time, and never mutated except for the ONE atomic exit-trigger claim
(`triggered_exit_kind`) described below.

WHAT IT DOES NOT DO. This module never calls a broker, never reads a clock, and never
decides anything about the LIVE market. It is pure data plus pure decision functions, the
same discipline `operator_trading_configuration.py` and `trade_proposal.py` already use:
the automatic position-plan manager (`usecases/position_plan_manager.py`) supplies fresh
evidence and calls `evaluate_exit_trigger` to get an answer; this module never fetches
that evidence itself.

THE SYSTEM IDENTITY IS NOT A LOOPHOLE. The automatic manager must authorize an exit
through the SAME `AuthorizePositionExitHandler`/`SubmitAuthorizedPositionExitHandler`
chain a human uses, which requires an `authorized_by` identity. `derive_system_identity`
produces a stable string that deterministically traces back to the ONE Owner approval
that created this plan (`plan_id` + the Owner's own approval identity, never freeform
text) -- it authorizes nothing beyond the exits this exact plan already named, and it
cannot be constructed without an existing plan and an existing Owner approval id.

EXACTLY ONE EXIT TRIGGER MAY WIN (exit-collision safety). Stop, target and mandatory-exit
conditions are evaluated independently and may become true in the same evaluation tick.
`triggered_exit_kind` is a single nullable column claimed via the SAME conditional
`UPDATE ... WHERE triggered_exit_kind IS NULL` pattern `claim_dispatch` already proves
exactly-once for order dispatch elsewhere in this codebase (see
`ApprovedPlanRepository.claim_exit_trigger`). A trigger that loses the claim must treat
that as `EXIT_ALREADY_CLAIMED` and submit nothing -- it never resubmits "just in case" and
never overwrites a prior claim. The existing exit pipeline's own `exit_eligibility` (an
exit is refused while another is in progress) and `claim_dispatch` (at most one active
exit attempt per position) are a second, independent layer of the same guarantee: even if
two callers raced past the plan-level claim somehow, the exit-attempt table itself cannot
hold two active attempts for the same entry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "LEGACY_SYSTEM_IDENTITY_PREFIX",
    "SYSTEM_IDENTITY_PREFIX",
    "ApprovedPlan",
    "ExitTriggerKind",
    "derive_legacy_system_identity",
    "derive_system_identity",
    "evaluate_exit_trigger",
    "reconstruct_approved_plan",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64

#: How long before `mandatory_liquidation_at` the automatic manager must already have
#: submitted the mandatory exit. Matches the documented safety-buffer requirement in the
#: release mission ("Use a documented safety buffer before regular-session close"). Chosen
#: so a plan evaluated on the manager's own poll interval (see
#: `position_plan_manager.DEFAULT_POLL_INTERVAL_SECONDS`, 15s) has many evaluation
#: opportunities to submit before the hard deadline even under broker/network delay.
MANDATORY_EXIT_SAFETY_BUFFER_SECONDS = 120


class ExitTriggerKind(StrEnum):
    """Which of the three pre-approved exit conditions fired. Never a fourth value."""

    STOP = "STOP"
    TARGET = "TARGET"
    MANDATORY_EXIT = "MANDATORY_EXIT"


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


#: RELEASE v1 RECOVERY HARDENING SECURITY GATE (isolated fix). The fixed marker on every
#: `authorized_by` the automatic manager ever derives -- and the ONLY thing a caller may
#: trust to recognize one (see `usecases.position_exit.AuthorizePositionExitHandler`'s own
#: reserved-prefix refusal, which keys off `position_exit.OVERDUE_RECOVERY_AUTHORIZED_BY_
#: PREFIX`, a sibling, never-colliding reserved prefix, the same way).
SYSTEM_IDENTITY_PREFIX = "system-approved-plan:"


def derive_system_identity(*, plan_id: str, owner_approval_id: str) -> str:
    """The ONLY `authorized_by` string the automatic manager may ever use.

    Deterministic, not generated: the same `(plan_id, owner_approval_id)` always produces
    the same identity, so the audit trail can always be walked back to the one human
    approval that authorized it. It is never accepted as a human `authorized_by` value for
    a MANUAL exit -- `PositionExitConsole.confirm` never exposes `authorized_by` to a
    caller at all, always using its own fixed `operator_identity`.

    ISOLATED SECURITY-GATE FIX. Previously this concatenated `plan_id` and
    `owner_approval_id` in the open (`f"system:approved-plan:{plan_id}:owner-approval:
    {owner_approval_id}"`), which could, and for a real incident's own governance ids
    DID, exceed the 64-character limit `PositionExitAuthorization.authorized_by` enforces
    (`__post_init__`'s `_require_identifier`) -- `ValueError` the instant the automatic
    manager tried to save the authorization, entirely independent of any deadline logic.
    Hashing rather than concatenating cannot overflow it, for any input length this
    function already accepts (each bounded at 64 characters by `_require_identifier`
    below). The function's own contract -- deterministic, traceable to exactly one
    `(plan_id, owner_approval_id)` pair, never freeform -- is unchanged; only the
    representation is. Nothing parses the old concatenated format anywhere in this
    codebase (`system_identity` is always compared for equality, never destructured), so
    this change is safe to make in isolation.
    """
    _require_identifier(plan_id, field="plan_id")
    _require_identifier(owner_approval_id, field="owner_approval_id")
    material = f"{plan_id}|{owner_approval_id}"
    return SYSTEM_IDENTITY_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


#: RELEASE v1 LEGACY APPROVED PLAN IDENTITY COMPATIBILITY. The PRE-security-gate format
#: `derive_system_identity` produced before the hash-based rewrite above -- preserved here,
#: unchanged, ONLY so an already-persisted row written under that format can be recognized
#: and read. Never used to derive a NEW plan's identity anywhere in this codebase; see
#: `reconstruct_approved_plan`'s own docstring for the one place this is read.
LEGACY_SYSTEM_IDENTITY_PREFIX = "system:approved-plan:"


def derive_legacy_system_identity(*, plan_id: str, owner_approval_id: str) -> str:
    """The historical (pre-security-gate) `system_identity` format, for verifying an
    already-persisted row ONLY -- never for deriving a new plan's identity.

    This is the exact formula `derive_system_identity` used before the hash-based rewrite:
    a literal concatenation, which is why it could (and for this real incident's own
    governance ids, did) exceed the 64-character limit `authorized_by` enforces. Kept
    byte-for-byte so `reconstruct_approved_plan` can recompute it and compare for an exact
    match -- the same input validation `derive_system_identity` itself applies, so this
    cannot be satisfied by a forged, truncated or freeform string either.
    """
    _require_identifier(plan_id, field="plan_id")
    _require_identifier(owner_approval_id, field="owner_approval_id")
    return f"{LEGACY_SYSTEM_IDENTITY_PREFIX}{plan_id}:owner-approval:{owner_approval_id}"


@dataclass(frozen=True, slots=True)
class ApprovedPlan:
    """The complete, immutable terms the Owner approved in ONE action.

    Everything except `triggered_exit_kind`/`triggered_exit_at` is write-once at approval
    time. Those two fields are the one deliberate, atomically-claimed mutation this record
    ever undergoes -- see the module docstring.
    """

    plan_id: str
    candidate_id: str
    entry_intent_governance_id: str
    symbol: str
    approved_quantity: Decimal
    stop_price: Decimal
    target_price: Decimal
    mandatory_liquidation_at: datetime
    owner_approval_id: str
    system_identity: str
    created_at: datetime
    triggered_exit_kind: ExitTriggerKind | None = None
    triggered_exit_at: datetime | None = None
    #: FORENSIC AUDIT FOLLOW-UP (2026-10-20 early-STOP incident): the quote that drove a
    #: STOP/TARGET claim, so a future incident is reconstructible from this row alone
    #: instead of needing to pull the broker's historical quotes after the fact. Always
    #: NULL together (see `_validate_structure`); never set for MANDATORY_EXIT, which
    #: fires on time alone and never consults a quote.
    triggered_exit_quote_bid: Decimal | None = None
    triggered_exit_quote_ask: Decimal | None = None
    triggered_exit_quote_captured_at: datetime | None = None
    triggered_exit_quote_source: str | None = None

    def __post_init__(self) -> None:
        self._validate_structure()
        self._validate_identity()

    def _validate_structure(self) -> None:
        """Every invariant EXCEPT the identity check -- shared, unchanged, by both a
        normal construction (`__post_init__`, below) and `reconstruct_approved_plan`'s
        legacy-identity path, so a legacy row is held to exactly the same structural
        standard as any other plan."""
        _require_identifier(self.plan_id, field="plan_id")
        _require_identifier(self.candidate_id, field="candidate_id")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        _require_identifier(self.symbol, field="symbol")
        _require_identifier(self.owner_approval_id, field="owner_approval_id")
        if self.approved_quantity <= 0:
            raise ValueError("approved_quantity must be positive")
        if self.stop_price <= 0 or self.target_price <= 0:
            raise ValueError("stop_price and target_price must be positive")
        if self.stop_price >= self.target_price:
            raise ValueError(
                "stop_price must be strictly below target_price (long-only full close)"
            )
        if (self.triggered_exit_kind is None) != (self.triggered_exit_at is None):
            raise ValueError(
                "triggered_exit_kind and triggered_exit_at must be set, or unset, together"
            )
        quote_fields = (
            self.triggered_exit_quote_bid,
            self.triggered_exit_quote_ask,
            self.triggered_exit_quote_captured_at,
            self.triggered_exit_quote_source,
        )
        if any(f is None for f in quote_fields) and any(f is not None for f in quote_fields):
            raise ValueError(
                "triggered_exit_quote_bid/ask/captured_at/source must be set, or unset, together"
            )
        if self.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT and any(
            f is not None for f in quote_fields
        ):
            raise ValueError(
                "quote evidence may only be set for a STOP/TARGET claim; "
                "MANDATORY_EXIT never consults a quote"
            )

    def _validate_identity(self) -> None:
        """UNCHANGED, unweakened: the ONLY identity a normal construction ever accepts is
        the CURRENT `derive_system_identity(...)` format. Every plan-creation path
        (`usecases/full_plan_approval.py`) constructs `ApprovedPlan(...)` directly, so this
        runs for every new plan exactly as it always has. A legacy row never reaches this
        method at all -- see `reconstruct_approved_plan`."""
        expected_identity = derive_system_identity(
            plan_id=self.plan_id, owner_approval_id=self.owner_approval_id
        )
        if self.system_identity != expected_identity:
            raise ValueError(
                "system_identity must be exactly derive_system_identity(plan_id, "
                "owner_approval_id); a plan can never carry a freeform or mismatched identity"
            )

    @property
    def is_claimed(self) -> bool:
        return self.triggered_exit_kind is not None

    @property
    def mandatory_exit_deadline(self) -> datetime:
        """When the automatic manager must have ALREADY submitted the mandatory exit."""
        return self.mandatory_liquidation_at - timedelta(
            seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS
        )


def reconstruct_approved_plan(
    *,
    plan_id: str,
    candidate_id: str,
    entry_intent_governance_id: str,
    symbol: str,
    approved_quantity: Decimal,
    stop_price: Decimal,
    target_price: Decimal,
    mandatory_liquidation_at: datetime,
    owner_approval_id: str,
    system_identity: str,
    created_at: datetime,
    triggered_exit_kind: ExitTriggerKind | None = None,
    triggered_exit_at: datetime | None = None,
    triggered_exit_quote_bid: Decimal | None = None,
    triggered_exit_quote_ask: Decimal | None = None,
    triggered_exit_quote_captured_at: datetime | None = None,
    triggered_exit_quote_source: str | None = None,
) -> ApprovedPlan:
    """Reconstruct an `ApprovedPlan` from an ALREADY-PERSISTED row -- the ONE place a
    pre-hash-rewrite (legacy) `system_identity` is ever accepted for reading.

    RELEASE v1 LEGACY APPROVED PLAN IDENTITY COMPATIBILITY. The hash-based
    `derive_system_identity` rewrite changed the identity FORMAT, but a plan approved
    before that rewrite still carries the OLD format in storage -- `ApprovedPlan(...)`
    itself (every creation path) still refuses that unconditionally, which is correct and
    unchanged, but it also made every READ of that one real, historical, already-approved
    plan raise, with no way to load it at all.

    This function tries the CURRENT format first (`ApprovedPlan(...)` directly -- the
    identical path and identical check every plan has always gone through: nothing here
    weakens it, and the overwhelming majority of calls, every plan approved after the
    rewrite, take exactly this branch). Only if that fails does it check whether
    `system_identity` matches the HISTORICAL formula
    (`derive_legacy_system_identity(plan_id, owner_approval_id)`) EXACTLY -- not a prefix,
    not a fuzzy match. A value that matches neither is rejected exactly as before: forged,
    truncated, freeform or otherwise mismatched identities are never accepted, legacy or
    not. A verified legacy row is reconstructed with every field EXACTLY as persisted
    (including `system_identity` itself, unrewritten -- the original Owner approval,
    deadline, trigger claim and execution evidence are never touched) and is still run
    through `_validate_structure()`, the SAME non-identity checks every other plan must
    satisfy.

    NEVER used by a plan-creation path: `usecases/full_plan_approval.py` constructs
    `ApprovedPlan(...)` directly and always derives a fresh, current-format identity, so a
    brand-new plan can never carry a legacy identity. This function is called ONLY from
    the Postgres repository's own row-to-domain conversion (`_row_to_plan`).

    THE CONSEQUENCE FOR AUTOMATIC EXITS. A legacy plan's own `system_identity` is still the
    oversized historical string (the original, independent 64-character `authorized_by`
    overflow this release already fixed in isolation) -- `position_plan_manager.py`
    therefore derives `authorized_by` fresh via `derive_system_identity(plan_id=...,
    owner_approval_id=...)` rather than trusting the plan's own (possibly legacy) stored
    field, which is always the safe, current, <=64-character form regardless of which
    format this plan happens to carry.
    """
    current_identity = derive_system_identity(plan_id=plan_id, owner_approval_id=owner_approval_id)
    if system_identity == current_identity:
        return ApprovedPlan(
            plan_id=plan_id,
            candidate_id=candidate_id,
            entry_intent_governance_id=entry_intent_governance_id,
            symbol=symbol,
            approved_quantity=approved_quantity,
            stop_price=stop_price,
            target_price=target_price,
            mandatory_liquidation_at=mandatory_liquidation_at,
            owner_approval_id=owner_approval_id,
            system_identity=system_identity,
            created_at=created_at,
            triggered_exit_kind=triggered_exit_kind,
            triggered_exit_at=triggered_exit_at,
            triggered_exit_quote_bid=triggered_exit_quote_bid,
            triggered_exit_quote_ask=triggered_exit_quote_ask,
            triggered_exit_quote_captured_at=triggered_exit_quote_captured_at,
            triggered_exit_quote_source=triggered_exit_quote_source,
        )
    legacy_identity = derive_legacy_system_identity(
        plan_id=plan_id, owner_approval_id=owner_approval_id
    )
    if system_identity != legacy_identity:
        raise ValueError(
            "system_identity matches neither the current derive_system_identity(plan_id, "
            "owner_approval_id) nor the historical derive_legacy_system_identity(plan_id, "
            "owner_approval_id) formula; a plan can never carry a freeform, forged or "
            "ambiguous identity"
        )
    plan = object.__new__(ApprovedPlan)
    object.__setattr__(plan, "plan_id", plan_id)
    object.__setattr__(plan, "candidate_id", candidate_id)
    object.__setattr__(plan, "entry_intent_governance_id", entry_intent_governance_id)
    object.__setattr__(plan, "symbol", symbol)
    object.__setattr__(plan, "approved_quantity", approved_quantity)
    object.__setattr__(plan, "stop_price", stop_price)
    object.__setattr__(plan, "target_price", target_price)
    object.__setattr__(plan, "mandatory_liquidation_at", mandatory_liquidation_at)
    object.__setattr__(plan, "owner_approval_id", owner_approval_id)
    object.__setattr__(plan, "system_identity", system_identity)
    object.__setattr__(plan, "created_at", created_at)
    object.__setattr__(plan, "triggered_exit_kind", triggered_exit_kind)
    object.__setattr__(plan, "triggered_exit_at", triggered_exit_at)
    object.__setattr__(plan, "triggered_exit_quote_bid", triggered_exit_quote_bid)
    object.__setattr__(plan, "triggered_exit_quote_ask", triggered_exit_quote_ask)
    object.__setattr__(plan, "triggered_exit_quote_captured_at", triggered_exit_quote_captured_at)
    object.__setattr__(plan, "triggered_exit_quote_source", triggered_exit_quote_source)
    plan._validate_structure()
    return plan


def evaluate_exit_trigger(
    plan: ApprovedPlan, *, last_price: Decimal, now: datetime
) -> ExitTriggerKind | None:
    """Pure decision: which exit condition, if any, has been reached right now.

    Priority when more than one condition is simultaneously true: STOP, then TARGET, then
    MANDATORY_EXIT. A long-only plan's `stop_price < target_price` invariant means price
    cannot satisfy both the stop and target conditions at once, so this ordering only ever
    matters between a price trigger and the independent time-based mandatory-exit trigger;
    STOP is given priority there too, because a price that has already crossed the stop is
    the more urgent risk-bounding fact. This function never widens `stop_price` or
    `target_price` and never looks at anything the plan did not already freeze.
    """
    if plan.is_claimed:
        return None
    if last_price <= plan.stop_price:
        return ExitTriggerKind.STOP
    if last_price >= plan.target_price:
        return ExitTriggerKind.TARGET
    if now >= plan.mandatory_exit_deadline:
        return ExitTriggerKind.MANDATORY_EXIT
    return None
