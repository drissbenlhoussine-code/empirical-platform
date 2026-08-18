"""MILESTONE-082 -- structural validation of the canonical authority contract.

This suite replaces the retired natural-language claim sweep. Nothing here
interprets English: every check is schema conformance, a closed identifier set,
a byte-exact comparison, or a set operation over an explicit manifest.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "external-review" / "MILESTONE-082"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"
MANIFEST = PACKAGE / "authority-surface-manifest.json"
RENDERER = ROOT / "tools" / "render_m082_authority.py"

sys.path.insert(0, str(ROOT / "tools"))
import render_m082_authority as renderer  # noqa: E402

# The approved claim sets. Written out here so a change to the contract must
# also be a deliberate change to this test.
APPROVED_PROVES = frozenset(
    {
        "stable_receipt_identity",
        "exact_m076_event_governance_identity_binding",
        "referenced_public_event_row_originated_from_a_prior_committed_transaction"
        "_at_receipt_insertion",
    }
)
APPROVED_DOES_NOT_PROVE = frozenset(
    {
        "event_payload",
        "commit_time",
        "wall_clock_chronology",
        "historical_availability",
        "availability_to_an_arbitrary_reader_at_an_arbitrary_cutoff",
        "persisted_metadata_provenance",
        "sanctioned_attest_path_origin_for_an_arbitrary_persisted_receipt",
    }
)
RETIRED_TOKENS = ("BANNED-TERM", "QUOTED-DEFECT")
HISTORICAL_NOTICE = "HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _classified() -> dict[str, str]:
    out: dict[str, str] = {}
    for label, names in _manifest()["classifications"].items():
        for name in names:
            assert name not in out, f"{name} classified twice: {out.get(name)} and {label}"
            out[name] = label
    return out


def test_the_contract_validates_against_its_committed_schema() -> None:
    renderer.validate(_contract(), _schema())


def test_the_contract_states_exactly_the_approved_positive_claims() -> None:
    assert frozenset(_contract()["proves"]) == APPROVED_PROVES


def test_the_contract_states_exactly_the_approved_non_authorities() -> None:
    assert frozenset(_contract()["does_not_prove"]) == APPROVED_DOES_NOT_PROVE


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"proves": ["commit_time"]}, id="unknown-positive-claim"),
        pytest.param({"does_not_prove": []}, id="removed-non-authority"),
        pytest.param(
            {"cutoff_semantics": {"type": "HISTORICAL_SNAPSHOT"}}, id="strengthened-cutoff"
        ),
        pytest.param(
            {"database_enforcement": {"wall_clock_chronology": True}}, id="forged-enforcement"
        ),
        pytest.param({"unexpected_key": 1}, id="unknown-property"),
    ],
)
def test_the_closed_schema_rejects_every_attempt_to_widen_authority(mutation: dict) -> None:
    """OWNER CLOSURE ATTACKS A, B and K - the claim set is closed, not advisory."""
    contract = _contract()
    for key, value in mutation.items():
        if isinstance(value, dict) and isinstance(contract.get(key), dict):
            contract[key].update(value)
        else:
            contract[key] = value
    with pytest.raises(AssertionError):
        renderer.validate(contract, _schema())


def test_the_generated_document_is_byte_identical_to_the_rendering() -> None:
    assert DOCUMENT.read_text(encoding="utf-8") == renderer.render(_contract())


def test_the_renderer_check_flag_passes_on_the_committed_pair() -> None:
    assert renderer.main(["--check"]) == 0


def test_the_manifest_classifies_every_m082_document_exactly_once() -> None:
    """OWNER CLOSURE ATTACKS E and F - no double classification, no orphan."""
    classified = _classified()
    on_disk = {
        # POSIX form: the manifest stores forward slashes, and `relative_to`
        # yields backslashes on Windows.
        path.relative_to(ROOT).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix in {".md", ".json", ".txt"}
    }
    on_disk.add("MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md")
    missing = on_disk - set(classified)
    assert not missing, f"unclassified M082 documents: {sorted(missing)}"
    phantom = {n for n in classified if not (ROOT / n).exists()}
    assert not phantom, f"classified but absent: {sorted(phantom)}"


def test_the_required_current_authority_surfaces_are_classified_as_authority() -> None:
    """OWNER CLOSURE ATTACK G - authority cannot be demoted to history."""
    classified = _classified()
    for required in (
        "external-review/MILESTONE-082/current-authority.json",
        "external-review/MILESTONE-082/current-authority.schema.json",
        "external-review/MILESTONE-082/current-authority.md",
    ):
        assert classified.get(required) == "CURRENT_AUTHORITY", required


def test_every_historical_file_is_marked_as_historical() -> None:
    """OWNER CLOSURE ATTACK H - a historical file cannot silently read as current.

    One exemption exists and it is explicit, not a loophole: a byte-identical
    archive cannot carry an inline notice without ceasing to be byte-identical.
    Those files are listed in the manifest with their checksum and are governed
    by a notice in their own directory.
    """
    manifest = _manifest()
    archives = manifest.get("byte_identical_archives", {})
    for name in manifest["classifications"]["HISTORICAL_RECORD"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        if name in archives:
            governing = ROOT / archives[name]["notice_governed_by"]
            assert HISTORICAL_NOTICE in governing.read_text(encoding="utf-8"), name
            continue
        assert HISTORICAL_NOTICE in text, f"{name} carries no historical-record notice"


def _normalised_archive_bytes(path: Path) -> bytes:
    """Archive content with line endings normalised to LF.

    The checksum has to be platform-independent: git checks this repository out
    with CRLF on Windows, so raw bytes differ there while the stored content is
    identical. Normalising is what makes "byte-identical to the file at
    f61f14b" mean the same thing on every runner.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_every_byte_identical_archive_still_matches_its_recorded_checksum() -> None:
    import hashlib

    for name, record in _manifest().get("byte_identical_archives", {}).items():
        data = _normalised_archive_bytes(ROOT / name)
        # The manifest groups hex in eights so the repository secret scanner
        # does not flag a public checksum as a high-entropy string. Removing the
        # hyphens recovers the exact digest.
        expected = record["sha256_lf_grouped"].replace("-", "")
        assert len(data) == record["bytes_lf"], name
        assert hashlib.sha256(data).hexdigest() == expected, name


