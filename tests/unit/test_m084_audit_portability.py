"""MILESTONE-084 derived-audit tooling: the pin agrees, and the gates can run.

Two post-freeze administrative corrections are held fixed here. Both were found
while reconstructing M084 as the input contract for M085, and both are defects in
DERIVED AUDIT TOOLING only -- no M084 production module, migration, authority
file, recorded claim or result is involved.

FIND-F-01 -- the audit compared against a moving target
-------------------------------------------------------

`tools/render_m084_file_audit.py` and `tools/render_m084_exhaustion_table.py`
both compared `BASE..HEAD` and read file contents from the working tree. Correct
while the branch WAS the pull request; wrong once it was merged, because the
range then also swept in the merge, freeze and checkpoint commits and the content
reads followed later edits to shared toolchain files. Both are now pinned to the
approved M084 head. Each tool carries its own copy of the pin, following the
convention already used for the base commit across this toolchain, so the tests
here require every copy to agree -- a pin duplicated without a check is a pin
that drifts.

FIND-F-02 -- the gates could not run outside one machine
--------------------------------------------------------

`tools/render_m084_exhaustion_table.py` ran its gate subprocesses as
`.venv313/bin/python` with the environment REPLACED by
`PATH=/usr/bin:/bin:/usr/local/bin`. Both are POSIX-only, and both are specific
to one operator's layout: on Windows that executable does not exist, and
replacing the whole environment removes what Windows needs to start a process at
all. Every gate row failed for an environment reason while claiming to have
measured a gate, so the table could not be rendered at all.

The fix uses the interpreter already running the tool, refuses to run under an
unsupported one rather than reporting its exit codes as evidence, and inherits
the environment instead of replacing it. The tests below cover both directions:
that a supported interpreter is accepted and actually executes, and that an
unsupported one raises.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tools import render_m084_exhaustion_table as exhaustion
from tools import render_m084_file_audit as file_audit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

#: Every tool that pins the M084 base commit, and the name it pins it under.
_BASE_PINS = {
    "tools/render_m084_file_audit.py": "BASE_GROUPS",
    "tools/render_m084_exhaustion_table.py": "_BASE_GROUPS",
    "tools/check_frozen_paths.py": "_BASE_GROUPS",
    "tools/m084_frozen_m083_acceptance.py": "_FROZEN_COMMIT_GROUPS",
}

#: Every tool that pins the approved M084 head.
_HEAD_PINS = {
    "tools/render_m084_file_audit.py": "HEAD_GROUPS",
    "tools/render_m084_exhaustion_table.py": "_HEAD_GROUPS",
}


def _code_strings(relative_path: str) -> list[tuple[int, str]]:
    """Every string constant in the module that is NOT a docstring.

    Docstrings are excluded deliberately. The modules under test necessarily
    QUOTE the defective literals in order to explain them, and a plain substring
    search over the file reports that explanation as the defect -- a shape this
    toolchain has already been caught by more than once.
    """
    tree = ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and id(node) not in docstrings
        and isinstance(value := node.value, str)
    ]


def _literal_tuple(relative_path: str, name: str) -> tuple[str, ...]:
    """Read a module-level tuple constant without importing the module.

    Read rather than imported so that a tool with import-time behaviour cannot
    run it as a side effect of checking its constants, and so that private names
    are readable too.
    """
    tree = ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple), (relative_path, name)
            return value
    raise AssertionError(f"{relative_path} has no module-level {name}")


class TestEveryCopyOfThePinAgrees:
    """FIND-F-01. A pin duplicated across four files is four chances to drift."""

    def test_every_tool_pins_the_same_base_commit(self) -> None:
        joined = {path: "".join(_literal_tuple(path, name)) for path, name in _BASE_PINS.items()}
        assert len(set(joined.values())) == 1, joined
        assert set(joined.values()) == {file_audit.BASE}

    def test_every_tool_that_pins_the_head_pins_the_same_one(self) -> None:
        joined = {path: "".join(_literal_tuple(path, name)) for path, name in _HEAD_PINS.items()}
        assert len(set(joined.values())) == 1, joined
        assert set(joined.values()) == {file_audit.HEAD}

    def test_the_two_renderers_agree_at_runtime_not_only_in_source(self) -> None:
        assert exhaustion.BASE == file_audit.BASE
        assert exhaustion.HEAD == file_audit.HEAD

    def test_the_pinned_commits_are_full_length_and_distinct(self) -> None:
        assert len(file_audit.BASE) == 40
        assert len(file_audit.HEAD) == 40
        assert file_audit.BASE != file_audit.HEAD

    def test_neither_renderer_still_compares_against_the_branch_tip(self) -> None:
        # The defect had one shape: a git range ending at the branch tip. Named
        # so it cannot come back by copy-paste.
        #
        # Scoped to the two RENDERERS. `tools/check_frozen_paths.py` compares
        # against the tip on purpose and must keep doing so -- see the companion
        # test below -- because it asks a different question: not "what did M084
        # change" but "has anything touched a frozen path since". Pinning that
        # one would disable the guard.
        for path in ("tools/render_m084_file_audit.py", "tools/render_m084_exhaustion_table.py"):
            offenders = [entry for entry in _code_strings(path) if "..HEAD" in entry[1]]
            assert offenders == [], (path, offenders)

    def test_the_frozen_path_guard_still_compares_against_the_branch_tip(self) -> None:
        # The other half of the pair. If a later cleanup "consistently" pinned
        # this tool too, the frozen-path guard would stop seeing new violations
        # and would keep reporting success.
        source = (_REPO_ROOT / "tools" / "check_frozen_paths.py").read_text(encoding="utf-8")
        assert any(
            isinstance(node, ast.Constant)
            and isinstance(value := node.value, str)
            and value.endswith("..HEAD")
            for node in ast.walk(ast.parse(source))
        )


class TestTheSupportedInterpreterIsCheckedNotAssumed:
    """FIND-F-02, positive and negative."""

    def test_the_supported_version_matches_pyproject(self) -> None:
        # Anti-vacuity: the constant is only meaningful if it still tracks the
        # packaging constraint it claims to mirror.
        requires = next(
            line
            for line in _PYPROJECT.read_text(encoding="utf-8").splitlines()
            if line.startswith("requires-python")
        )
        major, minor = exhaustion.SUPPORTED_PYTHON
        assert f">={major}.{minor}" in requires, requires
        assert f"<{major}.{minor + 1}" in requires, requires

    def test_a_supported_interpreter_is_accepted_and_is_the_running_one(self) -> None:
        assert exhaustion.interpreter() == sys.executable
        assert Path(sys.executable).is_file()

    def test_an_unsupported_interpreter_raises_rather_than_being_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unsupported = (3, 12, 0, "final", 0)
        monkeypatch.setattr(sys, "version_info", unsupported)
        with pytest.raises(exhaustion.UnsupportedInterpreterError) as raised:
            exhaustion.interpreter()
        assert "3.12" in str(raised.value)

    def test_the_error_names_both_versions_so_the_operator_can_act(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
        with pytest.raises(exhaustion.UnsupportedInterpreterError) as raised:
            exhaustion.interpreter()
        message = str(raised.value)
        assert "3.13" in message
        assert "3.9" in message


class TestTheChildEnvironmentIsPlatformNeutral:
    """FIND-F-02. The environment is extended, not replaced."""

    def test_the_repository_is_on_pythonpath(self) -> None:
        assert exhaustion._child_environment()["PYTHONPATH"].startswith(str(_REPO_ROOT))

    def test_an_existing_pythonpath_is_preserved_and_joined_with_os_pathsep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYTHONPATH", "SOMEWHERE_ELSE")
        value = exhaustion._child_environment()["PYTHONPATH"]
        assert value == f"{_REPO_ROOT}{os.pathsep}SOMEWHERE_ELSE"
        # The separator is the platform's, not a hard-coded colon.
        assert os.pathsep in value

    def test_the_parent_environment_is_inherited_rather_than_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("M084_PORTABILITY_PROBE", "present")
        assert exhaustion._child_environment().get("M084_PORTABILITY_PROBE") == "present"

    def test_the_whole_parent_environment_survives(self) -> None:
        # The behavioural half of the negative control: replacing the
        # environment was what made the child unlaunchable on Windows, where
        # `dict(os.environ)` upper-cases its keys, so the comparison is made
        # case-insensitively rather than assuming either casing.
        parent = {name.upper(): value for name, value in os.environ.items()}
        child = {name.upper(): value for name, value in exhaustion._child_environment().items()}
        # PYTHONPATH is the one variable this function is allowed to change.
        assert set(parent) - {"PYTHONPATH"} <= set(child)
        for name, value in parent.items():
            if name != "PYTHONPATH":
                assert child[name] == value, name

    def test_no_posix_only_interpreter_or_path_remains_in_executable_code(self) -> None:
        offenders = [
            entry
            for entry in _code_strings("tools/render_m084_exhaustion_table.py")
            if ".venv313" in entry[1] or "/usr/bin" in entry[1]
        ]
        assert offenders == [], offenders

    def test_that_control_would_fire_on_the_original_defect(self, tmp_path: Path) -> None:
        # Anti-vacuity for the check above: prove the extractor detects the
        # literal when it IS in executable code, so that its silence means
        # something. The probe carries a docstring too, so the exclusion is
        # exercised rather than assumed.
        probe = tmp_path / "probe.py"
        probe.write_text(
            '"""A docstring naming .venv313/bin/python, which must be ignored."""\n'
            'subprocess.run([".venv313/bin/python", "-c", "pass"])\n',
            encoding="utf-8",
        )
        tree = ast.parse(probe.read_text(encoding="utf-8"))
        docstring = tree.body[0]
        assert isinstance(docstring, ast.Expr)
        found = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node is not docstring.value
            and isinstance(node.value, str)
            and ".venv313" in node.value
        ]
        assert found == [".venv313/bin/python"]


class TestAGateActuallyRuns:
    """The point of FIND-F-02: an exit code that is really measured."""

    def test_a_succeeding_gate_reports_success(self) -> None:
        ok, evidence = exhaustion._gate(["-c", "raise SystemExit(0)"], "self-test")()
        assert ok is True
        assert "exit 0" in evidence

    def test_a_failing_gate_reports_failure_with_its_code(self) -> None:
        # Anti-vacuity: a gate that reported success unconditionally would pass
        # the test above and prove nothing.
        ok, evidence = exhaustion._gate(["-c", "raise SystemExit(3)"], "self-test")()
        assert ok is False
        assert "exit 3" in evidence

    def test_the_child_can_import_the_repository_it_is_pointed_at(self) -> None:
        # PYTHONPATH is only useful if it actually reaches the child process.
        ok, _ = exhaustion._gate(
            ["-c", "import tools.render_m084_file_audit; raise SystemExit(0)"],
            "import self-test",
        )()
        assert ok is True

    def test_the_original_vector_is_still_unrunnable_here(self) -> None:
        # FIND-F-02, reproduced rather than described: the exact argument vector
        # the tool used before the correction cannot start a process on this
        # platform. On Windows a missing executable raises rather than returning
        # a code, which is why every gate row died instead of reporting `exit 1`.
        if (_REPO_ROOT / ".venv313" / "bin" / "python").exists():
            pytest.skip("this machine actually has the .venv313 layout the old vector assumed")
        with pytest.raises((FileNotFoundError, NotADirectoryError, PermissionError)):
            subprocess.run(  # noqa: S603 - fixed argument vector, no shell
                [".venv313/bin/python", "-c", "raise SystemExit(0)"],  # noqa: S607
                cwd=_REPO_ROOT,
                capture_output=True,
                check=False,
            )
