"""RELEASE v1 -- an in-memory `ApprovedPlanRepository` fake, same discipline as the other
fakes in `_m085_fakes.py`: real invariants (the atomic claim), not a shortcut."""

from __future__ import annotations

import threading
from datetime import datetime

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.approved_plan_repositories import (
    ApprovedPlanAlreadyExistsError,
)


class FakeApprovedPlans:
    def __init__(self) -> None:
        self.rows: dict[str, ApprovedPlan] = {}
        self._lock = threading.Lock()

    def save(self, plan: ApprovedPlan) -> ApprovedPlan:
        with self._lock:
            if plan.plan_id in self.rows:
                raise ApprovedPlanAlreadyExistsError(f"plan {plan.plan_id!r} already exists")
            if any(
                p.entry_intent_governance_id == plan.entry_intent_governance_id
                for p in self.rows.values()
            ):
                raise ApprovedPlanAlreadyExistsError(
                    f"a plan already exists for entry {plan.entry_intent_governance_id!r}"
                )
            self.rows[plan.plan_id] = plan
            return plan

    def get(self, plan_id: str) -> ApprovedPlan | None:
        return self.rows.get(plan_id)

    def for_entry(self, entry_intent_governance_id: str) -> ApprovedPlan | None:
        for plan in self.rows.values():
            if plan.entry_intent_governance_id == entry_intent_governance_id:
                return plan
        return None

    def list_unclaimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        unclaimed = [p for p in self.rows.values() if not p.is_claimed]
        unclaimed.sort(key=lambda p: p.created_at)
        return tuple(unclaimed[:limit])

    def list_claimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        claimed = [p for p in self.rows.values() if p.is_claimed]
        claimed.sort(key=lambda p: p.triggered_exit_at or p.created_at)
        return tuple(claimed[:limit])

    def claim_exit_trigger(
        self, plan_id: str, *, kind: ExitTriggerKind, claimed_at: datetime
    ) -> ApprovedPlan | None:
        with self._lock:
            current = self.rows.get(plan_id)
            if current is None:
                raise ValueError(f"no plan {plan_id!r} exists")
            if current.is_claimed:
                return None
            claimed = ApprovedPlan(
                plan_id=current.plan_id,
                candidate_id=current.candidate_id,
                entry_intent_governance_id=current.entry_intent_governance_id,
                symbol=current.symbol,
                approved_quantity=current.approved_quantity,
                stop_price=current.stop_price,
                target_price=current.target_price,
                mandatory_liquidation_at=current.mandatory_liquidation_at,
                owner_approval_id=current.owner_approval_id,
                system_identity=current.system_identity,
                created_at=current.created_at,
                triggered_exit_kind=kind,
                triggered_exit_at=claimed_at,
            )
            self.rows[plan_id] = claimed
            return claimed
