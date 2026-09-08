"""Render the M083 current-authority document from its canonical contract.

The contract in `current-authority.json` is the ONLY source of M083 authority.
This tool validates it against the committed JSON Schema and renders
`current-authority.md` deterministically from it.

    python tools/render_m083_authority.py            # write the document
    python tools/render_m083_authority.py --check    # fail if it has drifted

There is no prose interpretation anywhere in this tool. It reads structured
identifiers from a closed set and emits fixed sentences for them; an
identifier the schema does not allow cannot reach the document at all. This
mirrors `tools/render_m082_authority.py` deliberately: M082's owner findings
20-28 retired natural-language claim validation in favour of exactly this
closed, machine-readable shape, and M083 starts from that shape rather than
re-deriving it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent.parent / "external-review" / "MILESTONE-083"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"


class SchemaError(AssertionError):
    """The contract does not satisfy the committed schema."""


def validate(instance: object, schema: dict[str, object], where: str = "$") -> None:
    """Validate against the subset of JSON Schema the contract actually uses."""
    if "const" in schema and instance != schema["const"]:
        raise SchemaError(f"{where}: expected {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaError(f"{where}: {instance!r} is not one of {schema['enum']!r}")

    expected = schema.get("type")
    if expected == "object":
        if not isinstance(instance, dict):
            raise SchemaError(f"{where}: expected an object")
        for key in schema.get("required", []):
            if key not in instance:
                raise SchemaError(f"{where}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    raise SchemaError(f"{where}: unknown property {key!r}")
        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], f"{where}.{key}")
    elif expected == "array":
        if not isinstance(instance, list):
            raise SchemaError(f"{where}: expected an array")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaError(f"{where}: expected at least {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaError(f"{where}: expected at most {schema['maxItems']} items")
        if schema.get("uniqueItems") and len(instance) != len({json.dumps(i) for i in instance}):
            raise SchemaError(f"{where}: items must be unique")
        for index, item in enumerate(instance):
            validate(item, schema.get("items", {}), f"{where}[{index}]")
    elif expected == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            raise SchemaError(f"{where}: expected an integer")
    elif expected == "string":
        if not isinstance(instance, str):
            raise SchemaError(f"{where}: expected a string")
        pattern = schema.get("pattern")
        if pattern and not re.fullmatch(pattern, instance):
            raise SchemaError(f"{where}: {instance!r} does not match {pattern!r}")


_PROVES = {
    "stable_watermark_governance_identity": "a stable watermark governance identity",
    "exact_receipt_governance_id_set_visible_to_capture_statement_snapshot": (
        "the EXACT set of M082 `receipt_governance_id` values visible to the "
        "schema-qualified capture query, under that one statement's own "
        "PostgreSQL transaction snapshot"
    ),
    "canonical_deterministic_storage_order": (
        'that set stored once, in deterministic canonical (`COLLATE "C"`) order'
    ),
    "stored_set_stable_against_later_receipt_activity": (
        "that the stored set does not change when a later receipt or event is "
        "inserted -- reading an existing watermark reads its stored set only "
        "and never re-consults the current receipt inventory"
    ),
    "row_level_update_delete_refused_while_installed_trigger_is_active": (
        "that ordinary row-level UPDATE and DELETE against this watermark's row "
        "are refused by the installed trigger -- a narrower guarantee than "
        "absolute database immutability; it does NOT cover TRUNCATE, DROP, "
        "disabling the trigger, or superuser mutation (see `does_not_prove` and "
        "`structural_limitations`)"
    ),
}
_DOES_NOT_PROVE = {
    "research_session_decision_candidate_brief_or_evaluation_consumption": (
        "that any ResearchSession, DecisionCandidate, brief or evaluation consumed this watermark"
    ),
    "evaluation_time_capture_time_or_wall_clock_chronology": (
        "evaluation time, capture time, or any wall-clock chronology"
    ),
    "receipt_or_event_commit_time": "receipt commit time or event commit time",
    "historical_availability_at_an_arbitrary_cutoff": (
        "historical availability at an arbitrary timestamp or cutoff"
    ),
    "receipt_ordering_committed_prefix_or_sequence_authority": (
        "receipt ordering, a committed prefix, or any sequence authority"
    ),
    "event_payload_current_or_historical": "event payload, current or historical",
    "receipt_metadata_provenance": "receipt metadata provenance",
    "operator_or_broker_truth_fills_or_trades": ("operator truth, broker truth, fills or trades"),
    "every_m076_event_has_a_receipt": "that every M076 event has a receipt",
    "an_absent_receipt_did_not_exist_at_another_time": (
        "that an absent receipt did not exist at another time"
    ),
    "the_set_represents_all_operator_evidence": ("that the set represents all operator evidence"),
    "future_tail_or_excluded_receipt_count": "any future-tail or excluded-receipt count",
    "cryptographic_sealing": "cryptographic sealing",
    "protection_against_ddl_trigger_disable_truncate_drop_or_superuser": (
        "protection against DDL authority, trigger disabling, TRUNCATE, DROP or superuser mutation"
    ),
    "profitability_performance_advice_or_live_trading_readiness": (
        "profitability, performance, advice or live-trading readiness"
    ),
}
_ENFORCEMENT = {
    "capture_query_overwrites_caller_supplied_membership": (
        "the trigger-computed set unconditionally replaces any caller-supplied "
        "`receipt_governance_ids`"
    ),
    "canonical_deterministic_order": "deterministic canonical storage order",
    "empty_set_explicit_not_null": "an explicit empty array, never NULL, for zero receipts",
    "row_level_update_delete_refused": "row-level UPDATE/DELETE refusal",
    "identity_uniqueness_idempotency": (
        "idempotent capture by watermark identity, with one immutable winner under concurrent retry"
    ),
    "ddl_authority_trigger_disable_truncate_drop_superuser": (
        "DDL authority, trigger disabling, TRUNCATE, DROP or superuser mutation"
    ),
}
_LIMITATIONS = {
    "row_level_update_delete_refusal_does_not_cover_truncate_drop_or_superuser": (
        "Row-level UPDATE/DELETE refusal does not cover TRUNCATE, DROP, or a superuser."
    ),
    "no_cryptographic_signature_and_no_monotonicity_enforcement": (
        "No cryptographic signature and no monotonicity enforcement."
    ),
    "statement_snapshot_visibility_is_not_prior_commit_visibility": (
        "Statement-snapshot visibility is NOT prior-commit visibility: a receipt "
        "inserted earlier in the SAME transaction as the capture is included even "
        "though it has not committed."
    ),
    "a_crash_between_capture_statement_start_and_commit_leaves_no_partial_row": (
        "A crash or rollback between the capture statement's start and its commit "
        "leaves no partial row -- the whole row is produced inside one statement."
    ),
    "the_watermark_cannot_report_how_much_evidence_it_excluded": (
        "The watermark cannot report how much evidence it excluded, and offers no count of it."
    ),
    "watermark_identity_is_caller_supplied_and_carries_no_chronology_of_its_own": (
        "The watermark governance identity is caller-supplied and carries no chronology of its own."
    ),
}
_FUTURE = {
    "future_evaluation_context_milestone_may_bind_a_watermark_to_one_evaluation_not_started": (
        "A future evaluation-context milestone may bind a watermark to one "
        "evaluation. It is not started."
    ),
    "m082_receipt_identity_attestation_is_not_replaced_or_strengthened_by_this_milestone": (
        "M082's receipt identity attestation is **not** replaced or strengthened by this milestone."
    ),
}


def render(contract: dict[str, Any]) -> str:
    """Deterministic Markdown for one validated contract."""
    out: list[str] = []
    add = out.append
    add(f"# {contract['milestone']} — {contract['title']}")
    add("")
    add(
        f"**Current authority, version {contract['authority_version']}.** "
        "Generated from `current-authority.json`; do not edit by hand."
    )
    add("")
    add(
        "This document is the single active statement of what MILESTONE-083 "
        "establishes. Every other file in this package is either current "
        "validation evidence or historical record, and neither carries authority."
    )
    add("")
    add("## What a persisted watermark proves")
    add("")
    add("One persisted watermark row binds:")
    add("")
    for key in contract["proves"]:
        add(f"- {_PROVES[key]};")
    add("")
    add("## What it does not prove")
    add("")
    for key in contract["does_not_prove"]:
        add(f"- **Not** {_DOES_NOT_PROVE[key]}.")
    add("")
    add("## Database enforcement")
    add("")
    add("| Property | Enforced |")
    add("|---|---|")
    for key, description in _ENFORCEMENT.items():
        enforced = "**yes**" if contract["database_enforcement"][key] else "**no**"
        add(f"| {description} | {enforced} |")
    add("")
    add("## Structural limitations")
    add("")
    for key in contract["structural_limitations"]:
        add(f"- {_LIMITATIONS[key]}")
    add("")
    add("## Intended future use")
    add("")
    for key in contract["intended_future_use"]:
        add(f"- {_FUTURE[key]}")
    add("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the document has drifted")
    args = parser.parse_args(argv)

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    validate(contract, json.loads(SCHEMA.read_text(encoding="utf-8")))
    expected = render(contract)

    if args.check:
        actual = DOCUMENT.read_text(encoding="utf-8") if DOCUMENT.exists() else ""
        if actual != expected:
            print(f"{DOCUMENT} is not the deterministic rendering of {CONTRACT}", file=sys.stderr)
            return 1
        print("current-authority.md matches current-authority.json")
        return 0

    DOCUMENT.write_text(expected, encoding="utf-8")
    print(f"wrote {DOCUMENT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