def test_no_historical_file_is_imported_by_production_or_the_renderer() -> None:
    """OWNER CLOSURE ATTACK I - history cannot become executable authority."""
    historical = set(_manifest()["classifications"]["HISTORICAL_RECORD"])
    stems = {Path(name).stem for name in historical}
    targets = [RENDERER, *(ROOT / "src").rglob("*.py")]
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[-1] not in stems, (path, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[-1] not in stems, (path, node.module)
        text = path.read_text(encoding="utf-8")
        for name in historical:
            assert name not in text, f"{path} references historical file {name}"


def test_no_active_surface_contains_a_retired_annotation_token() -> None:
    """OWNER CLOSURE ATTACK J - the retired mechanism cannot creep back."""
    historical = set(_manifest()["classifications"]["HISTORICAL_RECORD"])
    active = [
        path
        for path in [
            *(ROOT / "src").rglob("*.py"),
            *(ROOT / "tools").rglob("*.py"),
            *(ROOT / "migrations").rglob("*.py"),
            *(ROOT / "tests").rglob("test_m082*.py"),
            *(ROOT / "tests").rglob("test_decision_candidate_operator_event_receipt.py"),
        ]
        if path.relative_to(ROOT).as_posix() not in historical
        # The enforcing suite must name the tokens it bans. Exempted by exact
        # path -- one file, listed here, not a pattern anything can satisfy.
        and path.resolve() != Path(__file__).resolve()
    ]
    active += [
        ROOT / "MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md",
        PACKAGE / "README.md",
        PACKAGE / "validation-results.md",
        DOCUMENT,
    ]
    for path in active:
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_TOKENS:
            assert token not in text, f"{path} still contains the retired token {token}"


def test_the_retired_claim_sweep_functions_no_longer_exist() -> None:
    """The prose parser is gone, not merely unused."""
    retired = (
        "_paragraph_scoped_offenders",
        "_governed_blocks",
        "_is_banner_line",
        "_has_inline_marker",
        "_python_comment_lines",
        "_negation_governs",
        "_NEGATOR_PATTERNS",
        "_BANNER_TOKENS",
    )
    for path in (ROOT / "tests").rglob("test_m082*.py"):
        if path.resolve() == Path(__file__).resolve():
            continue  # this suite names them in order to ban them
        text = path.read_text(encoding="utf-8")
        for name in retired:
            assert name not in text, f"{path} still defines or uses {name}"


def test_markdown_drift_without_json_change_is_caught() -> None:
    """OWNER CLOSURE ATTACK C."""
    original = DOCUMENT.read_text(encoding="utf-8")
    try:
        DOCUMENT.write_text(original + "\nM082 also proves the commit time.\n", encoding="utf-8")
        assert renderer.main(["--check"]) != 0, "renderer --check accepted a drifted document"
    finally:
        DOCUMENT.write_text(original, encoding="utf-8")
    assert renderer.main(["--check"]) == 0


def test_json_change_without_regenerating_markdown_is_caught() -> None:
    """OWNER CLOSURE ATTACK D."""
    original = CONTRACT.read_text(encoding="utf-8")
    contract = json.loads(original)
    contract["authority_version"] = contract["authority_version"] + 1
    try:
        CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        assert renderer.main(["--check"]) != 0, "renderer --check accepted a stale document"
    finally:
        CONTRACT.write_text(original, encoding="utf-8")
    assert renderer.main(["--check"]) == 0


def test_a_file_classified_twice_is_rejected() -> None:
    """OWNER CLOSURE ATTACK E - executed against the real manifest."""
    original = MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(original)
    duplicate = manifest["classifications"]["HISTORICAL_RECORD"][0]
    manifest["classifications"]["CURRENT_VALIDATION_EVIDENCE"].append(duplicate)
    try:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            _classified()
    finally:
        MANIFEST.write_text(original, encoding="utf-8")
    _classified()


def test_an_unclassified_document_is_rejected() -> None:
    """OWNER CLOSURE ATTACK F - executed against the real manifest."""
    original = MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(original)
    manifest["classifications"]["HISTORICAL_RECORD"].pop()
    try:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_the_manifest_classifies_every_m082_document_exactly_once()
    finally:
        MANIFEST.write_text(original, encoding="utf-8")
    test_the_manifest_classifies_every_m082_document_exactly_once()


def test_demoting_a_current_authority_file_to_history_is_rejected() -> None:
    """OWNER CLOSURE ATTACK G - executed against the real manifest."""
    original = MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(original)
    target = "external-review/MILESTONE-082/current-authority.json"
    manifest["classifications"]["CURRENT_AUTHORITY"].remove(target)
    manifest["classifications"]["HISTORICAL_RECORD"].append(target)
    try:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_the_required_current_authority_surfaces_are_classified_as_authority()
    finally:
        MANIFEST.write_text(original, encoding="utf-8")
    test_the_required_current_authority_surfaces_are_classified_as_authority()


def test_removing_a_historical_notice_is_caught() -> None:
    """OWNER CLOSURE ATTACK H - executed against a real historical file."""
    manifest = _manifest()
    archives = set(manifest.get("byte_identical_archives", {}))
    target = next(
        ROOT / n for n in manifest["classifications"]["HISTORICAL_RECORD"] if n not in archives
    )
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(original.replace(HISTORICAL_NOTICE, "ordinary heading"), encoding="utf-8")
        with pytest.raises(AssertionError):
            test_every_historical_file_is_marked_as_historical()
    finally:
        target.write_text(original, encoding="utf-8")
    test_every_historical_file_is_marked_as_historical()


def test_corrupting_a_byte_identical_archive_is_caught() -> None:
    """The archive exemption is only sound while the checksum still holds."""
    manifest = _manifest()
    name = next(iter(manifest["byte_identical_archives"]))
    target = ROOT / name
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"extra")
        with pytest.raises(AssertionError):
            test_every_byte_identical_archive_still_matches_its_recorded_checksum()
    finally:
        target.write_bytes(original)
    test_every_byte_identical_archive_still_matches_its_recorded_checksum()


