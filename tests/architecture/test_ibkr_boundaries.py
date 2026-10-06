from pathlib import Path

from tools.check_architecture import check_path
from tools.check_ibkr_architecture import check_adapter


def test_sdk_exception_is_exact_file_and_module(tmp_path: Path) -> None:
    root = tmp_path / "src/empirical_platform/shared/brokerage"
    root.mkdir(parents=True)
    allowed = root / "ibkr_session.py"
    allowed.write_text("from ibapi.client import EClient\n", encoding="utf-8")
    assert check_path(tmp_path)  # Even this file cannot import SDKs in the core package.
    allowed.write_text("from ibapi.order import Order\n", encoding="utf-8")
    assert check_path(tmp_path)
    allowed.unlink()
    (root / "other.py").write_text("from ibapi.client import EClient\n", encoding="utf-8")
    assert check_path(tmp_path)


def test_optional_adapter_has_a_separate_exact_sdk_boundary(tmp_path: Path) -> None:
    source = tmp_path / "session.py"
    source.write_text("from ibapi.client import EClient\n", encoding="utf-8")
    assert check_adapter(tmp_path) == []
    source.write_text("from ibapi.order import Order\n", encoding="utf-8")
    assert check_adapter(tmp_path)
    assert check_adapter(Path("integrations/ibkr/src/empirical_ibkr")) == []


def test_default_store_resolution_is_absent_from_new_migrations() -> None:
    source = Path("migrations_market_access/env.py").read_text(encoding="utf-8")
    assert "resolve_foundation_config" not in source
    assert 'config.attributes.get("connection")' in source
    assert "require_test_connection(connection)" in source
