"""Real additive upgrade and immutable risk evidence, on isolated TEST databases only."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from tests.integration._m085_support import (
    CHAIN_AT,
    EVALUATED_AT,
    a_basis_at,
    a_configuration,
    a_context,
    a_proposal,
    alembic_config,
    build_engine,
    chain_clock,
    config,
)
from tests.unit._m085_fakes import a_preview, an_account

from empirical_platform.decision_candidate.operator_trading_configuration import (
    configuration_fingerprint,
)
from empirical_platform.decision_candidate.paper_execution import (
    authorize_submission,
    execution_policy_from_configuration,
)
from empirical_platform.decision_candidate.trade_approval import (
    OperatorAction,
    build_approved_order_intent,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    V1_INTEGRATED_SCHEMA_HEAD,
    PostgresPaperExecutionRuntime,
    require_v1_integrated_schema_compatibility,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.decision_to_approval import (
    SaveOperatorTradingConfigurationCommand,
    SaveOperatorTradingConfigurationHandler,
)
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError, _policy_for


@pytest.fixture
def engine() -> Iterator[Engine]:
    yield from build_engine("b9f2c4d6" + "a8e1")


def test_upgrade_and_full_risk_round_trip(engine: Engine) -> None:
    service = PostgresPersistenceService(config())
    service.initialize()
    runtime = PostgresRepositoryRuntime(service)
    paper = PostgresPaperExecutionRuntime(service)
    try:
        legacy = a_configuration(configuration_governance_id="CFG-HISTORICAL")
        runtime.operator_trading_configurations.save(legacy)
        legacy_digest = configuration_fingerprint(legacy)
        command.upgrade(alembic_config(), "head")
        assert require_v1_integrated_schema_compatibility(service) == V1_INTEGRATED_SCHEMA_HEAD
        historical = runtime.operator_trading_configurations.get("CFG-HISTORICAL", 1)
        assert historical == legacy and configuration_fingerprint(historical) == legacy_digest
        assert (
            historical.risk_contract_version == 1
            and historical.maximum_planned_loss_per_trade is None
        )
        governed = replace(
            a_configuration(),
            risk_contract_version=2,
            maximum_position_quantity_shares=1,
            maximum_planned_loss_per_trade=Decimal("5.123456789012345678"),
        )
        stored = SaveOperatorTradingConfigurationHandler(
            configuration_repository=runtime.operator_trading_configurations
        ).handle(SaveOperatorTradingConfigurationCommand(governed))
        assert stored == governed and configuration_fingerprint(
            stored
        ) == configuration_fingerprint(governed)
        context = a_context(runtime, stored)
        runtime.evaluation_contexts.save(context)
        proposal = a_proposal(stored, context)
        saved = runtime.trade_proposals.save(proposal)
        assert saved == proposal and saved.entry_risk is not None
        decision = record_operator_decision(
            proposal=saved,
            decision_governance_id="DEC-RISK",
            action=OperatorAction.APPROVE,
            operator_identity="owner",
            decided_at=EVALUATED_AT + timedelta(seconds=10),
            approval_expiry_seconds=120,
        )
        runtime.approval_decisions.record(decision)
        approved = runtime.trade_proposals.set_status(
            saved.proposal_governance_id, ProposalStatus.APPROVED
        )
        intent = build_approved_order_intent(
            intent_governance_id="INT-RISK",
            proposal=approved,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-RISK",
        )
        persisted = runtime.approved_order_intents.issue(intent)
        assert persisted == intent and persisted.entry_risk == proposal.entry_risk
        account = an_account(captured_at=CHAIN_AT)
        paper.paper_account_snapshots.save(account)
        preview = a_preview(
            intent=persisted,
            account=account,
            policy=execution_policy_from_configuration(stored),
            created_at=CHAIN_AT,
            broker_now=chain_clock(),
            quote_captured_at=CHAIN_AT,
            market_next_close=EVALUATED_AT + timedelta(hours=2),
        )
        assert preview.is_authorizable, preview.refusals
        assert paper.submission_previews.save(preview) == preview
        auth = authorize_submission(
            preview=preview,
            authorization_id="AUTH-RISK",
            authorized_by="owner",
            authorized_at=CHAIN_AT,
            validity_seconds=20,
            time_basis=a_basis_at(CHAIN_AT),
        )
        assert paper.execution_authorizations.save(auth) == auth
        assert paper.execution_authorizations.get("AUTH-RISK").entry_risk == proposal.entry_risk
        assert runtime.operator_trading_configurations.requires_current_risk_contract
        legacy_intent = replace(
            persisted, configuration_governance_id="CFG-HISTORICAL", entry_risk=None
        )
        with pytest.raises(PaperExecutionRefusedError, match="legacy"):
            _policy_for(legacy_intent, runtime.operator_trading_configurations)
        for table, key, value in [
            (
                "operator_trading_configuration",
                "configuration_governance_id",
                governed.configuration_governance_id,
            ),
            ("trade_proposal", "proposal_governance_id", proposal.proposal_governance_id),
            ("approved_order_intent", "intent_governance_id", intent.intent_governance_id),
            ("paper_submission_preview", "preview_id", preview.preview_id),
            ("paper_execution_authorization", "authorization_id", auth.authorization_id),
        ]:
            with pytest.raises(DBAPIError), engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE public.{table} SET risk_contract=NULL WHERE {key}=:value"),  # noqa: S608 - fixed test table/key allowlist
                    {"value": value},
                )
    finally:
        service.close()
