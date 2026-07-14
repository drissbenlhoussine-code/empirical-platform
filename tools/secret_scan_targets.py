"""Discover repository files that must be scanned for secrets."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _git_paths(root: Path, *args: str) -> list[str]:
    result = subprocess.run(  # noqa: S603 - toolchain helper invokes Git with fixed args.
        ["git", *args, "-z"],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    )
    if not result.stdout:
        return []
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def discover_secret_scan_targets(root: Path) -> list[str]:
    """Return tracked and relevant untracked files, excluding ignored/local artifacts."""
    root = root.resolve()
    tracked = _git_paths(root, "ls-files")
    untracked = _git_paths(root, "ls-files", "--others", "--exclude-standard")
    seen: set[str] = set()
    targets: list[str] = []

    for candidate in [*tracked, *untracked]:
        normalized = candidate.replace("\\", "/")
        path = root / normalized
        if normalized in seen or not path.is_file():
            continue
        seen.add(normalized)
        targets.append(normalized)

    targets.sort()
    if not targets:
        raise RuntimeError("secret scan target discovery returned no files")
    return targets


def main() -> int:
    """Print one scan target per line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args()
    for target in discover_secret_scan_targets(Path(args.root)):
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
