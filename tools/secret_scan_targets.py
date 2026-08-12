"""Discover repository files that must be scanned for secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_MAX_SCAN_COMMAND_LENGTH = 28_000

_BENIGN_HIGH_ENTROPY_LINE_PATTERNS = (
    re.compile(r"^[+-]?Revision ID: [0-9a-f]{12}$"),
    re.compile(r"^[+-]?Revises: [0-9a-f]{12}$"),
    re.compile(r'^[+-]?revision: str = "[0-9a-f]{12}"$'),
    re.compile(r'^[+-]?down_revision: str \| None = "[0-9a-f]{12}"$'),
    re.compile(r'^New migration `[0-9a-f]{12}` \(`down_revision = "[0-9a-f]{12}"`\):'),
    re.compile(r'^[+-]?_EXPECTED_SHA256 = "[0-9a-f]{64}"$'),
    re.compile(r'^[+-]?_EXPECTED_DATASET_SHA256 = "[0-9a-f]{64}"$'),
    re.compile(r'^[+-]?_EXPECTED_MANIFEST_HASH = "[0-9a-f]{64}"$'),
    re.compile(r'^[+-]?\s*"dataset_bundle_sha256": "[0-9a-f]{64}",?$'),
    re.compile(r'^[+-]?\s*"membership_manifest_hash": "[0-9a-f]{64}"$'),
)


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


def build_secret_scan_subprocess_env() -> dict[str, str]:
    """Return a child-process environment that won't inherit coverage hooks."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }


def _batch_targets_for_detect_secrets(
    targets: list[str],
    *,
    max_command_length: int = DEFAULT_MAX_SCAN_COMMAND_LENGTH,
) -> list[list[str]]:
    """Split scan targets into stable batches that fit inside Windows command
    length limits."""
    command_prefix_length = len(" ".join([sys.executable, "-m", "detect_secrets", "scan"]))
    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_length = command_prefix_length

    for target in targets:
        target_length = len(target) + 1
        if current_batch and current_length + target_length > max_command_length:
            batches.append(current_batch)
            current_batch = [target]
            current_length = command_prefix_length + target_length
            continue
        current_batch.append(target)
        current_length += target_length

    if current_batch:
        batches.append(current_batch)

    return batches


def scan_targets_for_secrets(
    root: Path,
    targets: list[str],
    *,
    max_command_length: int = DEFAULT_MAX_SCAN_COMMAND_LENGTH,
) -> dict[str, Any]:
    """Run detect-secrets across all targets, batching if necessary, and merge
    the JSON results."""
    merged_results: dict[str, list[dict[str, Any]]] = {}
    env = build_secret_scan_subprocess_env()

    for batch in _batch_targets_for_detect_secrets(targets, max_command_length=max_command_length):
        result = subprocess.run(  # noqa: S603 - toolchain helper invokes current Python with fixed args.
            [sys.executable, "-m", "detect_secrets", "scan", *batch],  # noqa: S607
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        findings = json.loads(result.stdout)["results"]
        for path, entries in findings.items():
            merged_results.setdefault(path, []).extend(entries)

    return {"results": _filter_benign_secret_findings(root, merged_results)}


def _filter_benign_secret_findings(
    root: Path,
    findings: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Drop findings that match known benign migration-revision documentation
    patterns, keeping all other results intact."""
    filtered: dict[str, list[dict[str, Any]]] = {}

    for relative_path, entries in findings.items():
        kept_entries: list[dict[str, Any]] = []
        for entry in entries:
            if _is_known_benign_secret_finding(root, relative_path, entry):
                continue
            kept_entries.append(entry)
        if kept_entries:
            filtered[relative_path] = kept_entries

    return filtered


def _is_known_benign_secret_finding(
    root: Path,
    relative_path: str,
    entry: dict[str, Any],
) -> bool:
    if entry.get("type") != "Hex High Entropy String":
        return False
    line_number = entry.get("line_number")
    if not isinstance(line_number, int) or line_number <= 0:
        return False
    line = _read_line(root / relative_path, line_number)
    if line is None:
        return False
    return any(pattern.search(line) for pattern in _BENIGN_HIGH_ENTROPY_LINE_PATTERNS)


def _read_line(path: Path, line_number: int) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if line_number > len(lines):
        return None
    return lines[line_number - 1]


def main() -> int:
    """Print one scan target per line, or emit merged scan JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument(
        "--scan-json",
        action="store_true",
        help="run detect-secrets over all discovered targets and emit merged JSON",
    )
    args = parser.parse_args()
    root = Path(args.root)
    targets = discover_secret_scan_targets(root)
    if args.scan_json:
        print(json.dumps(scan_targets_for_secrets(root, targets), sort_keys=True))
        return 0
    for target in targets:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
