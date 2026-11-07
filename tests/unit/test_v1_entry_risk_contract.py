"""Adversarial v1 quantity/loss contract; real broker access is never used."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from tests.unit._m085_fakes import _NOW, a_preview, a_time_basis, an_intent
from tests.unit.test_m084_domain_core import a_configuration, a_variant, evaluate

from empirical_platform.decision_candidate.entry_risk_contract import EntryRiskContract, read_risk
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
    configuration_fingerprint,
)
from empirical_platform.decision_candidate.paper_execution import (
    authorization_binding_refusal,
    authorize_submission,
    entry_risk_refusal,
    execution_policy_from_configuration,
)
from empirical_platform.decision_candidate.trade_proposal import compute_fingerprint
from empirical_platform.usecases.decision_to_approval_io import (
    read_configuration,
    render_configuration_json,
)


def config(**changes: object) -> OperatorTradingConfiguration:
    return replace(
        a_configuration(),
        risk_contract_version=2,
        maximum_position_quantity_shares=changes.pop("maximum_position_quantity_shares", 1),
        maximum_planned_loss_per_trade=changes.pop("maximum_planned_loss_per_trade", Decimal("5")),
        **changes,
    )


def risk(**changes: object) -> EntryRiskContract:
    values = dict(
        entry_ceiling=Decimal("100"),
        stop_price=Decimal("95"),
        quantity=1,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("5"),
        planned_loss=Decimal("5"),
    )
    values.update(changes)
    return EntryRiskContract(**values)


@pytest.mark.parametrize("quantity,cap", [(1, 2), (1, 1), (2, 2)])
def test_quantity_below_and_at_cap(quantity: int, cap: int) -> None:
    assert (
        risk(
            quantity=quantity,
            maximum_position_quantity_shares=cap,
            stop_price=Decimal("99"),
            planned_loss=Decimal(quantity),
        ).quantity
        == quantity
    )


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": 2},
        {"quantity": 0},
        {"quantity": True},
        {"stop_price": Decimal("94.99"), "planned_loss": Decimal("5.01")},
        {"entry_ceiling": Decimal("100.01"), "planned_loss": Decimal("5.01")},
        {"stop_price": Decimal("100"), "planned_loss": Decimal("0")},
        {"entry_ceiling": Decimal("NaN")},
        {"planned_loss": Decimal("4.99")},
        {"maximum_planned_loss_per_trade": Decimal("Infinity")},
        {"maximum_position_quantity_shares": False},
    ],
)
def test_invalid_or_excess_risk_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        risk(**change)


@pytest.mark.parametrize("loss", [Decimal("0.01"), Decimal("4.99"), Decimal("5")])
def test_loss_below_and_exact_cap(loss: Decimal) -> None:
    assert risk(stop_price=Decimal("100") - loss, planned_loss=loss).planned_loss == loss


def test_sizing_uses_share_cap_and_preserves_loss_evidence() -> None:
    proposal = evaluate(configuration=config()).proposal
    assert proposal is not None and proposal.quantity == 1
    assert proposal.entry_risk is not None
    assert (
        proposal.entry_risk.planned_loss
        == (proposal.limit_price - proposal.stop_loss_price) * proposal.quantity
    )


def test_planned_loss_above_cap_refuses_proposal() -> None:
    outcome = evaluate(configuration=config(maximum_planned_loss_per_trade=Decimal("0.01")))
    assert outcome.proposal is None
    assert any(c.check_id == "planned_loss" for c in outcome.risk_checks)


def test_notional_and_daily_loss_remain_independent() -> None:
    assert evaluate(configuration=config(maximum_capital_per_trade=Decimal("1"))).proposal is None
    from tests.unit.test_m084_domain_core import an_account

    assert (
        evaluate(
            configuration=config(), account=an_account(realized_pnl_today=Decimal("-500"))
        ).proposal
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [{"maximum_position_quantity_shares": 2}, {"maximum_planned_loss_per_trade": Decimal("4.99")}],
)
def test_configuration_fingerprint_binds_each_cap(changes: dict[str, Any]) -> None:
    assert configuration_fingerprint(config()) != configuration_fingerprint(config(**changes))


def test_exact_decimal_json_round_trip() -> None:
    c = config(maximum_planned_loss_per_trade=Decimal("4.123456789012345678"))
    assert read_configuration(render_configuration_json(c)) == c
    assert configuration_fingerprint(
        replace(c, maximum_planned_loss_per_trade=Decimal("4.1234567890123456780"))
    ) == configuration_fingerprint(c)
    assert read_risk(risk().document()) == risk()


def test_legacy_is_not_upgraded_by_reading() -> None:
    old = a_configuration()
    assert read_configuration(render_configuration_json(old)) == old
    assert old.risk_contract_version == 1 and old.maximum_planned_loss_per_trade is None
    assert read_risk(None) is None
    assert (
        entry_risk_refusal(an_intent(), execution_policy_from_configuration(config())) is not None
    )


@pytest.mark.parametrize("changes", [{"stop_loss_price": Decimal("1")}, {"quantity": 2}])
def test_proposal_fingerprint_changes_with_approved_terms(changes: dict[str, Any]) -> None:
    proposal = evaluate(configuration=config()).proposal
    assert proposal is not None
    changed = a_variant(proposal, **changes)
    assert compute_fingerprint(changed) != proposal.content_fingerprint


def test_preview_authorization_carries_same_stop_and_risk() -> None:
    from tests.unit._m085_fakes import a_configuration as send_config

    policy = execution_policy_from_configuration(
        replace(
            send_config(),
            risk_contract_version=2,
            maximum_position_quantity_shares=1,
            maximum_planned_loss_per_trade=Decimal("5"),
            maximum_capital_per_trade=Decimal("500"),
        )
    )
    intent = an_intent(limit_price=Decimal("100"), entry_risk=risk())
    preview = a_preview(intent=intent, policy=policy)
    assert preview.is_authorizable
    authorization = authorize_submission(
        preview=preview,
        authorization_id="AUTH-RISK",
        authorized_by="owner",
        authorized_at=_NOW,
        validity_seconds=20,
        time_basis=a_time_basis(),
    )
    assert authorization.entry_risk == intent.entry_risk
    changed = replace(
        authorization, entry_risk=risk(stop_price=Decimal("96"), planned_loss=Decimal("4"))
    )
    assert authorization_binding_refusal(authorization=changed, preview=preview) is not None


def test_valid_v2_dispatch_uses_only_fake_broker() -> None:
    from freezegun import freeze_time
    from tests.unit._m085_fakes import (
        FakeConfigurations,
        FakeIntents,
    )
    from tests.unit._m085_fakes import (
        a_configuration as send_config,
    )
    from tests.unit.test_m085_paper_execution_handlers import TestSubmitAuthorizedPaperOrder

    harness = TestSubmitAuthorizedPaperOrder()
    approved_risk = EntryRiskContract(Decimal("4"), Decimal("3"), 1, 1, Decimal("5"), Decimal("1"))
    configuration = replace(
        send_config(),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("5"),
    )
    world = harness._world(
        intents=FakeIntents(an_intent(entry_risk=approved_risk)),
        configurations=FakeConfigurations(configuration),
    )
    with freeze_time(_NOW):
        harness._authorize(world)
        harness._handler(world).handle(harness._command())
    assert len(world["broker"].submitted) == 1


@pytest.mark.parametrize("changed", ["stop", "entry", "quantity", "legacy"])
def test_changed_terms_refused_before_fake_broker_write(changed: str) -> None:
    import copy

    from freezegun import freeze_time
    from tests.unit._m085_fakes import (
        FakeConfigurations,
        FakeIntents,
    )
    from tests.unit._m085_fakes import (
        a_configuration as send_config,
    )
    from tests.unit.test_m085_paper_execution_handlers import TestSubmitAuthorizedPaperOrder

    from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError

    harness = TestSubmitAuthorizedPaperOrder()
    approved_risk = EntryRiskContract(Decimal("4"), Decimal("3"), 1, 1, Decimal("5"), Decimal("1"))
    configuration = replace(
        send_config(),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("5"),
    )
    intent = an_intent(entry_risk=approved_risk)
    world = harness._world(
        intents=FakeIntents(intent), configurations=FakeConfigurations(configuration)
    )
    with freeze_time(_NOW):
        harness._authorize(world)
        hostile = copy.copy(intent)
        if changed == "legacy":
            object.__setattr__(hostile, "entry_risk", None)
        else:
            altered = copy.copy(approved_risk)
            if changed == "stop":
                object.__setattr__(altered, "stop_price", Decimal("2"))
            elif changed == "entry":
                object.__setattr__(hostile, "limit_price", Decimal("10"))
            else:
                object.__setattr__(hostile, "quantity", 2)
            object.__setattr__(hostile, "entry_risk", altered)
        world["intents"] = FakeIntents(hostile)
        with pytest.raises((PaperExecutionRefusedError, ValueError)):
            harness._handler(world).handle(harness._command())
    assert world["broker"].submitted == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_position_quantity_shares", 0),
        ("maximum_position_quantity_shares", 1.0),
        ("maximum_planned_loss_per_trade", 5.0),
        ("maximum_planned_loss_per_trade", Decimal("0")),
    ],
)
def test_configuration_rejects_ambiguous_limits(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        config(**{field: value})


def test_risk_arithmetic_ignores_ambient_decimal_precision() -> None:
    from decimal import localcontext

    from empirical_platform.decision_candidate.entry_risk_contract import planned_loss

    entry = Decimal("100.12345678901234567890123456789")
    stop = Decimal("99.00000000000000000000000000001")
    with localcontext() as context:
        context.prec = 3
        assert planned_loss(entry, stop, 3) == Decimal("3.37037036703703703670370370364")
        assert read_risk(risk().document()) == risk()


def test_float_money_cannot_enter_risk_document() -> None:
    document = risk().document()
    document["planned_loss"] = 5.0
    with pytest.raises(ValueError, match="decimal string"):
        read_risk(document)


@pytest.mark.parametrize("changed", ["stop", "entry", "quantity", "cap"])
def test_last_transport_boundary_recomputes_risk(changed: str) -> None:
    from freezegun import freeze_time
    from tests.unit._m085_fakes import FakeConfigurations, FakeIntents
    from tests.unit._m085_fakes import a_configuration as send_config
    from tests.unit.test_m085_paper_execution_handlers import TestSubmitAuthorizedPaperOrder

    harness = TestSubmitAuthorizedPaperOrder()
    approved_risk = EntryRiskContract(Decimal("4"), Decimal("3"), 1, 1, Decimal("5"), Decimal("1"))
    configuration = replace(
        send_config(),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("5"),
    )
    intent = an_intent(entry_risk=approved_risk)
    world = harness._world(
        intents=FakeIntents(intent), configurations=FakeConfigurations(configuration)
    )
    original = world["broker"].submit_order
    reached = []

    def connect(order: object, *, before_send: object = None) -> object:
        reached.append(True)
        if changed == "stop":
            object.__setattr__(approved_risk, "stop_price", Decimal("0.5"))
        elif changed == "entry":
            object.__setattr__(intent, "limit_price", Decimal("10"))
        elif changed == "quantity":
            object.__setattr__(intent, "quantity", 2)
        else:
            object.__setattr__(configuration, "maximum_planned_loss_per_trade", Decimal("0.5"))
        return original(order, before_send=before_send)

    with freeze_time(_NOW):
        harness._authorize(world)
        world["broker"].submit_order = connect
        result = harness._handler(world).handle(harness._command())
    assert reached == [True]
    assert not result.dispatched
    assert world["broker"].submitted == []


@pytest.mark.parametrize("version", [True, 2.0, "2", 3])
def test_risk_version_is_explicit_integer(version: object) -> None:
    document = risk().document() | {"version": version}
    with pytest.raises(ValueError):
        read_risk(document)


def test_owner_proposal_rendering_contains_exact_risk_evidence() -> None:
    from empirical_platform.usecases.decision_to_approval_io import (
        render_proposal_json,
        render_proposal_text,
    )

    proposal = evaluate(configuration=config()).proposal
    assert proposal is not None and proposal.entry_risk is not None
    assert render_proposal_json(proposal)["entry_risk"] == proposal.entry_risk.document()
    rendered = render_proposal_text(proposal)
    assert f"evaluated planned loss {proposal.entry_risk.planned_loss}" in rendered
    assert "configured maximum shares 1" in rendered
    assert "configured maximum planned loss 5" in rendered
