"""Owner-authorized exact compatibility baseline; historical M084 claims stay intact."""

import json
from pathlib import Path

import pytest
from tools import check_frozen_paths as guard


def test_exact_risk_correction_preserves_historical_blobs() -> None:
    record = json.loads(guard.RISK_RECORD.read_text())
    assert len(record["files"]) == 5
    assert guard.EXEMPT == frozenset()
    historical = guard.base_digests("M084")
    for path, archive in guard.RISK_ARCHIVES.items():
        assert guard.blob_id("HEAD", archive) == historical[path]
        assert guard.operational_digest(path, historical[path]) == guard.blob_id("HEAD", path)
        assert guard.blob_id("HEAD", path) != historical[path]


@pytest.mark.parametrize("path", list(guard.RISK_ARCHIVES))
def test_future_mutation_is_not_cleared(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    real = guard.blob_id
    monkeypatch.setattr(
        guard, "blob_id", lambda revision, p: "f" * 40 if p == path else real(revision, p)
    )
    assert path in guard.content_violations()["M084"]


@pytest.mark.parametrize("corruption", ["original", "scope", "archive", "corrected"])
def test_invalid_correction_fails_closed(
    corruption: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = json.loads(guard.RISK_RECORD.read_text())
    path = next(iter(guard.RISK_ARCHIVES))
    item = record["files"][path]
    if corruption == "original":
        item["original_blob"] = ["f" * 8] * 5
    elif corruption == "scope":
        record["files"]["another.py"] = item
    elif corruption == "archive":
        item["historical_copy"] = "another.py"
    else:
        item["corrected_blob"] = item["original_blob"]
    target = tmp_path / "baseline.json"
    target.write_text(json.dumps(record))
    monkeypatch.setattr(guard, "RISK_RECORD", target)
    with pytest.raises(ValueError):
        guard.operational_digest(path, guard.base_digests("M084")[path])
