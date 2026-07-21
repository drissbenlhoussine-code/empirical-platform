from pathlib import Path

from tools.check_architecture import check_path


def test_current_source_tree_respects_boundaries() -> None:
    assert check_path(Path.cwd()) == []


def test_negative_fixture_detects_illegal_import() -> None:
    fixture_root = Path("tests/fixtures/illegal_imports")
    violations = check_path(fixture_root)
    assert any("review may not import acquisition" in violation for violation in violations)
    assert any("datasets may not import run" in violation for violation in violations)
    assert any("campaign may not import datasets" in violation for violation in violations)
    assert any("campaign may not import run" in violation for violation in violations)
    assert any("run may not import campaign" in violation for violation in violations)
    assert any("evidence may not import run" in violation for violation in violations)
    assert any("review may not import run" in violation for violation in violations)
    assert any(
        "campaign may not import empirical_platform.shared.persistence" in violation
        for violation in violations
    )
    assert any("review may not import sqlalchemy" in violation for violation in violations)
