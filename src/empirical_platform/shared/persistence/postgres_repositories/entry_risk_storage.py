"""Additive risk-v2 SQL/JSON codec. Absence is preserved only as historical evidence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from empirical_platform.decision_candidate.paper_execution import SubmissionPreview

from empirical_platform.decision_candidate.entry_risk_contract import EntryRiskContract


def encode_risk(risk: EntryRiskContract | None) -> str | None:
    return None if risk is None else json.dumps(risk.document(), sort_keys=True)


def risk_insert(statement: str, payload: str | None) -> str:
    if payload is None:
        return statement
    # Statements are repository-owned constants, never caller SQL or identifiers.
    before, values = (
        statement.split(" VALUES ", 1) if " VALUES " in statement else statement.split("VALUES ", 1)
    )
    before = before.rstrip()
    assert before.endswith(")")
    values_part, returning = values.split("RETURNING ", 1)
    values_part = values_part.rstrip()
    assert values_part.endswith(")")
    return (
        before[:-1]
        + ", risk_contract) VALUES "
        + values_part[:-1]
        + ", CAST(:risk_contract AS jsonb)) RETURNING "
        + returning
    )


def configuration_risk(row: dict[str, Any]) -> dict[str, Any]:
    risk = row.get("risk_contract")
    if risk is None:
        return {}
    if type(risk.get("version")) is not int or risk.get("version") != 2:
        raise ValueError("invalid stored risk configuration version")
    if not isinstance(risk.get("maximum_planned_loss_per_trade"), str):
        raise ValueError("stored loss cap must be an exact decimal string")
    from decimal import Decimal

    return {
        "risk_contract_version": 2,
        "maximum_position_quantity_shares": risk["maximum_position_quantity_shares"],
        "maximum_planned_loss_per_trade": Decimal(risk["maximum_planned_loss_per_trade"]),
    }


def preview_risk(preview: SubmissionPreview) -> str | None:
    if preview.policy.risk_contract_version == 1 and preview.entry_risk is None:
        return None
    return json.dumps(
        {
            "version": 2,
            "maximum_position_quantity_shares": preview.policy.maximum_position_quantity_shares,
            "maximum_planned_loss_per_trade": str(preview.policy.maximum_planned_loss_per_trade),
            "entry": None if preview.entry_risk is None else preview.entry_risk.document(),
        },
        sort_keys=True,
    )
