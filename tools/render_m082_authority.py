"""Render the M082 current-authority document from its canonical contract.

The contract in `current-authority.json` is the ONLY source of M082 authority.
This tool validates it against the committed JSON Schema and renders
`current-authority.md` deterministically from it.

    python tools/render_m082_authority.py            # write the document
    python tools/render_m082_authority.py --check    # fail if it has drifted

There is no prose interpretation anywhere in this tool. It reads structured
identifiers from a closed set and emits fixed sentences for them; an identifier
the schema does not allow cannot reach the document at all.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent.parent / "external-review" / "MILESTONE-082"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"


class SchemaError(AssertionError):
    """The contract does not satisfy the committed schema."""


def validate(instance: object, schema: dict[str, object], where: str = "$") -> None:
    """Validate against the subset of JSON Schema the contract actually uses.

    Deliberately dependency-free and deliberately strict: every keyword below is
    enforced, and `additionalProperties: false` plus closed `enum`/`const` are
    what make an unknown claim identifier impossible rather than merely unusual.
    """
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
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaError(f"{where}: below minimum {schema['minimum']}")
    elif expected == "string":
        if not isinstance(instance, str):
            raise SchemaError(f"{where}: expected a string")
        pattern = schema.get("pattern")
        if pattern and not re.fullmatch(pattern, instance):
            raise SchemaError(f"{where}: {instance!r} does not match {pattern!r}")


# Fixed sentences for the closed identifier sets. An identifier with no sentence
# here is a programming error, not a rendering fallback.
_PROVES = {
    "stable_receipt_identity": "a stable receipt identity",
    "exact_m076_event_governance_identity_binding": (
        "a binding to one exact M076 event governance identity"
    ),
    "referenced_public_event_row_originated_from_a_prior_committed_transaction"
    "_at_receipt_insertion": (
        "that the referenced `public` event row originated from a **prior committed "
        "transaction** at receipt insertion"
    ),
}
_DOES_NOT_PROVE = {
    "event_payload": "the event payload, current or historical",
    "commit_time": "the event's commit time",
    "wall_clock_chronology": "any wall-clock chronology",
    "historical_availability": "historical availability",
    "availability_to_an_arbitrary_reader_at_an_arbitrary_cutoff": (
        "availability to an arbitrary reader at an arbitrary cutoff"
    ),
    "persisted_metadata_provenance": "the provenance of persisted metadata",
    "sanctioned_attest_path_origin_for_an_arbitrary_persisted_receipt": (
        "that an arbitrary persisted receipt came through the sanctioned `attest()` path"
    ),
}
_SANCTIONED = {
    "application_clock_call_issued_causally_after_committed_read_back": (
        "the application clock CALL is issued causally after the committed read-back; "
        "the value it returns proves no chronology"
    ),
    "application_constant": "an application constant",
    "caller_supplied_and_passed_through": "caller-supplied and passed through unchanged",
}
_ENFORCEMENT = {
    "event_foreign_key": "the referenced event exists",
    "prior_committed_transaction_origin": (
        "the referenced event came from a prior committed transaction"
    ),
    "one_receipt_per_event": "exactly one receipt per event",
    "event_delete_restricted": "receipt evidence cannot vanish with its event",
    "row_update_delete_immutability": "row-level UPDATE/DELETE immutability",
    "non_blank_identity_and_metadata": "non-blank receipt identity and metadata",
    "metadata_provenance": "the provenance of persisted metadata",
    "wall_clock_chronology": "any wall-clock chronology",
}
_CUTOFF = {
    "RECEIPT_LABEL_FILTER_ONLY": (
        "The cutoff is a **receipt-label filter only**. It selects receipts whose label is "
        "at or before the cutoff, and asserts nothing else."
    ),
    "historical_knowledge_authority": "carries historical knowledge authority",
    "future_tail_counts": "emits future-tail counts",
    "event_payload_enrichment": "enriches entries with event payload",
}
_LIMITATIONS = {
    "row_update_delete_immutability_does_not_cover_truncate_drop_or_superuser": (
        "Row immutability is row-level UPDATE/DELETE only. TRUNCATE, DROP and a superuser "
        "remain outside it."
    ),
    "no_cryptographic_signature_and_no_monotonicity_enforcement": (
        "No cryptographic signature and no monotonicity enforcement. This is not a trusted "
        "timestamping service."
    ),
    "postgresql_commit_timestamps_are_unavailable_and_not_used": (
        "PostgreSQL commit timestamps are unavailable here and are not used."
    ),
    "repeated_evaluation_at_the_same_cutoff_can_change_because_a_label_can_be_backdated": (
        "Repeated evaluation at the same cutoff can change, because a label can be backdated."
    ),
    "a_crash_between_event_commit_and_receipt_insertion_leaves_an_unattested_gap": (
        "A crash between event commit and receipt insertion leaves an unattested gap."
    ),
    "the_view_cannot_report_how_much_evidence_it_excluded": (
        "The view cannot report how much evidence it excluded, and offers no count of it."
    ),
}
_FUTURE = {
    "evidence_watermark_milestone_may_bind_an_evaluation_to_an_explicitly_persisted_receipt_set": (
        "A future evidence-watermark milestone may bind an evaluation to an explicitly "
        "persisted receipt set. It is not started."
    ),
    "m079_recorded_at_firewall_is_not_replaced_by_this_milestone": (
        "M079's `recorded_at` firewall is **not** replaced by this milestone."
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
        "This document is the single active statement of what MILESTONE-082 establishes. "
        "Every other file in this package is either current validation evidence or "
        "historical record, and neither carries authority."
    )
    add("")
    add("## What a persisted receipt proves")
    add("")
    add("A persisted receipt binds:")
    add("")
    for key in contract["proves"]:
        add(f"- {_PROVES[key]};")
    add("")
    add("## What it does not prove")
    add("")
    for key in contract["does_not_prove"]:
        add(f"- **Not** {_DOES_NOT_PROVE[key]}.")
    add("")
    add("## Metadata provenance")
    add("")
    meta = contract["metadata_authority"]
    add(
        f"As a **generic persisted value**, receipt metadata has "
        f"**{meta['generic_persisted_value'].replace('_', ' ')}**. A direct SQL receipt for a "
        "genuinely prior-committed event is accepted by design and may carry any allowed value."
    )
    add("")
    add("On the sanctioned `attest()` path only:")
    add("")
    for field in ("system_received_at", "attester_version", "attested_by"):
        add(f"- `{field}` — {_SANCTIONED[meta['sanctioned_attest_path'][field]]};")
    add("")
    add("## Cutoff semantics")
    add("")
    add(_CUTOFF[contract["cutoff_semantics"]["type"]])
    add("")
    for key in ("historical_knowledge_authority", "future_tail_counts", "event_payload_enrichment"):
        state = "does" if contract["cutoff_semantics"][key] else "does **not**"
        add(f"- It {state} {_CUTOFF[key]}.")
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
