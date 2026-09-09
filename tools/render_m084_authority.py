"""Render the M084 current-authority document from its canonical contract.

The contract in `current-authority.json` is the ONLY source of M084 authority.
This tool validates it against the committed JSON Schema and renders
`current-authority.md` deterministically from it.

    python tools/render_m084_authority.py            # write the document
    python tools/render_m084_authority.py --check    # fail if it has drifted

There is no prose interpretation anywhere in this tool. It reads structured
identifiers from a closed set and emits fixed sentences for them; an identifier
the schema does not allow cannot reach the document at all. This mirrors
`tools/render_m083_authority.py` deliberately: M082's owner findings 20-28
retired natural-language claim validation in favour of exactly this closed,
machine-readable shape, and M083 and M084 start from that shape rather than
re-deriving it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.render_m083_authority import validate

PACKAGE = Path(__file__).resolve().parent.parent / "external-review" / "MILESTONE-084"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"

_PROVES = {
    "one_versioned_operator_configuration_governing_one_evaluation": (
        "the one versioned operator configuration that governed the evaluation, "
        "named by identity and version"
    ),
    "one_evaluation_context_bound_to_exactly_one_persisted_m083_watermark": (
        "one evaluation context bound to exactly one PERSISTED MILESTONE-083 "
        "evidence watermark, by foreign key -- a context for a watermark that "
        "does not exist cannot be stored"
    ),
    "the_receipt_count_and_set_digest_read_from_the_loaded_watermark_not_from_the_caller": (
        "a consumed-receipt count and set digest READ FROM the loaded watermark's "
        "own stored set, neither of which the caller can supply or overstate"
    ),
    "deterministic_single_reason_no_trade_or_one_proposal_from_one_input_set": (
        "that one input set yields either exactly one proposal or exactly one "
        "closed NO_TRADE reason, selected by explicit precedence and reproducible "
        "across runs"
    ),
    "quantity_price_and_risk_verdict_derived_by_the_engine_never_supplied_by_the_caller": (
        "that quantity, entry price and every risk verdict were DERIVED by the "
        "engine -- none of the three is a parameter it accepts"
    ),
    "one_fingerprint_binding_one_approval_to_one_exact_set_of_order_terms": (
        "one SHA-256 fingerprint binding an approval to one exact set of order "
        "terms, so a changed quantity, price, symbol, order type or expiry cannot "
        "inherit an older approval"
    ),
    "order_terms_immutable_after_insert_with_status_the_only_mutable_column": (
        "that a stored proposal's order terms cannot be edited afterwards -- "
        "`status` is the only column any statement may change"
    ),
    "a_closed_proposal_state_machine_in_which_only_prepared_has_outgoing_edges": (
        "a closed proposal state machine in which only PREPARED has outgoing "
        "edges and every other status is terminal"
    ),
    "at_most_one_explicit_human_decision_per_proposal": (
        "at most one explicit decision per proposal, naming the operator who made "
        "it, admitted only while the proposal was still PREPARED"
    ),
    "at_most_one_order_intent_per_proposal_derived_from_that_decision": (
        "at most one order intent per proposal, whose terms the database "
        "re-derives from that proposal and that decision at insert"
    ),
    "every_stored_intent_is_not_submitted_and_no_transition_away_from_it_exists": (
        "that every stored intent is NOT_SUBMITTED, and that this milestone "
        "provides no transition away from NOT_SUBMITTED -- not in code, where no "
        "method exists, and not in the database, where a CHECK constraint and an "
        "append-only trigger both refuse it"
    ),
    "no_module_of_the_package_imports_an_order_submission_dependency": (
        "that no module of the package imports a client capable of placing, "
        "modifying or cancelling an order, enforced statically across every "
        "module rather than a named subset"
    ),
}

_DOES_NOT_PROVE = {
    "that_an_asserted_quote_account_or_session_matches_what_the_market_or_broker_showed": (
        "that an asserted quote, account balance or session status matches what "
        "the market or a broker actually showed -- every market input is an "
        "operator assertion this milestone records and range-checks, never verifies"
    ),
    "that_the_m082_receipts_behind_the_watermark_describe_anything_historically_true": (
        "that the MILESTONE-082 receipts behind the bound watermark describe "
        "anything historically true"
    ),
    "profitability_expected_return_or_advice": (
        "profitability, expected return, or advice of any kind"
    ),
    "fillability_liquidity_at_the_proposed_price_or_execution_quality": (
        "fillability, liquidity at the proposed price, or execution quality"
    ),
    "broker_acceptance_of_the_intent_or_of_its_terms": (
        "that any broker would accept the intent or its terms"
    ),
    "that_an_approved_intent_was_will_be_or_can_be_sent_to_any_venue": (
        "that an approved intent was, will be, or can be sent to any venue"
    ),
    "paper_or_live_trading_readiness": "paper-trading or live-trading readiness",
    "regulatory_tax_or_reporting_compliance": (
        "regulatory, tax or reporting compliance in any jurisdiction"
    ),
    "protection_against_ddl_trigger_disable_truncate_drop_or_superuser": (
        "protection against DDL authority, `ALTER TABLE ... DISABLE TRIGGER`, "
        "TRUNCATE, DROP, or a superuser"
    ),
    "cryptographic_sealing_against_an_attacker_with_database_write_access": (
        "cryptographic sealing against a determined attacker with database write access"
    ),
    "any_wall_clock_chronology_beyond_the_instants_the_caller_supplied": (
        "any wall-clock chronology beyond the instants the caller supplied"
    ),
    "that_a_proposal_absent_from_the_table_was_never_evaluated": (
        "that an instrument absent from the proposal table was never evaluated -- "
        "a NO_TRADE writes nothing"
    ),
}

_ENFORCEMENT = {
    "unleveraged_long_only_intraday_preparation_mode_configuration_only": (
        "Only an unleveraged, long-only, intraday, PREPARATION-mode configuration is storable"
    ),
    "order_terms_immutable_after_insert": "A stored proposal's order terms cannot be changed",
    "closed_proposal_state_machine_on_update": (
        "Only PREPARED has outgoing transitions; every other status is terminal"
    ),
    "decision_admitted_only_against_a_prepared_proposal_with_a_matching_fingerprint": (
        "A decision is admitted only against a still-PREPARED proposal, with that "
        "proposal's current fingerprint and version"
    ),
    "one_decision_per_proposal": "At most one decision exists per proposal",
    "one_intent_per_proposal": "At most one order intent exists per proposal",
    "intent_terms_re_derived_from_the_proposal_and_decision_at_insert": (
        "An intent's terms are re-checked against the proposal and decision it cites"
    ),
    "submission_state_restricted_to_not_submitted": (
        "`submission_state` accepts only NOT_SUBMITTED"
    ),
    "decisions_intents_and_risk_check_evidence_append_only": (
        "Decisions, intents and risk-check evidence refuse row-level UPDATE and DELETE"
    ),
    "evaluation_context_requires_an_existing_watermark_row": (
        "An evaluation context requires an existing MILESTONE-083 watermark row"
    ),
    "ddl_authority_trigger_disable_truncate_drop_superuser": (
        "DDL authority, `DISABLE TRIGGER`, TRUNCATE, DROP, superuser"
    ),
}

_LIMITATIONS = {
    "row_level_refusals_do_not_cover_truncate_drop_disable_trigger_or_superuser": (
        "Row-level UPDATE/DELETE refusal is exactly that. TRUNCATE is "
        "statement-level and a row trigger does not intercept it; DROP TABLE, "
        "DROP TRIGGER, `ALTER TABLE ... DISABLE TRIGGER`, "
        "`session_replication_role = replica` and superuser mutation all remain "
        "possible. This must not be described as absolute database immutability."
    ),
    "market_inputs_are_operator_asserted_and_are_never_verified_against_a_venue": (
        "Market inputs are operator-asserted. This milestone connects to no "
        "broker and no market-data vendor: a human writes the observations down, "
        "and the platform records and range-checks them without verifying them."
    ),
    "the_fingerprint_is_a_change_detector_not_a_cryptographic_seal": (
        "The content fingerprint is a change detector and an approval binding. It "
        "is not a signature and offers no protection against an attacker who can "
        "write to the database."
    ),
    "risk_check_evidence_is_excluded_from_the_fingerprint_by_design": (
        "Risk-check evidence is stored but deliberately excluded from the "
        "fingerprint: a proposal that moves from PREPARED to APPROVED is the same "
        "order, and making the digest depend on diagnostic text would break that."
    ),
    "a_no_trade_is_not_persisted_so_the_tables_do_not_record_every_evaluation": (
        "A NO_TRADE is returned and not persisted, so these tables are not a "
        "record of every evaluation that was performed."
    ),
    "the_engine_reads_no_clock_and_every_instant_it_records_was_supplied_to_it": (
        "The engine reads no clock. Every instant it records was supplied by its "
        "caller, and the record carries no independent evidence of when anything "
        "happened."
    ),
    "the_liquidation_deadline_check_compares_local_times_not_an_exchange_calendar": (
        "The liquidation-deadline check compares local times in the operator's "
        "configured timezone. It consults no exchange calendar and knows nothing "
        "of holidays or shortened sessions; `exchange_calendar_policy` records "
        "which policy the operator believes applies, and enforces nothing."
    ),
}

_FUTURE = {
    "a_future_milestone_may_submit_an_intent_to_a_paper_account_it_is_not_started": (
        "A future milestone may submit an intent to a paper account. It is not started."
    ),
    "such_a_milestone_must_add_a_submission_state_transition_in_the_open_because_none_exists": (
        "Such a milestone must add a submission-state transition explicitly, in "
        "the open, because none exists here to inherit."
    ),
    (
        "m083_watermark_authority_is_consumed_by_this_milestone_"
        "and_is_neither_replaced_nor_strengthened"
    ): (
        "MILESTONE-083's watermark authority is CONSUMED by this milestone and is "
        "neither replaced nor strengthened by it."
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
        "This document is the single active statement of what MILESTONE-084 "
        "establishes. Every other file in this package is either current "
        "validation evidence or historical record, and neither carries authority."
    )
    add("")
    add("## What one approved order intent proves")
    add("")
    add("One intent, and the records it is derived from, together establish:")
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
