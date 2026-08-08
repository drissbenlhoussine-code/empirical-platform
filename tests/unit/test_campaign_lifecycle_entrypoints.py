"""MILESTONE-056 behavioral tests for the seven new Campaign lifecycle CLI
wrappers: `prepare_campaign_for_authorization`, `revise_campaign_scope_statement`,
`record_campaign_authorization`, `activate_campaign`, `suspend_campaign`,
`resume_campaign`, `complete_campaign`.

Proves each `main()`'s own argument-count validation and correct delegation
to its `run_*()` function, without touching real persistence -- the same
convention as `tests/unit/test_run_execution_entrypoints.py`.
Resource-lifecycle correctness is proven once, centrally, by
`tests/unit/test_entrypoint_composition.py`. Real end-to-end composition
(against real PostgreSQL, including the complete legal lifecycle) is proven
separately by this milestone's own integration test.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from empirical_platform.entrypoints import activate_campaign as activate_module
from empirical_platform.entrypoints import complete_campaign as complete_module
from empirical_platform.entrypoints import (
    prepare_campaign_for_authorization as prepare_module,
)
from empirical_platform.entrypoints import record_campaign_authorization as record_auth_module
from empirical_platform.entrypoints import resume_campaign as resume_module
from empirical_platform.entrypoints import (
    revise_campaign_scope_statement as revise_scope_module,
)
from empirical_platform.entrypoints import suspend_campaign as suspend_module
from empirical_platform.shared.contracts.repository import SaveOperation, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT_ISO = "2026-08-08T12:00:00+00:00"


def _save_result() -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))


# ---------------------------------------------------------------------------
# prepare_campaign_for_authorization
# (shape: governance_id, runtime_id, expected_version, actor, occurred_at_iso,
# [correlation_id], [reason])
# ---------------------------------------------------------------------------


def test_prepare_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-prepare-campaign-for-authorization",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor",
        ],
    )
    with pytest.raises(
        SystemExit, match="usage: empirical-platform-prepare-campaign-for-authorization"
    ):
        prepare_module.main()


def test_prepare_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(prepare_module, "run_prepare_campaign_for_authorization", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-prepare-campaign-for-authorization",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    prepare_module.main()

    assert calls == [
        {
            "campaign_governance_id": "CAMP-0001",
            "campaign_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
            "reason": None,
        }
    ]


def test_prepare_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        prepare_module, "run_prepare_campaign_for_authorization", lambda **_: _save_result()
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-prepare-campaign-for-authorization",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    prepare_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_prepare_main_propagates_exceptions_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(prepare_module, "run_prepare_campaign_for_authorization", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-prepare-campaign-for-authorization",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        prepare_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# revise_campaign_scope_statement
# ---------------------------------------------------------------------------


def test_revise_scope_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-revise-campaign-scope-statement", "CAMP-0001", _RUNTIME_ID_VALUE],
    )
    with pytest.raises(
        SystemExit, match="usage: empirical-platform-revise-campaign-scope-statement"
    ):
        revise_scope_module.main()


def test_revise_scope_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(revise_scope_module, "run_revise_campaign_scope_statement", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-revise-campaign-scope-statement",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a revised scope",
        ],
    )

    revise_scope_module.main()

    assert calls == [
        {
            "campaign_governance_id": "CAMP-0001",
            "campaign_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "scope_statement": "a revised scope",
        }
    ]


def test_revise_scope_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        revise_scope_module, "run_revise_campaign_scope_statement", lambda **_: _save_result()
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-revise-campaign-scope-statement",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a revised scope",
        ],
    )

    revise_scope_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_revise_scope_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(revise_scope_module, "run_revise_campaign_scope_statement", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-revise-campaign-scope-statement",
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a revised scope",
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        revise_scope_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# record_campaign_authorization / activate_campaign / suspend_campaign /
# resume_campaign / complete_campaign
# (identical CLI shape: governance_id, runtime_id, expected_version, reason,
# actor, occurred_at_iso, [correlation_id])
# ---------------------------------------------------------------------------

_REASON_MODULE_CASES = [
    (
        record_auth_module,
        "run_record_campaign_authorization",
        "empirical-platform-record-campaign-authorization",
    ),
    (activate_module, "run_activate_campaign", "empirical-platform-activate-campaign"),
    (suspend_module, "run_suspend_campaign", "empirical-platform-suspend-campaign"),
    (resume_module, "run_resume_campaign", "empirical-platform-resume-campaign"),
    (complete_module, "run_complete_campaign", "empirical-platform-complete-campaign"),
]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _REASON_MODULE_CASES)
def test_reason_command_main_rejects_too_few_arguments(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del run_attr
    monkeypatch.setattr(
        "sys.argv", [usage_prefix, "CAMP-0001", _RUNTIME_ID_VALUE, "0", "a reason", "actor"]
    )
    with pytest.raises(SystemExit, match=f"usage: {usage_prefix}"):
        module.main()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _REASON_MODULE_CASES)
def test_reason_command_main_calls_run_with_exact_parsed_required_arguments(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(module, run_attr, fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            usage_prefix,
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    module.main()  # type: ignore[attr-defined]

    assert calls == [
        {
            "campaign_governance_id": "CAMP-0001",
            "campaign_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "reason": "a reason",
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
        }
    ]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _REASON_MODULE_CASES)
def test_reason_command_main_parses_optional_correlation_id(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(module, run_attr, fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            usage_prefix,
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
            "CORR-1",
        ],
    )

    module.main()  # type: ignore[attr-defined]

    assert calls[0]["correlation_id"] == "CORR-1"


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _REASON_MODULE_CASES)
def test_reason_command_main_prints_exact_result_payload(
    module: object,
    run_attr: str,
    usage_prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(module, run_attr, lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            usage_prefix,
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    module.main()  # type: ignore[attr-defined]

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _REASON_MODULE_CASES)
def test_reason_command_main_propagates_exceptions_unchanged(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(module, run_attr, failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            usage_prefix,
            "CAMP-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        module.main()  # type: ignore[attr-defined]

    assert excinfo.value is sentinel
