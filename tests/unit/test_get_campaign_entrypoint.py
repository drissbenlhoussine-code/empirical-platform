"""MILESTONE-050 behavioral tests for `entrypoints.get_campaign`'s CLI wrapper.

Proves `main()`'s own argument-count validation and correct delegation to
`run_get_campaign()`, without touching real persistence: `run_get_campaign`
is monkeypatched at the module level with a deterministic stub, mirroring
this project's own established preference for real fakes/stubs over mocks.
Real end-to-end composition (against real PostgreSQL) is proven separately
by this milestone's own integration test.
"""

from __future__ import annotations

import json

import pytest

from empirical_platform.campaign.aggregate import CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.entrypoints import get_campaign as get_campaign_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_campaign import CampaignSnapshot

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _snapshot() -> CampaignSnapshot:
    identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )
    return CampaignSnapshot(
        identity=identity,
        scope_statement=CampaignScopeStatement("a real scope statement"),
        state=CampaignLifecycleState.DRAFT,
    )


def test_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-campaign"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-campaign"):
        get_campaign_module.main()


def test_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE, "extra"]
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-campaign"):
        get_campaign_module.main()


def test_main_calls_run_get_campaign_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run_get_campaign(
        *, campaign_governance_id: str, campaign_runtime_id: str
    ) -> CampaignSnapshot:
        calls.append(
            {
                "campaign_governance_id": campaign_governance_id,
                "campaign_runtime_id": campaign_runtime_id,
            }
        )
        return _snapshot()

    monkeypatch.setattr(get_campaign_module, "run_get_campaign", fake_run_get_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    get_campaign_module.main()

    assert calls == [
        {"campaign_governance_id": "CAMP-0001", "campaign_runtime_id": _RUNTIME_ID_VALUE}
    ]


def test_main_prints_exact_snapshot_payload_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(get_campaign_module, "run_get_campaign", lambda **_: _snapshot())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    get_campaign_module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {
        "governance_id": "CAMP-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "scope_statement": "a real scope statement",
        "state": "DRAFT",
    }


def test_main_propagates_run_get_campaign_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_get_campaign(**_: str) -> CampaignSnapshot:
        raise sentinel

    monkeypatch.setattr(get_campaign_module, "run_get_campaign", failing_run_get_campaign)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-campaign", "CAMP-0001", _RUNTIME_ID_VALUE]
    )

    with pytest.raises(RuntimeError) as excinfo:
        get_campaign_module.main()

    assert excinfo.value is sentinel


def test_snapshot_payload_shape() -> None:
    payload = get_campaign_module._snapshot_payload(_snapshot())
    assert set(payload.keys()) == {"governance_id", "runtime_id", "scope_statement", "state"}
    assert payload["governance_id"] == "CAMP-0001"
    assert payload["runtime_id"] == _RUNTIME_ID_VALUE
    assert payload["scope_statement"] == "a real scope statement"
    assert payload["state"] == "DRAFT"


def test_run_get_campaign_accepts_optional_config_override() -> None:
    """Structural proof that the testability seam (an explicit `config`
    parameter) exists, without constructing real persistence."""
    import inspect

    signature = inspect.signature(get_campaign_module.run_get_campaign)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None
