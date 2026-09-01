"""MILESTONE-083 -- argument handling for the watermark capture/get CLIs.

No database and no composition root reached: both `main()` functions raise
`SystemExit` on a malformed argument list before `postgres_repository_runtime`
is ever called, so these tests exercise exactly that boundary.
"""

from __future__ import annotations

import pytest

from empirical_platform.entrypoints import (
    capture_evaluation_evidence_watermark,
    get_evaluation_evidence_watermark,
)


@pytest.mark.parametrize(
    "module",
    [capture_evaluation_evidence_watermark, get_evaluation_evidence_watermark],
)
def test_no_arguments_is_refused(module: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(SystemExit) as exc:
        module.main()  # type: ignore[attr-defined]
    assert "usage:" in str(exc.value)


@pytest.mark.parametrize(
    "module",
    [capture_evaluation_evidence_watermark, get_evaluation_evidence_watermark],
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
    [capture_evaluation_evidence_watermark, get_evaluation_evidence_watermark],
)
def test_only_the_json_flag_with_no_identity_is_refused(
    module: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    with pytest.raises(SystemExit) as exc:
        module.main()  # type: ignore[attr-defined]
    assert "usage:" in str(exc.value)
