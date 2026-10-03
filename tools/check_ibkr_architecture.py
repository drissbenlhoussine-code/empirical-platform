"""Audit the separately packaged optional adapter without weakening frozen core rules."""

import ast
from pathlib import Path

from tools.check_architecture import ORDER_SUBMISSION_PREFIXES

ALLOWED = {
    "session.py": {"ibapi.client", "ibapi.wrapper"},
    "paper.py": {"ibapi.contract", "ibapi.execution", "ibapi.order", "ibapi.order_cancel"},
}


def check_adapter(root: Path) -> list[str]:
    violations = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            )
            for name in names:
                forbidden = any(
                    name == p or name.startswith(p + ".") for p in ORDER_SUBMISSION_PREFIXES
                )
                if forbidden and name not in ALLOWED.get(path.relative_to(root).as_posix(), set()):
                    violations.append(f"{path.name}: unauthorized SDK import {name}")
                if name.startswith("empirical_platform.shared.persistence") or name.startswith(
                    "empirical_platform.usecases"
                ):
                    violations.append(f"{path.name}: adapter cannot own governance or persistence")
    return violations


if __name__ == "__main__":
    errors = check_adapter(Path("integrations/ibkr/src/empirical_ibkr"))
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
