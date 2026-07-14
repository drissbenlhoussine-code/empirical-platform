from pathlib import Path

from tools.check_architecture import check_path


def test_current_source_tree_respects_boundaries() -> None:
    assert check_path(Path.cwd()) == []


def test_negative_fixture_detects_illegal_import() -> None:
    fixture_root = Path("tests/fixtures/illegal_imports")
    violations = check_path(fixture_root)
    assert violations
    assert "review may not import acquisition" in violations[0]
