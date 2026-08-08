"""MILESTONE-053 behavioral tests for the six `entrypoints.*evidence_package*`
CLI wrappers: `create_evidence_package`, `get_evidence_package`,
`start_evidence_package_collection`, `record_evidence_package_criterion_result`,
`record_evidence_package_artifact_reference`, `seal_evidence_package`.

Proves each `main()`'s own argument-count validation and correct delegation
to its `run_*()` function, without touching real persistence -- the same
convention as `tests/unit/test_run_entrypoints.py`. Resource-lifecycle
correctness is proven once, centrally, by
`tests/unit/test_entrypoint_composition.py`. Real end-to-end composition
(against real PostgreSQL, including genuine lifecycle and OCC failures) is
proven separately by this milestone's own integration test.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from empirical_platform.entrypoints import create_evidence_package as create_ep_module
from empirical_platform.entrypoints import get_evidence_package as get_ep_module
from empirical_platform.entrypoints import (
    record_evidence_package_artifact_reference as record_artifact_module,
)
from empirical_platform.entrypoints import (
    record_evidence_package_criterion_result as record_criterion_module,
)
from empirical_platform.entrypoints import seal_evidence_package as seal_module
from empirical_platform.entrypoints import start_evidence_package_collection as start_module
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.repository import SaveOperation, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_evidence_package import EvidencePackageSnapshot

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT_ISO = "2026-08-08T12:00:00+00:00"


def _ep_identity() -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _ep_snapshot() -> EvidencePackageSnapshot:
    return EvidencePackageSnapshot(
        identity=_ep_identity(),
        run_id=RunId("RUN-0001"),
        state=EvidencePackageLifecycleState.COLLECTING,
    )


def _save_result() -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))


# ---------------------------------------------------------------------------
# create_evidence_package
# ---------------------------------------------------------------------------


def test_create_ep_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-evidence-package", "EVID-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-evidence-package"):
        create_ep_module.main()


def test_create_ep_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(
        *, evidence_package_governance_id: str, run_governance_id: str
    ) -> DomainIdentity[EvidencePackageId]:
        calls.append(
            {
                "evidence_package_governance_id": evidence_package_governance_id,
                "run_governance_id": run_governance_id,
            }
        )
        return _ep_identity()

    monkeypatch.setattr(create_ep_module, "run_create_evidence_package", fake_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-evidence-package", "EVID-0001", "RUN-0001"]
    )

    create_ep_module.main()

    assert calls == [
        {"evidence_package_governance_id": "EVID-0001", "run_governance_id": "RUN-0001"}
    ]


def test_create_ep_main_prints_exact_identity_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(create_ep_module, "run_create_evidence_package", lambda **_: _ep_identity())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-evidence-package", "EVID-0001", "RUN-0001"]
    )

    create_ep_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"governance_id": "EVID-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_create_ep_main_propagates_exceptions_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: str) -> DomainIdentity[EvidencePackageId]:
        raise sentinel

    monkeypatch.setattr(create_ep_module, "run_create_evidence_package", failing_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-create-evidence-package", "EVID-0001", "RUN-0001"]
    )

    with pytest.raises(RuntimeError) as excinfo:
        create_ep_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# get_evidence_package
# ---------------------------------------------------------------------------


def test_get_ep_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-evidence-package"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-evidence-package"):
        get_ep_module.main()


def test_get_ep_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(
        *, evidence_package_governance_id: str, evidence_package_runtime_id: str
    ) -> EvidencePackageSnapshot:
        calls.append(
            {
                "evidence_package_governance_id": evidence_package_governance_id,
                "evidence_package_runtime_id": evidence_package_runtime_id,
            }
        )
        return _ep_snapshot()

    monkeypatch.setattr(get_ep_module, "run_get_evidence_package", fake_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-evidence-package", "EVID-0001", _RUNTIME_ID_VALUE]
    )

    get_ep_module.main()

    assert calls == [
        {
            "evidence_package_governance_id": "EVID-0001",
            "evidence_package_runtime_id": _RUNTIME_ID_VALUE,
        }
    ]


def test_get_ep_main_prints_exact_snapshot_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(get_ep_module, "run_get_evidence_package", lambda **_: _ep_snapshot())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-evidence-package", "EVID-0001", _RUNTIME_ID_VALUE]
    )

    get_ep_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "governance_id": "EVID-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "run_id": "RUN-0001",
        "state": "COLLECTING",
    }


def test_get_ep_main_propagates_exceptions_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: str) -> EvidencePackageSnapshot:
        raise sentinel

    monkeypatch.setattr(get_ep_module, "run_get_evidence_package", failing_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-evidence-package", "EVID-0001", _RUNTIME_ID_VALUE]
    )

    with pytest.raises(RuntimeError) as excinfo:
        get_ep_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# start_evidence_package_collection / seal_evidence_package
# (identical CLI shape: governance_id, runtime_id, expected_version, actor,
# occurred_at_iso, [correlation_id], [reason])
# ---------------------------------------------------------------------------


_TRANSITION_MODULE_CASES = [
    (
        start_module,
        "run_start_evidence_package_collection",
        "empirical-platform-start-evidence-package-collection",
    ),
    (seal_module, "run_seal_evidence_package", "empirical-platform-seal-evidence-package"),
]


@pytest.mark.parametrize(("module", "run_attr", "usage_prefix"), _TRANSITION_MODULE_CASES)
def test_transition_command_main_rejects_too_few_arguments(
    module: object, run_attr: str, usage_prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del run_attr
    monkeypatch.setattr("sys.argv", [usage_prefix, "EVID-0001", _RUNTIME_ID_VALUE, "0", "actor"])
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
        [usage_prefix, "EVID-0001", _RUNTIME_ID_VALUE, "0", "actor-1", _OCCURRED_AT_ISO],
    )

    module.main()  # type: ignore[attr-defined]

    assert calls == [
        {
            "evidence_package_governance_id": "EVID-0001",
            "evidence_package_runtime_id": _RUNTIME_ID_VALUE,
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
            "EVID-0001",
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
        [usage_prefix, "EVID-0001", _RUNTIME_ID_VALUE, "0", "actor-1", _OCCURRED_AT_ISO],
    )

    module.main()  # type: ignore[attr-defined]

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


# ---------------------------------------------------------------------------
# record_evidence_package_criterion_result
# ---------------------------------------------------------------------------


def test_record_criterion_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-criterion-result",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "criterion-1",
        ],
    )
    with pytest.raises(
        SystemExit, match="usage: empirical-platform-record-evidence-package-criterion-result"
    ):
        record_criterion_module.main()


def test_record_criterion_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(
        record_criterion_module, "run_record_evidence_package_criterion_result", fake_run
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-criterion-result",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "criterion-1",
            _OCCURRED_AT_ISO,
            "PASS",
        ],
    )

    record_criterion_module.main()

    assert calls == [
        {
            "evidence_package_governance_id": "EVID-0001",
            "evidence_package_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "criterion_id": "criterion-1",
            "recorded_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "result_label": "PASS",
            "summary": None,
        }
    ]


def test_record_criterion_main_parses_optional_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(
        record_criterion_module, "run_record_evidence_package_criterion_result", fake_run
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-criterion-result",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "criterion-1",
            _OCCURRED_AT_ISO,
            "PASS",
            "a summary",
        ],
    )

    record_criterion_module.main()

    assert calls[0]["summary"] == "a summary"


def test_record_criterion_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        record_criterion_module,
        "run_record_evidence_package_criterion_result",
        lambda **_: _save_result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-criterion-result",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "criterion-1",
            _OCCURRED_AT_ISO,
            "PASS",
        ],
    )

    record_criterion_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_run_record_criterion_accepts_evidence_references_only_via_keyword() -> None:
    """Structural proof: `evidence_references` is reachable only via the
    Python-level `run_record_evidence_package_criterion_result()` call, not
    via CLI argv -- `main()` deliberately does not expose it."""
    import inspect

    signature = inspect.signature(
        record_criterion_module.run_record_evidence_package_criterion_result
    )
    assert "evidence_references" in signature.parameters
    assert signature.parameters["evidence_references"].default == ()
    source = inspect.getsource(record_criterion_module.main)
    assert "evidence_references" not in source


def test_record_criterion_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(
        record_criterion_module, "run_record_evidence_package_criterion_result", failing_run
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-criterion-result",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "criterion-1",
            _OCCURRED_AT_ISO,
            "PASS",
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        record_criterion_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# record_evidence_package_artifact_reference
# ---------------------------------------------------------------------------


def test_record_artifact_main_rejects_wrong_argument_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-artifact-reference",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
        ],
    )
    with pytest.raises(
        SystemExit, match="usage: empirical-platform-record-evidence-package-artifact-reference"
    ):
        record_artifact_module.main()


def test_record_artifact_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(
        record_artifact_module, "run_record_evidence_package_artifact_reference", fake_run
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-artifact-reference",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "s3://bucket/key",
        ],
    )

    record_artifact_module.main()

    assert calls == [
        {
            "evidence_package_governance_id": "EVID-0001",
            "evidence_package_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "value": "s3://bucket/key",
        }
    ]


def test_record_artifact_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        record_artifact_module,
        "run_record_evidence_package_artifact_reference",
        lambda **_: _save_result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-artifact-reference",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "s3://bucket/key",
        ],
    )

    record_artifact_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_record_artifact_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(
        record_artifact_module, "run_record_evidence_package_artifact_reference", failing_run
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-record-evidence-package-artifact-reference",
            "EVID-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "s3://bucket/key",
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        record_artifact_module.main()

    assert excinfo.value is sentinel