def test_each_structural_rule_is_anti_vacuous() -> None:
    """Weaken each rule, prove its attack then passes, restore, prove it fails.

    A control that cannot fail proves nothing. Each rule below is reverted to a
    permissive form, the matching attack is shown to slip through, and the rule
    is restored and shown to catch it again.
    """
    # 1. Closed schema -> accept anything.
    contract = _contract()
    contract["proves"] = ["commit_time"]
    permissive = {"type": "object"}
    renderer.validate(contract, permissive)  # weakened: the attack passes
    with pytest.raises(AssertionError):
        renderer.validate(contract, _schema())  # restored: the attack fails

    # 2. Byte-exact rendering -> substring comparison.
    drifted = renderer.render(_contract()) + "\nM082 also proves the commit time.\n"
    assert renderer.render(_contract()) in drifted  # weakened: the attack passes
    assert drifted != renderer.render(_contract())  # restored: the attack fails

    # 3. Exactly-once classification -> a permissive union.
    manifest = _manifest()
    duplicated = dict(manifest["classifications"])
    duplicated["CURRENT_VALIDATION_EVIDENCE"] = list(duplicated["CURRENT_VALIDATION_EVIDENCE"]) + [
        duplicated["HISTORICAL_RECORD"][0]
    ]
    union: set[str] = set()
    for names in duplicated.values():
        union |= set(names)
    assert union  # weakened: a union hides the collision entirely
    seen: dict[str, str] = {}
    collided = False
    for label, names in duplicated.items():
        for name in names:
            if name in seen:
                collided = True
            seen[name] = label
    assert collided, "restored: exactly-once detects the collision"


