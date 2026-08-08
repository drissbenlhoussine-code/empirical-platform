"""MILESTONE-055 behavioral tests for the seven new Run execution CLI
wrappers: `authorize_run`, `start_run_acquisition`, `append_run_manifest`,
`start_run_normalization`, `start_run_validation`, `complete_run_execution`,
`fail_run`.

Proves each `main()`'s own argument-count validation and correct delegation
to its `run_*()` function, without touching real persistence -- the same
convention as `tests/unit/test_review_entrypoints.py`. Resource-lifecycle
correctness is proven once, centrally, by
`tests/unit/test_entrypoint_composition.py`. Real end-to-end composition
(against real PostgreSQL, including the complete legal lifecycle and a
genuine OCC conflict) is proven separately by this milestone's own
integration test.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from empirical_platform.entrypoints import append_run_manifest as append_manifest_module
from empirical_platform.entrypoints import authorize_run as authorize_module
from empirical_platform.entrypoints import complete_run_execution as complete_module
from empirical_platform.entrypoints import fail_run as fail_module
from empirical_platform.entrypoints import start_run_acquisition as start_acquisition_module
from empirical_platform.entrypoints import start_run_normalization as start_normalization_module
from empirical_platform.entrypoints import start_run_validation as start_validation_module
from empirical_platform.shared.contracts.repository import SaveOperation, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT_ISO = "2026-08-08T12:00:00+00:00"


def _save_result() -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))


# ---------------------------------------------------------------------------
# authorize_run / start_run_acquisition / start_run_normalization /
# start_run_validation / complete_run_execution
# (identical CLI shape: governance_id, runtime_id, expected_version, actor,
# occurred_at_iso, [correlation_id], [reason])
# ---------------------------------------------------------------------------

_TRANSITION_MODULE_CASES = [
    (authorize_module, "run_authorize_run", "empirical-platform-authorize-run"),
    (
        start_acquisition_module,
        "run_start_run_acquisition",
        "empirical-platform-start-run-acquisition",
    ),
    (
        start_normalization_module,
        "run_start_run_normalization",
        "empirical-platform-start-run-normalization",
    ),
    (
        start_validation_module,
        "run_start_run_validation",
        "empirical-platform-start-run-validation",
    ),
    (
        complete_module,
        "run_complete_run_execution",
        "empirical-platform-complete-run-execution",
    ),
]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_rejects_too_few_arguments(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del run_attr
    monkeypatch.setattr("sys.argv", [usage_prefix, "RUN-0001", _RUNTIME_ID_VALUE, "0", "actor"])
    with pytest.raises(SystemExit, match=f"usage: {usage_prefix}"):
        module.main()  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_calls_run_with_exact_parsed_required_arguments(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(module, run_attr, fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [usage_prefix, "RUN-0001", _RUNTIME_ID_VALUE, "0", "actor-1", _OCCURRED_AT_ISO],
    )

    module.main()  # type: ignore[attr-defined]

    assert calls == [
        {
            "run_governance_id": "RUN-0001",
            "run_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
            "reason": None,
        }
    ]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_parses_optional_correlation_id_and_reason(
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
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
            "CORR-1",
            "a reason",
        ],
    )

    module.main()  # type: ignore[attr-defined]

    assert calls[0]["correlation_id"] == "CORR-1"
    assert calls[0]["reason"] == "a reason"


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_prints_exact_result_payload(
    module: object,
    run_attr: str,
    usage_prefix: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(module, run_attr, lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [usage_prefix, "RUN-0001", _RUNTIME_ID_VALUE, "0", "actor-1", _OCCURRED_AT_ISO],
    )

    module.main()  # type: ignore[attr-defined]

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_propagates_exceptions_unchanged(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(module, run_attr, failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [usage_prefix, "RUN-0001", _RUNTIME_ID_VALUE, "0", "actor-1", _OCCURRED_AT_ISO],
    )

    with pytest.raises(RuntimeError) as excinfo:
        module.main()  # type: ignore[attr-defined]

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# fail_run
# ---------------------------------------------------------------------------


def test_fail_run_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-fail-run", "RUN-0001", _RUNTIME_ID_VALUE, "0", "a reason", "actor-1"],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-fail-run"):
        fail_module.main()


def test_fail_run_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(fail_module, "run_fail_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-fail-run",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    fail_module.main()

    assert calls == [
        {
            "run_governance_id": "RUN-0001",
            "run_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "reason": "a reason",
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
        }
    ]


def test_fail_run_main_parses_optional_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(fail_module, "run_fail_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-fail-run",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
            "CORR-1",
        ],
    )

    fail_module.main()

    assert calls[0]["correlation_id"] == "CORR-1"


def test_fail_run_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(fail_module, "run_fail_run", lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-fail-run",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    fail_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_fail_run_main_propagates_exceptions_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(fail_module, "run_fail_run", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-fail-run",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        fail_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# append_run_manifest
# ---------------------------------------------------------------------------


def test_append_manifest_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-append-run-manifest", "RUN-0001", _RUNTIME_ID_VALUE, "0"],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-append-run-manifest"):
        append_manifest_module.main()


def test_append_manifest_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(append_manifest_module, "run_append_run_manifest", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-append-run-manifest",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            _OCCURRED_AT_ISO,
            "s3://bucket/data.csv",
        ],
    )

    append_manifest_module.main()

    assert calls == [
        {
            "run_governance_id": "RUN-0001",
            "run_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "recorded_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "source": "s3://bucket/data.csv",
            "acquisition_method": None,
            "normalization_method": None,
        }
    ]


def test_append_manifest_main_parses_optional_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(append_manifest_module, "run_append_run_manifest", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-append-run-manifest",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            _OCCURRED_AT_ISO,
            "s3://bucket/data.csv",
            "bulk-download",
            "z-score",
        ],
    )

    append_manifest_module.main()

    assert calls[0]["acquisition_method"] == "bulk-download"
    assert calls[0]["normalization_method"] == "z-score"


def test_append_manifest_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        append_manifest_module, "run_append_run_manifest", lambda **_: _save_result()
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-append-run-manifest",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            _OCCURRED_AT_ISO,
            "s3://bucket/data.csv",
        ],
    )

    append_manifest_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_append_manifest_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(append_manifest_module, "run_append_run_manifest", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-append-run-manifest",
            "RUN-0001",
            _RUNTIME_ID_VALUE,
            "0",
            _OCCURRED_AT_ISO,
            "s3://bucket/data.csv",
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        append_manifest_module.main()

    assert excinfo.value is sentinel


def test_run_append_run_manifest_accepts_manifest_id_and_notes_only_via_keyword() -> None:
    """Structural proof: `manifest_id`/`notes` are reachable only via the
    Python-level `run_append_run_manifest()` call, not via CLI argv --
    mirroring M053's identical `record_evidence_package_criterion_result`
    decision."""
    import inspect

    signature = inspect.signature(append_manifest_module.run_append_run_manifest)
    assert "manifest_id" in signature.parameters
    assert signature.parameters["manifest_id"].default is None
    assert "notes" in signature.parameters
    assert signature.parameters["notes"].default == ()
    source = inspect.getsource(append_manifest_module.main)
    assert "manifest_id" not in source
    assert "notes" not in source
