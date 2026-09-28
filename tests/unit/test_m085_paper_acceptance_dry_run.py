"""MILESTONE-085 corrective pass (item 8): the legacy harness's dry run is refused.

`tools/m085_paper_acceptance.py --dry-run` used to run "everything except dispatch" --
which wrote a configuration, a scripted APPROVE decision, an intent, three time-basis
rows, a preview and an account snapshot, and overwrote the evidence file. These tests
prove the flag now refuses BEFORE any of that can happen: no runtime, no database
connection, no socket, no handler that records an approval, intent, authorization,
attempt or order is constructed, and no file is written.

The harness is loaded from its path and never run without the flag.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from types import ModuleType

import pytest

from empirical_platform.entrypoints import _paper_composition
from empirical_platform.usecases import paper_execution as usecases

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "m085_paper_acceptance.py"

#: Every handler that writes something the harness's old dry run wrote, or that sends.
_WRITERS = (
    "PreparePaperBoundTradeProposalHandler",
    "DecidePaperBoundTradeProposalHandler",
    "IssuePaperBoundOrderIntentHandler",
    "PreviewPaperSubmissionHandler",
    "AuthorizePaperSubmissionHandler",
    "SubmitAuthorizedPaperOrderHandler",
    "CancelPaperOrderHandler",
    "ReconcilePaperOrderHandler",
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m085_paper_acceptance_under_test", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def touched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace everything with a side effect by a recorder that also refuses."""
    record: list[str] = []

    def refuse(name: str) -> object:
        def stand_in(*args: object, **kwargs: object) -> object:
            record.append(name)
            raise AssertionError(f"the dry run reached {name}")

        return stand_in

    monkeypatch.setattr(_paper_composition, "paper_execution_runtime", refuse("runtime"))
    for name in _WRITERS:
        monkeypatch.setattr(usecases, name, refuse(name))
    monkeypatch.setattr(socket, "socket", refuse("socket"))
    monkeypatch.setattr(socket, "create_connection", refuse("connection"))
    return record


def test_dry_run_is_refused_before_any_record_connection_or_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    touched: list[str],
) -> None:
    tool = _load()
    evidence = tmp_path / "paper-acceptance-results.md"
    monkeypatch.setattr(tool, "EVIDENCE", evidence)
    monkeypatch.setattr(tool, "PACKAGE", tmp_path)
    monkeypatch.setattr(tool, "build_m084_chain", lambda log: touched.append("chain") or None)

    assert tool.main(["--dry-run"]) == 2

    assert touched == [], "nothing may be constructed, connected or written by a dry run"
    assert not evidence.exists()
    assert list(tmp_path.iterdir()) == []
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
    assert "approval" in captured.err
    assert captured.out == ""


def test_the_refusal_guard_is_what_stops_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # Anti-vacuity for the test above: without the flag the harness DOES reach the
    # runtime immediately, so an empty record there is the refusal working, not a
    # harness that never touches anything.
    tool = _load()
    reached: list[str] = []

    def runtime(*args: object, **kwargs: object) -> object:
        reached.append("runtime")
        raise RuntimeError("stopped before any real connection")

    monkeypatch.setattr(_paper_composition, "paper_execution_runtime", runtime)
    with pytest.raises(RuntimeError, match="stopped before any real connection"):
        tool.main([])
    assert reached == ["runtime"]
