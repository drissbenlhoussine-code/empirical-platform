"""MILESTONE-054 behavioral tests for the six `entrypoints.*review*` CLI
wrappers: `create_review`, `get_review`, `start_review`, `add_review_finding`,
`complete_review`, `cancel_review`.

Proves each `main()`'s own argument-count validation and correct delegation
to its `run_*()` function, without touching real persistence -- the same
convention as `tests/unit/test_run_entrypoints.py` and
`tests/unit/test_evidence_package_entrypoints.py`. Resource-lifecycle
correctness is proven once, centrally, by
`tests/unit/test_entrypoint_composition.py` against the shared
MILESTONE-053 `_composition.postgres_repository_runtime()` helper all six of
these entrypoints reuse unchanged. Real end-to-end composition (against real
PostgreSQL, including genuine lifecycle and OCC failures) is proven
separately by this milestone's own integration test.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from empirical_platform.entrypoints import add_review_finding as add_finding_module
from empirical_platform.entrypoints import cancel_review as cancel_module
from empirical_platform.entrypoints import complete_review as complete_module
from empirical_platform.entrypoints import create_review as create_module
from empirical_platform.entrypoints import get_review as get_module
from empirical_platform.entrypoints import start_review as start_module
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.shared.contracts.repository import SaveOperation, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_review import ReviewSnapshot

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_OCCURRED_AT_ISO = "2026-08-08T12:00:00+00:00"


def _review_identity() -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId("REVIEW-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _review_snapshot() -> ReviewSnapshot:
    return ReviewSnapshot(
        identity=_review_identity(),
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        reviewer_reference="reviewer-1",
        state=ReviewLifecycleState.ASSIGNED,
    )


def _save_result() -> SaveResult:
    return SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(1))


# ---------------------------------------------------------------------------
# create_review
# ---------------------------------------------------------------------------


def test_create_review_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-create-review", "REVIEW-0001"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-create-review"):
        create_module.main()


def test_create_review_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(
        *,
        review_governance_id: str,
        target_evidence_package_governance_id: str,
        reviewer_reference: str,
    ) -> DomainIdentity[ReviewId]:
        calls.append(
            {
                "review_governance_id": review_governance_id,
                "target_evidence_package_governance_id": target_evidence_package_governance_id,
                "reviewer_reference": reviewer_reference,
            }
        )
        return _review_identity()

    monkeypatch.setattr(create_module, "run_create_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-create-review", "REVIEW-0001", "EVID-0001", "reviewer-1"],
    )

    create_module.main()

    assert calls == [
        {
            "review_governance_id": "REVIEW-0001",
            "target_evidence_package_governance_id": "EVID-0001",
            "reviewer_reference": "reviewer-1",
        }
    ]


def test_create_review_main_prints_exact_identity_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(create_module, "run_create_review", lambda **_: _review_identity())
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-create-review", "REVIEW-0001", "EVID-0001", "reviewer-1"],
    )

    create_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"governance_id": "REVIEW-0001", "runtime_id": _RUNTIME_ID_VALUE}


def test_create_review_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: str) -> DomainIdentity[ReviewId]:
        raise sentinel

    monkeypatch.setattr(create_module, "run_create_review", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-create-review", "REVIEW-0001", "EVID-0001", "reviewer-1"],
    )

    with pytest.raises(RuntimeError) as excinfo:
        create_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# get_review
# ---------------------------------------------------------------------------


def test_get_review_main_rejects_missing_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["empirical-platform-get-review"])
    with pytest.raises(SystemExit, match="usage: empirical-platform-get-review"):
        get_module.main()


def test_get_review_main_calls_run_with_exact_parsed_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_run(*, review_governance_id: str, review_runtime_id: str) -> ReviewSnapshot:
        calls.append(
            {"review_governance_id": review_governance_id, "review_runtime_id": review_runtime_id}
        )
        return _review_snapshot()

    monkeypatch.setattr(get_module, "run_get_review", fake_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-review", "REVIEW-0001", _RUNTIME_ID_VALUE]
    )

    get_module.main()

    assert calls == [
        {"review_governance_id": "REVIEW-0001", "review_runtime_id": _RUNTIME_ID_VALUE}
    ]


def test_get_review_main_prints_exact_snapshot_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(get_module, "run_get_review", lambda **_: _review_snapshot())
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-review", "REVIEW-0001", _RUNTIME_ID_VALUE]
    )

    get_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "governance_id": "REVIEW-0001",
        "runtime_id": _RUNTIME_ID_VALUE,
        "target_evidence_package_id": "EVID-0001",
        "reviewer_reference": "reviewer-1",
        "state": "ASSIGNED",
    }


def test_get_review_main_propagates_exceptions_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: str) -> ReviewSnapshot:
        raise sentinel

    monkeypatch.setattr(get_module, "run_get_review", failing_run)
    monkeypatch.setattr(
        "sys.argv", ["empirical-platform-get-review", "REVIEW-0001", _RUNTIME_ID_VALUE]
    )

    with pytest.raises(RuntimeError) as excinfo:
        get_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# start_review
# ---------------------------------------------------------------------------


def test_start_review_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-start-review", "REVIEW-0001", _RUNTIME_ID_VALUE, "0", "actor"],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-start-review"):
        start_module.main()


def test_start_review_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(start_module, "run_start_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-start-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    start_module.main()

    assert calls == [
        {
            "review_governance_id": "REVIEW-0001",
            "review_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
            "reason": None,
        }
    ]


def test_start_review_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(start_module, "run_start_review", lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-start-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    start_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_start_review_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(start_module, "run_start_review", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-start-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        start_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# add_review_finding
# ---------------------------------------------------------------------------


def test_add_finding_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["empirical-platform-add-review-finding", "REVIEW-0001", _RUNTIME_ID_VALUE, "0"],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-add-review-finding"):
        add_finding_module.main()


def test_add_finding_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(add_finding_module, "run_add_review_finding", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-add-review-finding",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "finding text",
        ],
    )

    add_finding_module.main()

    assert calls == [
        {
            "review_governance_id": "REVIEW-0001",
            "review_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "text": "finding text",
            "rationale": None,
        }
    ]


def test_add_finding_main_parses_optional_rationale(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(add_finding_module, "run_add_review_finding", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-add-review-finding",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "finding text",
            "a rationale",
        ],
    )

    add_finding_module.main()

    assert calls[0]["rationale"] == "a rationale"


def test_add_finding_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(add_finding_module, "run_add_review_finding", lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-add-review-finding",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "finding text",
        ],
    )

    add_finding_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_run_add_review_finding_accepts_evidence_references_only_via_keyword() -> None:
    """Structural proof: `evidence_references` is reachable only via the
    Python-level `run_add_review_finding()` call, not via CLI argv --
    mirroring M053's identical `record_evidence_package_criterion_result`
    decision."""
    import inspect

    signature = inspect.signature(add_finding_module.run_add_review_finding)
    assert "evidence_references" in signature.parameters
    assert signature.parameters["evidence_references"].default == ()
    source = inspect.getsource(add_finding_module.main)
    assert "evidence_references" not in source


def test_add_finding_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(add_finding_module, "run_add_review_finding", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-add-review-finding",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "finding text",
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        add_finding_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# complete_review
# ---------------------------------------------------------------------------


def test_complete_review_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-complete-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "ACCEPTED",
            "final rationale",
            "actor-1",
        ],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-complete-review"):
        complete_module.main()


def test_complete_review_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(complete_module, "run_complete_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-complete-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "ACCEPTED",
            "final rationale",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    complete_module.main()

    assert calls == [
        {
            "review_governance_id": "REVIEW-0001",
            "review_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "disposition": ReviewDisposition.ACCEPTED,
            "final_disposition_rationale": "final rationale",
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
        }
    ]


def test_complete_review_main_parses_optional_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(complete_module, "run_complete_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-complete-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "ACCEPTED",
            "final rationale",
            "actor-1",
            _OCCURRED_AT_ISO,
            "CORR-1",
        ],
    )

    complete_module.main()

    assert calls[0]["correlation_id"] == "CORR-1"


def test_complete_review_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(complete_module, "run_complete_review", lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-complete-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "ACCEPTED",
            "final rationale",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    complete_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_complete_review_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(complete_module, "run_complete_review", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-complete-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "ACCEPTED",
            "final rationale",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        complete_module.main()

    assert excinfo.value is sentinel


# ---------------------------------------------------------------------------
# cancel_review
# ---------------------------------------------------------------------------


def test_cancel_review_main_rejects_too_few_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
        ],
    )
    with pytest.raises(SystemExit, match="usage: empirical-platform-cancel-review"):
        cancel_module.main()


def test_cancel_review_main_calls_run_with_exact_parsed_required_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(cancel_module, "run_cancel_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    cancel_module.main()

    assert calls == [
        {
            "review_governance_id": "REVIEW-0001",
            "review_runtime_id": _RUNTIME_ID_VALUE,
            "expected_persisted_version": 0,
            "reason": "a reason",
            "actor": "actor-1",
            "occurred_at": datetime.fromisoformat(_OCCURRED_AT_ISO),
            "correlation_id": None,
        }
    ]


def test_cancel_review_main_parses_optional_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> SaveResult:
        calls.append(kwargs)
        return _save_result()

    monkeypatch.setattr(cancel_module, "run_cancel_review", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
            "CORR-1",
        ],
    )

    cancel_module.main()

    assert calls[0]["correlation_id"] == "CORR-1"


def test_cancel_review_main_prints_exact_result_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cancel_module, "run_cancel_review", lambda **_: _save_result())
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    cancel_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"operation": "updated", "persisted_version": "1"}


def test_cancel_review_main_propagates_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> SaveResult:
        raise sentinel

    monkeypatch.setattr(cancel_module, "run_cancel_review", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "empirical-platform-cancel-review",
            "REVIEW-0001",
            _RUNTIME_ID_VALUE,
            "0",
            "a reason",
            "actor-1",
            _OCCURRED_AT_ISO,
        ],
    )

    with pytest.raises(RuntimeError) as excinfo:
        cancel_module.main()

    assert excinfo.value is sentinel
