"""MILESTONE-053 behavioral tests for `entrypoints.create_run` and
`entrypoints.get_run`'s CLI wrappers.

Proves each `main()`'s own argument-count validation and correct delegation
to its `run_*()` function, without touching real persistence: `run_create_run`
and `run_get_run` are monkeypatched at the module level with deterministic
stubs, mirroring this project's own established preference for real
fakes/stubs over mocks. Resource-lifecycle correctness (the M050-Y-1 lesson)
is proven once, centrally, by `tests/unit/test_entrypoint_composition.py`
against the shared `_composition.postgres_repository_runtime()` helper both
of these entrypoints compose through -- it is not re-proven per entrypoint
here. Real end-to-end composition (against real PostgreSQL) is proven
separately by this milestone's own integration test.
"""

from __future__ import annotations

import json

import pytest

from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.entrypoints import create_run as create_run_module
from empirical_platform.entrypoints import get_run as get_run_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_run import RunSnapshot

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _run_identity() -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId("RUN-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _run_snapshot() -> RunSnapshot:
    return RunSnapshot(
        identity=_run_identity(),
        campaign_id=CampaignId("CAMP-0001"),
        state=RunLifecycleState.CREATED,
    )


# ---------------------------------------------------------------------------
# create_run
# ---------------------------------------------------------------------------


def test_create_run_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-run", "RUN-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-run"):
        create_run_module.main()


def test_create_run_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-run", "RUN-0001", "CAMP-0001", "extra"]
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-run"):
        create_run_module.main()


def test_create_run_main_calls_run_create_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run_create_run(
        *, run_governance_id: str, campaign_governance_id: str
    ) -> DomainIdentity[RunId]:
        calls.append(
            {
                "run_governance_id": run_governance_id,
                "campaign_governance_id": campaign_governance_id,
            }
        )
        return _run_identity()

    monkeypatch.setattr(create_run_module, "run_create_run", fake_run_create_run)
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-run", "RUN-0001", "CAMP-0001"])

    create_run_module.main()

    assert calls == [{"run_governance_id": "RUN-0001", "campaign_governance_id": "CAMP-0001"}]


def test_create_run_main_prints_exact_identity_payload_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(create_run_module, "run_create_run", lambda **_: _run_identity())
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-run", "RUN-0001", "CAMP-0001"])

    create_run_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"governance_id": "RUN-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_create_run_main_propagates_run_create_run_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_create_run(**_: str) -> DomainIdentity[RunId]:
        raise sentinel

    monkeypatch.setattr(create_run_module, "run_create_run", failing_run_create_run)
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-run", "RUN-0001", "CAMP-0001"])

    with pytest.raises(RuntimeError) as excinfo:
        create_run_module.main()

    assert excinfo.value is sentinel


def test_create_run_identity_payload_shape() -> None:
    payload = create_run_module._identity_payload(_run_identity())
    assert payload == {"governance_id": "RUN-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_run_create_run_accepts_optional_config_and_identifier_generator_overrides() -> None:
    """Structural proof that both testability seams exist."""
    import inspect

    signature = inspect.signature(create_run_module.run_create_run)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None
    assert "identifier_generator" in signature.parameters
    assert signature.parameters["identifier_generator"].default is None


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------


def test_get_run_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-run"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-run"):
        get_run_module.main()


def test_get_run_main_rejects_too_many_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-run", "RUN-0001", _RUNTIME_ID_VALUE, "extra"]
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-run"):
        get_run_module.main()


def test_get_run_main_calls_run_get_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run_get_run(*, run_governance_id: str, run_runtime_id: str) -> RunSnapshot:
        calls.append({"run_governance_id": run_governance_id, "run_runtime_id": run_runtime_id})
        return _run_snapshot()

    monkeypatch.setattr(get_run_module, "run_get_run", fake_run_get_run)
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-run", "RUN-0001", _RUNTIME_ID_VALUE])

    get_run_module.main()

    assert calls == [{"run_governance_id": "RUN-0001", "run_runtime_id": _RUNTIME_ID_VALUE}]


def test_get_run_main_prints_exact_snapshot_payload_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(get_run_module, "run_get_run", lambda **_: _run_snapshot())
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-run", "RUN-0001", _RUNTIME_ID_VALUE])

    get_run_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "governance_id": "RUN-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "campaign_id": "CAMP-0001",
        "state": "CREATED",
    }


def test_get_run_main_propagates_run_get_run_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run_get_run(**_: str) -> RunSnapshot:
        raise sentinel

    monkeypatch.setattr(get_run_module, "run_get_run", failing_run_get_run)
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-run", "RUN-0001", _RUNTIME_ID_VALUE])

    with pytest.raises(RuntimeError) as excinfo:
        get_run_module.main()

    assert excinfo.value is sentinel


def test_get_run_snapshot_payload_shape() -> None:
    payload = get_run_module._snapshot_payload(_run_snapshot())
    assert payload == {
        "governance_id": "RUN-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "campaign_id": "CAMP-0001",
        "state": "CREATED",
    }


def test_run_get_run_accepts_optional_config_override() -> None:
    import inspect

    signature = inspect.signature(get_run_module.run_get_run)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None