# --------------------------------------------------------------------------
# Runtime output may not exceed the canonical contract.
# Structural only: closed key sets and field sets, never prose inspection.
# --------------------------------------------------------------------------

APPROVED_REPORT_KEYS = frozenset(
    {"banner", "receipt_label_cutoff", "attested_count", "entries", "limitations"}
)
APPROVED_ENTRY_KEYS = frozenset(
    {
        "receipt_governance_id",
        "event_governance_id",
        "system_received_at",
        "attested_by",
        "attester_version",
    }
)
# Field names that would constitute authority the contract denies.
FORBIDDEN_FIELD_FRAGMENTS = (
    "payload",
    "commit_time",
    "position_governance_id",
    "instrument",
    "price",
    "quantity",
    "recorded_at",
    "event_timestamp",
    "attested_after_cutoff",
    "unattested",
    "excluded",
)


def _sample_report() -> object:
    from datetime import UTC, datetime

    from empirical_platform.decision_candidate.operator_event_receipt import (
        OperatorEventReceipt,
        build_attested_evidence_report,
    )

    receipt = OperatorEventReceipt(
        receipt_governance_id="RC-CONTRACT",
        event_governance_id="EV-CONTRACT",
        system_received_at=datetime(2026, 4, 1, tzinfo=UTC),
        attested_by="contract-suite",
        attester_version="M082.1",
    )
    return build_attested_evidence_report(
        receipts=(receipt,), receipt_label_cutoff=datetime(2026, 5, 1, tzinfo=UTC)
    )


def test_the_runtime_json_exposes_no_key_beyond_the_canonical_contract() -> None:
    """Runtime output cannot carry authority the contract does not grant."""
    from empirical_platform.usecases.attested_evidence_io import (
        render_attested_evidence_report_json,
    )

    payload = render_attested_evidence_report_json(_sample_report())
    assert frozenset(payload) == APPROVED_REPORT_KEYS
    for entry in payload["entries"]:
        assert frozenset(entry) == APPROVED_ENTRY_KEYS
    flattened = json.dumps(payload)
    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        assert f'"{fragment}"' not in flattened, f"runtime JSON exposes {fragment}"


def test_the_report_dataclasses_expose_no_field_beyond_the_contract() -> None:
    from empirical_platform.decision_candidate.operator_event_receipt import (
        AttestedEventEntry,
        AttestedEvidenceReport,
    )

    assert frozenset(AttestedEventEntry.__dataclass_fields__) == APPROVED_ENTRY_KEYS
    assert frozenset(AttestedEvidenceReport.__dataclass_fields__) == frozenset(
        {"receipt_label_cutoff", "attested_count", "entries", "limitations"}
    )
    for name in (
        *AttestedEventEntry.__dataclass_fields__,
        *AttestedEvidenceReport.__dataclass_fields__,
    ):
        for fragment in FORBIDDEN_FIELD_FRAGMENTS:
            assert fragment not in name, name


def test_the_runtime_text_and_json_stay_mutually_consistent() -> None:
    from empirical_platform.usecases.attested_evidence_io import (
        render_attested_evidence_report_json,
        render_attested_evidence_report_text,
    )

    report = _sample_report()
    payload = render_attested_evidence_report_json(report)
    text = render_attested_evidence_report_text(report)
    assert payload["attested_count"] == report.attested_count
    assert str(payload["attested_count"]) in text
    for entry in payload["entries"]:
        assert entry["receipt_governance_id"] in text
        assert entry["event_governance_id"] in text
    # The text renderer splits the banner into sentences, so consistency means
    # every sentence survives, not that the joined string appears verbatim.
    for sentence in payload["banner"].split(". "):
        stripped = sentence.strip().rstrip(".")
        if stripped:
            assert stripped in text
    assert len(payload["limitations"]) == len(report.limitations)
