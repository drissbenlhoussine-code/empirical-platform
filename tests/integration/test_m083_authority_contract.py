"""MILESTONE-083 -- structural validation of the canonical authority contract.

Owner finding M083-REV-002: this dedicated suite was absent. It executes the
REAL schema validator (`tools/render_m083_authority.validate`) and the REAL
renderer (`tools/render_m083_authority.render`/`main`) against the committed
contract and schema -- nothing here interprets English or guesses at meaning.
Every check is schema conformance, a closed identifier set, or a byte-exact
comparison.

Numbered comments below correspond to the Owner mission's required attack
list (36 items) so each one can be found by number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "external-review" / "MILESTONE-083"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"

sys.path.insert(0, str(ROOT / "tools"))
import render_m083_authority as renderer  # noqa: E402

# The approved claim sets, written out here so a change to the contract must
# also be a deliberate change to this test (mirrors the M082 authority suite).
APPROVED_PROVES = frozenset(
    {
        "stable_watermark_governance_identity",
        "exact_receipt_governance_id_set_visible_to_capture_statement_snapshot",
        "canonical_deterministic_storage_order",
        "stored_set_stable_against_later_receipt_activity",
        "row_level_update_delete_refused_while_installed_trigger_is_active",
    }
)
APPROVED_DOES_NOT_PROVE = frozenset(
    {
        "research_session_decision_candidate_brief_or_evaluation_consumption",
        "evaluation_time_capture_time_or_wall_clock_chronology",
        "receipt_or_event_commit_time",
        "historical_availability_at_an_arbitrary_cutoff",
        "receipt_ordering_committed_prefix_or_sequence_authority",
        "event_payload_current_or_historical",
        "receipt_metadata_provenance",
        "operator_or_broker_truth_fills_or_trades",
        "every_m076_event_has_a_receipt",
        "an_absent_receipt_did_not_exist_at_another_time",
        "the_set_represents_all_operator_evidence",
        "future_tail_or_excluded_receipt_count",
        "cryptographic_sealing",
        "protection_against_ddl_trigger_disable_truncate_drop_or_superuser",
        "profitability_performance_advice_or_live_trading_readiness",
    }
)
APPROVED_STRUCTURAL_LIMITATIONS = frozenset(
    {
        "row_level_update_delete_refusal_does_not_cover_truncate_drop_or_superuser",
        "no_cryptographic_signature_and_no_monotonicity_enforcement",
        "statement_snapshot_visibility_is_not_prior_commit_visibility",
        "a_crash_between_capture_statement_start_and_commit_leaves_no_partial_row",
        "the_watermark_cannot_report_how_much_evidence_it_excluded",
        "watermark_identity_is_caller_supplied_and_carries_no_chronology_of_its_own",
    }
)
APPROVED_INTENDED_FUTURE_USE = frozenset(
    {
        "future_evaluation_context_milestone_may_bind_a_watermark_to_one_evaluation_not_started",
        "m082_receipt_identity_attestation_is_not_replaced_or_strengthened_by_this_milestone",
    }
)
APPROVED_DATABASE_ENFORCEMENT = {
    "capture_query_overwrites_caller_supplied_membership": True,
    "canonical_deterministic_order": True,
    "empty_set_explicit_not_null": True,
    "row_level_update_delete_refused": True,
    "identity_uniqueness_idempotency": True,
    "ddl_authority_trigger_disable_truncate_drop_superuser": False,
}


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _rejects(contract: dict) -> None:
    with pytest.raises(renderer.SchemaError):
        renderer.validate(contract, _schema())


# --------------------------------------------------------------------------
# 1. Valid contract accepted.
# --------------------------------------------------------------------------


def test_1_the_committed_contract_validates_against_its_committed_schema() -> None:
    renderer.validate(_contract(), _schema())


def test_the_contract_states_exactly_the_approved_claim_sets() -> None:
    contract = _contract()
    assert frozenset(contract["proves"]) == APPROVED_PROVES
    assert frozenset(contract["does_not_prove"]) == APPROVED_DOES_NOT_PROVE
    assert frozenset(contract["structural_limitations"]) == APPROVED_STRUCTURAL_LIMITATIONS
    assert frozenset(contract["intended_future_use"]) == APPROVED_INTENDED_FUTURE_USE
    assert contract["database_enforcement"] == APPROVED_DATABASE_ENFORCEMENT
    assert contract["milestone"] == "M083"
    assert contract["authority_version"] == 1


# --------------------------------------------------------------------------
# AUDIT FINDING M083-AUD-002 -- the SCHEMA's own enum membership must be
# pinned, not only the contract's.
#
# Found by the anti-vacuity mutation campaign: adding a brand-new identifier
# to the schema's `proves` enum was NOT detected by any existing test. The
# tests above pin the CONTRACT (`current-authority.json`) against the
# APPROVED_* constants, and `test_21_to_27` pins seven specific forbidden
# LITERALS -- so widening the schema with any eighth identifier passed
# unnoticed. The schema is the structural gate every other attack test relies
# on; an unpinned gate can be widened in one commit and used in the next,
# with the contract-side tests only noticing at the second step.
#
# These assertions close that direction: the schema's admissible universe and
# the approved sets must be the SAME set, so neither file can drift alone.
# --------------------------------------------------------------------------


def test_the_schema_admits_exactly_the_approved_identifier_universe() -> None:
    schema = _schema()
    properties = schema["properties"]
    for key, approved in (
        ("proves", APPROVED_PROVES),
        ("does_not_prove", APPROVED_DOES_NOT_PROVE),
        ("structural_limitations", APPROVED_STRUCTURAL_LIMITATIONS),
        ("intended_future_use", APPROVED_INTENDED_FUTURE_USE),
    ):
        definition = properties[key]
        assert frozenset(definition["items"]["enum"]) == approved, (
            f"schema `{key}` enum admits a different universe than the approved set; "
            "the schema must not be widened independently of the contract"
        )
        # Closure is only meaningful alongside exact cardinality and uniqueness:
        # an enum of the right members still admits a short or repeated list.
        assert definition["minItems"] == len(approved)
        assert definition["maxItems"] == len(approved)
        assert definition["uniqueItems"] is True

    enforcement = properties["database_enforcement"]
    assert enforcement["additionalProperties"] is False
    assert frozenset(enforcement["required"]) == frozenset(APPROVED_DATABASE_ENFORCEMENT)
    for enforcement_key, approved_value in APPROVED_DATABASE_ENFORCEMENT.items():
        assert enforcement["properties"][enforcement_key]["const"] is approved_value, (
            f"schema pins `{enforcement_key}` to a value other than the approved one"
        )

    assert schema["additionalProperties"] is False
    assert frozenset(schema["required"]) == frozenset(_contract())
    assert properties["authority_version"]["const"] == 1
    assert properties["milestone"]["const"] == "M083"


# --------------------------------------------------------------------------
# 2. Exact generated Markdown accepted.
# --------------------------------------------------------------------------


def test_2_the_generated_document_is_byte_identical_to_the_rendering() -> None:
    assert DOCUMENT.read_text(encoding="utf-8") == renderer.render(_contract())


def test_2b_the_renderer_check_flag_passes_on_the_committed_pair() -> None:
    assert renderer.main(["--check"]) == 0


# --------------------------------------------------------------------------
# 3. authority_version 2 rejected.
# --------------------------------------------------------------------------


def test_3_authority_version_two_is_rejected() -> None:
    contract = _contract()
    contract["authority_version"] = 2
    _rejects(contract)
    # Regenerating the Markdown does not help: the schema refuses the
    # contract before rendering is ever reached (proven, not argued: render()
    # is never called by this test on the mutated contract at all -- the
    # schema is the gate).


# --------------------------------------------------------------------------
# 4/5. Unknown / missing top-level key rejected.
# --------------------------------------------------------------------------


def test_4_unknown_top_level_key_rejected() -> None:
    contract = _contract()
    contract["unexpected_top_level_key"] = "anything"
    _rejects(contract)


@pytest.mark.parametrize(
    "key",
    [
        "milestone",
        "authority_version",
        "title",
        "proves",
        "does_not_prove",
        "database_enforcement",
        "structural_limitations",
        "intended_future_use",
    ],
)
def test_5_missing_top_level_key_rejected(key: str) -> None:
    contract = _contract()
    del contract[key]
    _rejects(contract)


# --------------------------------------------------------------------------
# 6/7/8. Unknown / missing / duplicated positive claim rejected.
# --------------------------------------------------------------------------


def test_6_unknown_positive_claim_rejected() -> None:
    contract = _contract()
    contract["proves"][0] = "invented_positive_claim_same_length_swap"
    _rejects(contract)


def test_7_missing_positive_claim_rejected() -> None:
    contract = _contract()
    contract["proves"].pop()
    _rejects(contract)


def test_8_duplicated_positive_claim_rejected() -> None:
    contract = _contract()
    contract["proves"][1] = contract["proves"][0]
    _rejects(contract)


# --------------------------------------------------------------------------
# 9/10/11. Unknown / missing / duplicated non-claim rejected.
# --------------------------------------------------------------------------


def test_9_unknown_non_claim_rejected() -> None:
    contract = _contract()
    contract["does_not_prove"][0] = "invented_non_claim_same_length_swap"
    _rejects(contract)


def test_10_missing_non_claim_rejected() -> None:
    contract = _contract()
    contract["does_not_prove"].pop()
    _rejects(contract)


def test_11_duplicated_non_claim_rejected() -> None:
    contract = _contract()
    contract["does_not_prove"][1] = contract["does_not_prove"][0]
    _rejects(contract)


# --------------------------------------------------------------------------
# 12/13/14. database_enforcement: unknown key, missing key, wrong value.
# --------------------------------------------------------------------------


def test_12_unknown_database_enforcement_key_rejected() -> None:
    contract = _contract()
    contract["database_enforcement"]["unexpected_enforcement_key"] = True
    _rejects(contract)


@pytest.mark.parametrize("key", sorted(APPROVED_DATABASE_ENFORCEMENT))
def test_13_missing_database_enforcement_key_rejected(key: str) -> None:
    contract = _contract()
    del contract["database_enforcement"][key]
    _rejects(contract)


@pytest.mark.parametrize("key", sorted(APPROVED_DATABASE_ENFORCEMENT))
def test_14_incorrect_enforcement_value_rejected(key: str) -> None:
    contract = _contract()
    contract["database_enforcement"][key] = not APPROVED_DATABASE_ENFORCEMENT[key]
    _rejects(contract)


# --------------------------------------------------------------------------
# 15/16/17. structural_limitations: unknown, missing, duplicated.
# --------------------------------------------------------------------------


def test_15_unknown_structural_limitation_rejected() -> None:
    contract = _contract()
    contract["structural_limitations"][0] = "invented_limitation_same_length_swap"
    _rejects(contract)


def test_16_missing_structural_limitation_rejected() -> None:
    contract = _contract()
    contract["structural_limitations"].pop()
    _rejects(contract)


def test_17_duplicated_structural_limitation_rejected() -> None:
    contract = _contract()
    contract["structural_limitations"][1] = contract["structural_limitations"][0]
    _rejects(contract)


# --------------------------------------------------------------------------
# 18/19/20. intended_future_use: unknown, missing, duplicated.
# --------------------------------------------------------------------------


def test_18_unknown_future_use_identifier_rejected() -> None:
    contract = _contract()
    contract["intended_future_use"][0] = "invented_future_use_same_length_swap"
    _rejects(contract)


def test_19_missing_future_use_identifier_rejected() -> None:
    contract = _contract()
    contract["intended_future_use"].pop()
    _rejects(contract)


def test_20_duplicated_future_use_identifier_rejected() -> None:
    contract = _contract()
    contract["intended_future_use"][1] = contract["intended_future_use"][0]
    _rejects(contract)


# --------------------------------------------------------------------------
# 21-27. Specific forbidden authority classes cannot be smuggled into
# `proves`, because `proves` is a closed enum. Each of these is a concrete,
# named attempt at exactly the authority class the Owner named.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_claim",
    [
        pytest.param(
            "capture_time_or_wall_clock_chronology_authority", id="21-timestamp-capture-time"
        ),
        pytest.param("receipt_label_or_cutoff_authority", id="22-receipt-label-cutoff"),
        pytest.param("sequence_or_committed_prefix_authority", id="23-sequence-committed-prefix"),
        pytest.param("event_payload_authority", id="24-event-payload"),
        pytest.param("receipt_metadata_provenance_authority", id="25-metadata-provenance"),
        pytest.param(
            "immutable_after_persistence", id="26-absolute-immutability-retired-identifier"
        ),
        pytest.param(
            "research_session_decision_candidate_brief_or_evaluation_consumption",
            id="27-existing-evaluation-consumption",
        ),
    ],
)
def test_21_to_27_forbidden_authority_class_cannot_enter_proves(forbidden_claim: str) -> None:
    contract = _contract()
    contract["proves"][0] = forbidden_claim
    _rejects(contract)


# --------------------------------------------------------------------------
# 28/29/30. Markdown/JSON drift, including a deliberately reordered list.
# --------------------------------------------------------------------------


def test_28_json_change_without_regenerating_markdown_is_caught() -> None:
    original = CONTRACT.read_text(encoding="utf-8")
    contract = json.loads(original)
    # A schema-valid mutation: authority_version is frozen at 1, so drift is
    # provoked by reordering a closed set instead (uniqueItems tolerates any
    # order; only the byte-exact document check can catch this).
    contract["does_not_prove"] = list(reversed(contract["does_not_prove"]))
    try:
        CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        assert renderer.main(["--check"]) != 0, "renderer --check accepted a stale document"
    finally:
        CONTRACT.write_text(original, encoding="utf-8")
    assert renderer.main(["--check"]) == 0


def test_29_markdown_only_mutation_is_caught() -> None:
    original = DOCUMENT.read_text(encoding="utf-8")
    try:
        DOCUMENT.write_text(
            original + "\nM083 also proves receipt commit time.\n", encoding="utf-8"
        )
        assert renderer.main(["--check"]) != 0, "renderer --check accepted a drifted document"
    finally:
        DOCUMENT.write_text(original, encoding="utf-8")
    assert renderer.main(["--check"]) == 0


def test_30_reordering_proves_deliberately_changes_the_rendering() -> None:
    """The `proves` list is rendered in list order, so reordering it must
    change the exact document bytes -- proving the byte-exact check is
    actually sensitive to order, not merely to set membership."""
    contract = _contract()
    reordered = dict(contract)
    reordered["proves"] = list(reversed(contract["proves"]))
    renderer.validate(reordered, _schema())  # still schema-valid: same set
    assert renderer.render(reordered) != renderer.render(contract)


# --------------------------------------------------------------------------
# 31/32/33. Runtime JSON/domain field closure and text/JSON agreement.
# --------------------------------------------------------------------------

APPROVED_RUNTIME_JSON_KEYS = frozenset(
    {"banner", "watermark_governance_id", "receipt_governance_ids", "captured_receipt_count"}
)
APPROVED_DOMAIN_FIELDS = frozenset({"watermark_governance_id", "receipt_governance_ids"})
FORBIDDEN_RUNTIME_FIELD_FRAGMENTS = (
    "timestamp",
    "commit_time",
    "recorded_at",
    "event_timestamp",
    "receipt_label",
    "cutoff",
    "sequence",
    "payload",
    "metadata",
    "evaluation",
    "research_session",
    "decision_candidate_id",
    "session_id",
)


def _sample_watermark() -> EvaluationEvidenceWatermark:
    return EvaluationEvidenceWatermark(
        watermark_governance_id="WM-CONTRACT",
        receipt_governance_ids=("RC-A", "RC-B"),
    )


def test_31_runtime_json_exposes_no_key_beyond_the_canonical_contract() -> None:
    from empirical_platform.usecases.evaluation_evidence_watermark_io import (
        render_evaluation_evidence_watermark_json,
    )

    payload = render_evaluation_evidence_watermark_json(_sample_watermark())
    assert frozenset(payload) == APPROVED_RUNTIME_JSON_KEYS
    # Field NAMES (JSON object keys), not the banner's own negation prose,
    # are what must never carry a forbidden fragment -- the banner explicitly
    # SAYS "no timestamp", which is the claim, not a leak of one.
    for key in payload:
        for fragment in FORBIDDEN_RUNTIME_FIELD_FRAGMENTS:
            assert fragment not in key.lower(), f"runtime JSON key {key!r} exposes {fragment!r}"


def test_32_domain_dataclass_exposes_no_field_beyond_the_contract() -> None:
    assert frozenset(EvaluationEvidenceWatermark.__dataclass_fields__) == APPROVED_DOMAIN_FIELDS
    for name in EvaluationEvidenceWatermark.__dataclass_fields__:
        for fragment in FORBIDDEN_RUNTIME_FIELD_FRAGMENTS:
            assert fragment not in name, name


def test_33_text_and_json_renderers_stay_mutually_consistent() -> None:
    from empirical_platform.usecases.evaluation_evidence_watermark_io import (
        render_evaluation_evidence_watermark_json,
        render_evaluation_evidence_watermark_text,
    )

    watermark = _sample_watermark()
    payload = render_evaluation_evidence_watermark_json(watermark)
    text = render_evaluation_evidence_watermark_text(watermark)
    assert payload["watermark_governance_id"] in text
    assert str(payload["captured_receipt_count"]) in text
    for receipt_id in payload["receipt_governance_ids"]:
        assert receipt_id in text


# --------------------------------------------------------------------------
# 34. Retired M082 prose-sweep mechanisms are absent from the M083 renderer.
# M083 never had them; this pins that it never grows them either.
# --------------------------------------------------------------------------


def test_34_no_natural_language_claim_sweep_mechanism_exists() -> None:
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
    text = Path(renderer.__file__).read_text(encoding="utf-8")
    for name in retired:
        assert name not in text, f"render_m083_authority.py defines or uses {name}"


# --------------------------------------------------------------------------
# 35. The validator rejects for the INTENDED rule, not an incidental crash.
# This is the exact REV-001 reproduction: before the schema was closed, an
# invented identifier passed validate() and only failed inside render() with
# a bare KeyError -- a different failure than schema rejection. Prove the
# fix: validate() now raises SchemaError, and render() is never reached.
# --------------------------------------------------------------------------


def test_35_validator_rejects_before_render_is_ever_reached() -> None:
    contract = _contract()
    contract["structural_limitations"][0] = "an_identifier_the_owner_never_wrote"
    rendered = False

    class _RenderTripwireError(Exception):
        pass

    original_render = renderer.render

    def _tripwire(_contract: dict) -> str:
        nonlocal rendered
        rendered = True
        raise _RenderTripwireError("render() must never be reached for an invalid contract")

    renderer.render = _tripwire  # type: ignore[assignment]
    try:
        with pytest.raises(renderer.SchemaError):
            renderer.validate(contract, _schema())
        assert not rendered, "render() ran on a contract that failed validation"
    finally:
        renderer.render = original_render  # type: ignore[assignment]


def test_35b_pre_fix_behaviour_would_have_been_an_incidental_keyerror() -> None:
    """Historical proof the OLD (open-regex) schema shape really did let an
    invented identifier reach render() and crash with a bare KeyError -- the
    exact defect M083-REV-001 describes. This test hard-codes the vulnerable
    OLD schema fragment (not the committed file, which is now closed) so the
    regression is provable without weakening the real committed schema."""
    contract = _contract()
    contract["structural_limitations"] = [*contract["structural_limitations"], "an_invented_one"]
    vulnerable_items_schema = {"type": "string", "pattern": "^[a-z0-9_]+$"}
    vulnerable_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(_schema()["required"]),
        "properties": {
            **_schema()["properties"],
            "structural_limitations": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": vulnerable_items_schema,
            },
        },
    }
    renderer.validate(contract, vulnerable_schema)  # the old shape lets it through
    with pytest.raises(KeyError):
        renderer.render(contract)  # ...and only render() notices, incidentally


# --------------------------------------------------------------------------
# 36. The renderer's write path cannot emit an unvalidated identifier: main()
# without --check must fail (not write a document) for an invalid contract.
# --------------------------------------------------------------------------


def test_36_write_path_refuses_to_emit_for_an_invalid_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_contract_path = tmp_path / "current-authority.json"
    bad_document_path = tmp_path / "current-authority.md"
    contract = _contract()
    contract["structural_limitations"][0] = "unauthorized_identifier"
    bad_contract_path.write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.setattr(renderer, "CONTRACT", bad_contract_path)
    monkeypatch.setattr(renderer, "DOCUMENT", bad_document_path)
    with pytest.raises(renderer.SchemaError):
        renderer.main([])
    assert not bad_document_path.exists(), "an unvalidated identifier reached disk"


# --------------------------------------------------------------------------
# Anti-vacuity campaign: weaken each governing rule, prove the attack then
# passes, restore, prove the attack then fails again. A control that cannot
# fail proves nothing.
# --------------------------------------------------------------------------


def test_each_structural_rule_is_anti_vacuous() -> None:
    # 1. Closed schema -> permissive schema. The attack (an unknown proves
    #    claim) passes under the permissive schema and fails under the real
    #    committed one.
    contract = _contract()
    contract["proves"] = ["an_unauthorized_claim"]
    permissive = {"type": "object"}
    renderer.validate(contract, permissive)  # weakened: the attack passes
    with pytest.raises(renderer.SchemaError):
        renderer.validate(contract, _schema())  # restored: the attack fails

    # 2. Enum closure on structural_limitations -> open regex pattern (the
    #    exact pre-REV-001 shape). The attack passes under the weakened
    #    items schema and fails under the real committed one.
    weakened_items = {"type": "string", "pattern": "^[a-z0-9_]+$"}
    attacked = _contract()
    attacked["structural_limitations"][0] = "an_unauthorized_limitation"
    renderer.validate(
        attacked["structural_limitations"], {"type": "array", "items": weakened_items}
    )
    with pytest.raises(renderer.SchemaError):
        renderer.validate(attacked, _schema())

    # 3. Byte-exact rendering -> substring/containment comparison.
    drifted = renderer.render(_contract()) + "\nM083 also proves receipt commit time.\n"
    assert renderer.render(_contract()) in drifted  # weakened: the attack passes
    assert drifted != renderer.render(_contract())  # restored: the attack fails

    # 4. authority_version const=1 -> no constraint at all.
    versioned = _contract()
    versioned["authority_version"] = 2
    renderer.validate(versioned, {"type": "object"})  # weakened: the attack passes
    with pytest.raises(renderer.SchemaError):
        renderer.validate(versioned, _schema())  # restored: the attack fails


# --------------------------------------------------------------------------
# AUDIT FINDING M083-AUD-003 -- REV-005's architecture correction was not
# protected against silent re-introduction.
#
# Found by the anti-vacuity mutation campaign: re-adding the
# `entrypoints -> decision_candidate` edge that Owner finding REV-005 had
# removed was NOT detected by anything. `test_current_source_tree_respects_
# boundaries` cannot detect it by construction -- GRANTING a permission never
# produces a violation, it only stops producing them -- so the checker still
# exits 0 and the negative fixture still fails as designed.
#
# This pins only the one edge REV-005 was about. It deliberately does NOT
# freeze the whole ALLOWED table: the rest is project-wide architecture policy
# that other milestones must stay free to evolve, and an M083 test has no
# business gating that.
# --------------------------------------------------------------------------


def test_rev_005_entrypoints_may_not_regain_a_direct_decision_candidate_edge() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from check_architecture import ALLOWED  # noqa: PLC0415

    assert "decision_candidate" not in ALLOWED["entrypoints"], (
        "REV-005 removed the entrypoints -> decision_candidate widening; "
        "M083's entrypoints reach the domain type through the already-allowed "
        "`usecases` edge instead. Re-adding this edge would silently undo that "
        "correction without any architecture violation being reported."
    )
    # And the shape REV-005 relies on must still exist, or the removal above
    # would simply be broken rather than correct.
    from empirical_platform.usecases.capture_evaluation_evidence_watermark import (  # noqa: PLC0415
        __all__ as usecase_exports,
    )

    assert "EvaluationEvidenceWatermark" in usecase_exports
