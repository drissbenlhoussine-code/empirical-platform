"""MILESTONE-083 -- behavioral tests for the watermark capture/get CLIs.

Proves each `main()`'s own argument handling, correct delegation to its
`run_*()` function, and output formatting, without touching real persistence:
`run_capture_evaluation_evidence_watermark`/`run_get_evaluation_evidence_
watermark` are monkeypatched at the module level, mirroring
`tests/unit/test_run_entrypoints.py`'s established pattern for the same
`entrypoints._composition.postgres_repository_runtime()` composition seam.
Real end-to-end composition (against real PostgreSQL) is proven separately by
`tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`.
"""

from __future__ import annotations

import json

import pytest

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.entrypoints import capture_evaluation_evidence_watermark as capture_module
from empirical_platform.entrypoints import get_evaluation_evidence_watermark as get_module


def _watermark() -> EvaluationEvidenceWatermark:
    return EvaluationEvidenceWatermark(
        watermark_governance_id="WM-CLI", receipt_governance_ids=("RC-A", "RC-B")
    )


@pytest.mark.parametrize(
    "module",
    [capture_module, get_module],
)
def test_no_arguments_is_refused(module: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit) as exc:
        module.main()  # type: ignore[attr-defined]
    assert "usage:" in str(exc.value)


@pytest.mark.parametrize(
    "module",
    [capture_module, get_module],
)
def test_too_many_positional_arguments_is_refused(
    module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "WM-1", "WM-2"])
    with pytest.raises(SystemExit) as exc:
        module.main()  # type: ignore[attr-defined]
    assert "usage:" in str(exc.value)


@pytest.mark.parametrize(
    "module",
    [capture_module, get_module],
)
def test_only_the_json_flag_with_no_identity_is_refused(
    module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    with pytest.raises(SystemExit) as exc:
        module.main()  # type: ignore[attr-defined]
    assert "usage:" in str(exc.value)


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


def test_capture_main_calls_run_capture_with_the_parsed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(*, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        calls.append(watermark_governance_id)
        return _watermark()

    monkeypatch.setattr(capture_module, "run_capture_evaluation_evidence_watermark", fake_run)
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    capture_module.main()

    assert calls == ["WM-CLI"]


def test_capture_main_prints_text_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        capture_module, "run_capture_evaluation_evidence_watermark", lambda **_: _watermark()
    )
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    capture_module.main()

    out = capsys.readouterr().out
    assert "watermark_governance_id: WM-CLI" in out
    assert "  - RC-A" in out


def test_capture_main_prints_json_with_the_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        capture_module, "run_capture_evaluation_evidence_watermark", lambda **_: _watermark()
    )
    monkeypatch.setattr("sys.argv", ["prog", "--json", "WM-CLI"])

    capture_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["watermark_governance_id"] == "WM-CLI"
    assert payload["receipt_governance_ids"] == ["RC-A", "RC-B"]


def test_capture_main_propagates_run_capture_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> EvaluationEvidenceWatermark:
        raise sentinel

    monkeypatch.setattr(capture_module, "run_capture_evaluation_evidence_watermark", failing_run)
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    with pytest.raises(RuntimeError) as excinfo:
        capture_module.main()
    assert excinfo.value is sentinel


def test_run_capture_accepts_an_optional_config_override() -> None:
    """Structural proof that the testability seam exists, mirroring
    `test_run_create_run_accepts_optional_config_and_identifier_generator_
    overrides`."""
    import inspect

    signature = inspect.signature(capture_module.run_capture_evaluation_evidence_watermark)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_main_calls_run_get_with_the_parsed_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(*, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        calls.append(watermark_governance_id)
        return _watermark()

    monkeypatch.setattr(get_module, "run_get_evaluation_evidence_watermark", fake_run)
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    get_module.main()

    assert calls == ["WM-CLI"]


def test_get_main_prints_text_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        get_module, "run_get_evaluation_evidence_watermark", lambda **_: _watermark()
    )
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    get_module.main()

    out = capsys.readouterr().out
    assert "watermark_governance_id: WM-CLI" in out


def test_get_main_prints_json_with_the_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        get_module, "run_get_evaluation_evidence_watermark", lambda **_: _watermark()
    )
    monkeypatch.setattr("sys.argv", ["prog", "--json", "WM-CLI"])

    get_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["watermark_governance_id"] == "WM-CLI"


def test_get_main_propagates_run_get_exceptions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = RuntimeError("adversarial composition failure")

    def failing_run(**_: object) -> EvaluationEvidenceWatermark:
        raise sentinel

    monkeypatch.setattr(get_module, "run_get_evaluation_evidence_watermark", failing_run)
    monkeypatch.setattr("sys.argv", ["prog", "WM-CLI"])

    with pytest.raises(RuntimeError) as excinfo:
        get_module.main()
    assert excinfo.value is sentinel


def test_run_get_accepts_an_optional_config_override() -> None:
    import inspect

    signature = inspect.signature(get_module.run_get_evaluation_evidence_watermark)
    assert "config" in signature.parameters
    assert signature.parameters["config"].default is None
