"""The historical freeze and the exact authorized operational correction both stay pinned."""

import ast
import json

import pytest
from tools import check_frozen_paths as gate


def test_only_destructive_reset_function_changed() -> None:
    record = json.loads(gate.SAFETY_RECORD.read_text(encoding="utf-8"))
    trees = []
    for path in (record["historical_copy"], gate.SAFETY_TOOL):
        tree = ast.parse((gate.REPO_ROOT / path).read_text(encoding="utf-8"))
        tree.body = [
            node
            for node in tree.body
            if not (isinstance(node, ast.FunctionDef) and node.name == "_rebuild_schema")
        ]
        trees.append(ast.dump(tree))
    assert trees[0] == trees[1], "correction escaped the destructive reset function"


def test_original_manifest_and_archived_tool_remain_historical() -> None:
    record = json.loads(gate.SAFETY_RECORD.read_text(encoding="utf-8"))
    original = gate.base_digests("M084")[gate.SAFETY_TOOL]
    assert original == "".join(record["original_blob"])
    assert gate.blob_id("HEAD", record["historical_copy"]) == original
    corrected = gate.operational_digest(gate.SAFETY_TOOL, original)
    assert corrected != original
    assert gate.blob_id("HEAD", gate.SAFETY_TOOL) == corrected
    assert gate.EXEMPT == frozenset()


def test_further_tool_modification_fails_the_freeze_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    original_blob_id = gate.blob_id

    def tampered(revision: str, path: str) -> str | None:
        if revision == "HEAD" and path == gate.SAFETY_TOOL:
            return "0" * 40
        return original_blob_id(revision, path)

    monkeypatch.setattr(gate, "blob_id", tampered)
    assert gate.SAFETY_TOOL in gate.content_violations()["M084"]


def test_historical_copy_tampering_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    original_blob_id = gate.blob_id

    def tampered(revision: str, path: str) -> str | None:
        if path.endswith("original-tool.py.txt"):
            return "0" * 40
        return original_blob_id(revision, path)

    monkeypatch.setattr(gate, "blob_id", tampered)
    with pytest.raises(ValueError, match="historical evidence changed"):
        gate.content_violations()
