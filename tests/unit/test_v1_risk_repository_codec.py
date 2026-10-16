"""Offline repository wire contract; PostgreSQL alone proves trigger/concurrency behavior."""

import json
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from tests.unit._m085_fakes import _NOW, a_configuration, a_preview, a_time_basis, an_intent
from tests.unit.test_postgres_evaluation_evidence_watermark_repository import _FakeService

from empirical_platform.decision_candidate.entry_risk_contract import EntryRiskContract
from empirical_platform.decision_candidate.paper_execution import (
    SubmissionPreview,
    authorize_submission,
    execution_policy_from_configuration,
)
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres_repositories import (
    paper_execution_repositories as repo,
)


def preview() -> SubmissionPreview:
    risk = EntryRiskContract(
        Decimal("4"), Decimal("3"), 1, 1, Decimal("5.123456789012345678"), Decimal("1")
    )
    config = replace(
        a_configuration(),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=risk.maximum_planned_loss_per_trade,
    )
    return a_preview(
        intent=an_intent(entry_risk=risk), policy=execution_policy_from_configuration(config)
    )


def wire() -> tuple[Any, dict[str, Any], list[str]]:
    row: dict[str, Any] = {}
    statements = []

    def script(statement: str, parameters: Mapping[str, object]) -> list[dict[str, Any]]:
        statements.append(statement)
        if statement.startswith("INSERT"):
            row.update(parameters)
            for field in ("risk_contract",):
                if isinstance(row.get(field), str):
                    row[field] = json.loads(row[field])
        if "MAX(preview_version)" in statement:
            return [{"highest": 3}]
        return [row.copy()] if row else []

    return _FakeService(script), row, statements


@pytest.mark.parametrize("modern", [False, True])
def test_preview_repository_preserves_exact_policy_and_approved_risk(modern: bool) -> None:
    service, row, statements = wire()
    repository = repo.PostgresSubmissionPreviewRepository(service)
    assert repository.get("missing") is None
    assert repository.latest_for_intent("missing") is None
    expected = preview() if modern else a_preview()
    assert repository.save(expected) == expected
    assert repository.get(expected.preview_id) == expected
    assert repository.latest_for_intent(expected.intent_governance_id) == expected
    assert repository.next_version_for_intent(expected.intent_governance_id) == 4
    assert "risk_contract" not in statements[-1], "aggregate query must not select row evidence"
    assert (
        row["risk_contract"] is None
        if not modern
        else row["risk_contract"]["entry"] == expected.entry_risk.document()
    )


@pytest.mark.parametrize("modern", [False, True])
def test_authorization_repository_preserves_owner_evidence(modern: bool) -> None:
    service, row, _ = wire()
    repository = repo.PostgresExecutionAuthorizationRepository(service)
    assert repository.get("missing") is None
    assert repository.latest_for_intent("missing") is None
    shown = preview() if modern else a_preview()
    expected = authorize_submission(
        preview=shown,
        authorization_id="AUTH-CODEC",
        authorized_by="owner",
        authorized_at=_NOW,
        validity_seconds=20,
        time_basis=a_time_basis(),
    )
    assert repository.save(expected) == expected
    assert repository.get(expected.authorization_id) == expected
    assert repository.latest_for_intent(expected.intent_governance_id) == expected
    if modern:
        assert row["risk_contract"]["maximum_planned_loss_per_trade"] == "5.123456789012345678"


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("quantity", "1"),
        ("limit_price", 4.0),
        ("extended_hours", "false"),
        ("preview_id", 123),
        ("created_at", "yesterday"),
        ("quote_bid", 3.0),
        ("quote_source", 123),
        ("market_next_close", "tomorrow"),
        ("refusals", "invalid JSON"),
        ("refusals", [1]),
        ("policy_watchlist", "AAPL"),
        ("policy_watchlist", [1]),
        ("earliest_entry_time", "09:30"),
        ("order_type", "UNKNOWN"),
        ("risk_contract", {"version": 1}),
    ],
)
def test_malformed_persisted_preview_refuses_instead_of_coercing(field: str, value: object) -> None:
    service, row, _ = wire()
    repository = repo.PostgresSubmissionPreviewRepository(service)
    repository.save(preview())
    row[field] = value
    with pytest.raises((FoundationError, ValueError, TypeError)):
        repository.get("preview")


@pytest.mark.parametrize(
    "change",
    [
        {"stop_price": "2", "planned_loss": "2"},
        {"quantity": 2, "planned_loss": "2"},
        {"entry_ceiling": "5", "planned_loss": "2"},
    ],
)
def test_changed_persisted_risk_does_not_reuse_preview_binding(change: dict[str, object]) -> None:
    service, row, _ = wire()
    repository = repo.PostgresSubmissionPreviewRepository(service)
    repository.save(preview())
    row["risk_contract"]["entry"].update(change)
    with pytest.raises((FoundationError, ValueError)):
        repository.get("preview")
