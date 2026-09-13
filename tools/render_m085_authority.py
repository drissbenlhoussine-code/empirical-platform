"""Render the M085 current-authority document from its canonical contract.

The contract in `current-authority.json` is the ONLY source of M085 authority.
This tool validates it against the committed JSON Schema and renders
`current-authority.md` deterministically from it.

    python tools/render_m085_authority.py            # write the document
    python tools/render_m085_authority.py --check    # fail if it has drifted

THERE IS NO PROSE INTERPRETATION ANYWHERE IN THIS TOOL. It maps structured
identifiers from a closed set onto fixed sentences; an identifier the schema does
not allow cannot reach the document at all, because validation happens first and
because every lookup below is a dictionary access that raises on a key it does not
have. No keyword sweep, no banned-term list, no negation grammar, no natural
language is parsed -- M082's owner findings 20 through 28 produced eight
consecutive green prose sweeps each defeated by the next review, and that pattern
retired prose validation for this repository. M083, M084 and now M085 start from
the closed shape instead of re-deriving it.

WHY THE MAPS ARE EXHAUSTIVE RATHER THAN DEFAULTED. Each of the five tables below
must name EVERY identifier its section of the contract can hold, and a test
asserts that the table keys and the schema enums are equal sets. A `.get(key, "")`
would let a claim render as a blank line, which is how a claim gets published with
no statement of what it means.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.render_m083_authority import validate

PACKAGE = Path(__file__).resolve().parent.parent / "external-review" / "MILESTONE-085"
CONTRACT = PACKAGE / "current-authority.json"
SCHEMA = PACKAGE / "current-authority.schema.json"
DOCUMENT = PACKAGE / "current-authority.md"

_PROVES: dict[str, str] = {
    "one_persisted_m084_intent_is_dispatchable_at_most_once_to_the_paper_environment": (
        "that ONE persisted MILESTONE-084 approved order intent may be dispatched to "
        "the Alpaca paper environment AT MOST ONCE, enforced by a unique constraint "
        "rather than by a convention"
    ),
    "dispatch_requires_a_fresh_explicit_expiring_single_use_human_authorization": (
        "that a dispatch happens only after a FRESH, EXPLICIT, EXPIRING, SINGLE-USE "
        "human authorization -- there is no code path that produces one by default, by "
        "timeout, or by the absence of an objection"
    ),
    "one_authorization_binds_one_request_fingerprint_one_paper_account_and_one_client_order_id": (
        "that one authorization binds ONE request fingerprint, ONE paper account "
        "reference and ONE client order id together, so it cannot be replayed against "
        "different order terms or a different account"
    ),
    "the_client_order_id_is_derived_from_persisted_identity_and_never_generated": (
        "that the broker-facing order identity is DERIVED from persisted identity by a "
        "pure function, so a retry, a crash, a second worker and a reconciliation all "
        "compute the same value and address the same order"
    ),
    "the_dispatch_claim_is_committed_before_any_network_request_is_made": (
        "that the dispatch claim is committed to PostgreSQL BEFORE any network request, "
        "so an order cannot exist at the broker with nothing persisted to prove it"
    ),
    "a_duplicate_dispatch_request_returns_the_persisted_winner_and_sends_nothing": (
        "that a duplicate dispatch request returns the persisted winning attempt and "
        "sends NOTHING -- the loser is handed the winner rather than an error, because a "
        "caller given an error is a caller that may retry"
    ),
    "an_ambiguous_outcome_becomes_submission_unknown_and_never_a_second_order": (
        "that a request which MAY have been delivered becomes SUBMISSION_UNKNOWN, a "
        "state whose closed transition table has no edge back into submission, so an "
        "ambiguous dispatch can be resolved but never retried into a second order"
    ),
    "reconciliation_addresses_the_original_client_order_id_under_a_bounded_not_found_policy": (
        "that reconciliation asks the broker about the ORIGINAL client order id, and "
        "that a single not-found answer does not resolve an unknown outcome -- the "
        "policy requires repeated observations and elapsed time, and is published"
    ),
    "the_order_endpoint_is_pinned_to_one_paper_host_and_every_redirect_is_refused": (
        "that orders can reach exactly one host, that HTTP, userinfo, an alternative "
        "host, an IP literal, a non-canonical port, a path, a query and a fragment are "
        "each refused, and that every redirect is refused rather than followed"
    ),
    "every_broker_answer_is_validated_field_by_field_against_the_request_that_was_sent": (
        "that a broker acknowledgement is compared field by field against the request "
        "that was sent -- client order id, symbol, side, quantity and order type -- and a "
        "mismatch fails closed instead of being persisted"
    ),
    "the_execution_state_machine_is_closed_and_mirrored_by_a_database_trigger": (
        "that the execution state machine is closed, that its edges are mirrored by a "
        "database trigger, and that the two are compared across every ordered pair of "
        "states so they cannot drift"
    ),
    "the_m084_approved_intent_is_read_and_never_rewritten": (
        "that the MILESTONE-084 intent is READ and never rewritten: its submission "
        "state is still NOT_SUBMITTED after a dispatch, because M085 records execution "
        "in its own tables keyed by the intent's identity"
    ),
    "no_credential_reaches_a_domain_type_a_database_row_a_renderer_or_an_audit_record": (
        "that no broker credential reaches a domain type, a database row, a renderer or "
        "an audit record, and that a credential echoed back by a peer is scrubbed out "
        "of the stored response body"
    ),
}

_DOES_NOT_PROVE: dict[str, str] = {
    "live_trading_readiness": "live-trading readiness of any kind",
    "eligibility_for_an_alpaca_live_account": "eligibility for an Alpaca live account",
    "that_paper_behaviour_equals_live_behaviour": (
        "that paper behaviour equals live behaviour. Alpaca's own documentation lists "
        "what paper does not model: market impact, information leakage, latency "
        "slippage, queue position for non-marketable limit orders, price improvement, "
        "regulatory fees and dividends"
    ),
    "profitability_or_expected_return": "profitability or expected return",
    "fillability_or_liquidity_at_the_limit_price": (
        "fillability, or that any liquidity existed at the limit price"
    ),
    "execution_quality_or_the_absence_of_slippage": (
        "execution quality, or the absence of slippage"
    ),
    "venue_truth_beyond_what_the_alpaca_paper_endpoint_returned": (
        "anything about a venue beyond what the Alpaca paper endpoint returned"
    ),
    "market_input_truth_beyond_the_iex_quote_that_was_actually_read": (
        "market-input truth beyond the IEX quote that was actually read. The paper "
        "entitlement is IEX only, which is one venue's book and not the consolidated "
        "tape"
    ),
    "any_chronology_derived_from_identifiers": (
        "any chronology derived from an identifier. A governance identity is caller "
        "supplied and carries no ordering"
    ),
    "unattended_or_scheduled_authorization": (
        "unattended or scheduled authorization. Nothing here can create an "
        "authorization without a person"
    ),
    "approval_through_silence_timeout_retry_or_the_absence_of_rejection": (
        "approval arising from silence, a timeout, a retry, a restart, malformed input, "
        "operator error or an ambiguous broker response"
    ),
    "approval_of_more_than_one_exact_intent_version": (
        "approval of more than one exact intent version"
    ),
    "permission_to_trade_options_crypto_shorts_or_leveraged_positions": (
        "permission to trade options, crypto, shorts or leveraged positions. The "
        "request type cannot express any of them"
    ),
    "protection_against_a_database_owner_ddl_a_disabled_trigger_or_a_superuser": (
        "protection against a database owner, DDL, a disabled trigger, TRUNCATE, DROP "
        "or a superuser. Those are outside the enforcement boundary and two tests "
        "EXECUTE the hole rather than describing it"
    ),
    "cryptographic_non_repudiation_of_a_human_authorization": (
        "cryptographic non-repudiation of a human authorization. The record is a "
        "database row, not a signature"
    ),
    "recovery_of_an_unknown_broker_outcome_without_reconciliation": (
        "recovery of an unknown broker outcome without reconciliation"
    ),
    "that_an_order_was_not_accepted_merely_because_the_client_timed_out": (
        "that an order was not accepted merely because the client timed out"
    ),
    "that_cancellation_guarantees_no_fill_occurred": (
        "that a cancellation guarantees no fill occurred. A cancel request races the "
        "venue and can lose, which is why the model has a CANCEL_REQUESTED to FILLED "
        "edge"
    ),
    "that_a_paper_acknowledgement_is_a_real_market_execution": (
        "that a paper acknowledgement is a real-market execution"
    ),
}

_ENFORCEMENT: dict[str, str] = {
    "single_use_authorization_consumption": (
        "An authorization can be consumed exactly once, and never un-consumed"
    ),
    "authorization_immutable_apart_from_its_consumption": (
        "Nothing about an authorization may change except its consumption"
    ),
    "expired_authorization_cannot_be_consumed": (
        "An authorization cannot be consumed after its expiry instant"
    ),
    "at_most_one_consumed_authorization_per_intent": (
        "At most one authorization per intent may ever be spent"
    ),
    "at_most_one_dispatch_attempt_per_intent": "At most one dispatch attempt exists per intent",
    "unique_deterministic_client_order_id": (
        "No two attempts can address one broker order identity"
    ),
    "an_attempt_requires_a_consumed_matching_authorization": (
        "An attempt requires an authorization that is consumed, names it, and matches "
        "its intent, fingerprint and client order id"
    ),
    "an_attempt_must_be_inserted_as_dispatch_claimed": (
        "An attempt cannot be inserted already submitted"
    ),
    "closed_execution_state_machine_on_update": (
        "Only the closed transition table's edges are permitted, and a terminal state is terminal"
    ),
    "attempt_identity_immutable_after_the_claim": (
        "An attempt's intent, authorization, client order id, fingerprint and claim "
        "instant cannot change after the claim"
    ),
    "append_only_previews_accounts_acknowledgements_events_and_kill_switch": (
        "Previews, account snapshots, broker acknowledgements, audit events and the "
        "kill switch refuse UPDATE and DELETE"
    ),
    "paper_environment_and_endpoint_host_pinned_by_check_constraint": (
        "A row describing a non-paper environment or any other endpoint host cannot be stored"
    ),
    "long_only_whole_share_day_only_no_extended_hours_by_check_constraint": (
        "A preview describing a sell, a non-positive quantity, a non-DAY time in force "
        "or extended hours cannot be stored"
    ),
    "referential_integrity_to_the_m084_intent_by_trigger": (
        "A paper row naming an intent that does not exist is refused"
    ),
    "bounded_broker_response_payload": (
        "A stored broker response body is bounded, so a hostile peer cannot grow the "
        "audit table without limit"
    ),
}

_LIMITATIONS: dict[str, str] = {
    "row_level_refusals_do_not_cover_truncate_drop_a_disabled_trigger_or_a_superuser": (
        "The row-level refusals are ROW-LEVEL UPDATE/DELETE refusals under the "
        "installed triggers only. TRUNCATE is statement-level and not intercepted, and "
        "DROP TRIGGER, DROP TABLE, ALTER TABLE ... DISABLE TRIGGER, "
        "`session_replication_role = replica` and a superuser all remain outside the "
        "boundary. This must not be described as absolute database immutability."
    ),
    "the_quote_feed_is_iex_only_and_is_not_the_consolidated_tape": (
        "The quote feed available to this paper entitlement is IEX only. A quote read "
        "here describes one venue's book at one instant and is not the consolidated "
        "tape."
    ),
    "the_request_fingerprint_is_a_change_detector_not_a_cryptographic_seal": (
        "The request fingerprint is a change detector, not a cryptographic seal. It "
        "detects a changed order; it does not prove who authorized one."
    ),
    "a_rejected_or_expired_intent_cannot_be_re_dispatched_in_this_milestone": (
        "Because exactly one attempt may exist per intent, a rejected or expired "
        "dispatch cannot be retried in this milestone. A new attempt requires a new "
        "MILESTONE-084 intent. This is deliberate and is the safe direction to err in."
    ),
    "a_truncate_of_the_m084_intent_table_can_orphan_paper_rows": (
        "Referential integrity to the MILESTONE-084 intent is a trigger rather than a "
        "foreign key, because a foreign key made M084's own test fixture inexecutable. "
        "A TRUNCATE of `approved_order_intent`, which requires table ownership, can "
        "therefore leave paper rows referring to an intent that is gone."
    ),
    "an_unmapped_broker_status_leaves_the_state_unchanged_and_requires_an_operator": (
        "The broker-status map is closed. A status Alpaca returns that it does not name "
        "is recorded and leaves the state unchanged, which requires an operator to look "
        "-- deliberately, rather than guessing which known state it meant."
    ),
    "the_bounded_not_found_reconciliation_policy_is_a_stated_choice_not_a_proof": (
        "The bounded not-found reconciliation policy -- repeated observations plus "
        "elapsed time before an unknown outcome is resolved -- is a stated, reviewable "
        "CHOICE. It is not a proof that the order never existed."
    ),
    "the_external_paper_submission_was_measured_blocked_by_quote_staleness": (
        "The bounded external paper submission was MEASURED BLOCKED, not completed. The "
        "market was closed, the only available IEX quote was over three hours old, and "
        "the freshness tolerance was not widened to get past it. Every local, database "
        "and hostile-adapter validation is unaffected; see "
        "`paper-acceptance-results.md` for the measured numbers."
    ),
    "the_account_reference_is_a_digest_so_two_accounts_are_only_distinguishable_not_identifiable": (
        "The paper account is stored as a stable digest, not an account number. Two "
        "accounts are distinguishable from each other but no account is identifiable "
        "from the stored value -- which is the intent, and also a limit on what an "
        "auditor can do with it alone."
    ),
}

_FUTURE: dict[str, str] = {
    "extended_hours_execution_requires_its_own_separate_authorization": (
        "Extended-hours execution is refused here and requires its own separate "
        "authorization in a future milestone."
    ),
    "live_execution_requires_its_own_separate_authorization_and_is_not_implied_here": (
        "Live execution requires its own separate authorization. Nothing in this "
        "milestone implies it, and the environment type has no live member to select."
    ),
    "unattended_or_scheduled_dispatch_is_authorized_by_nothing_in_this_milestone": (
        "Unattended or scheduled dispatch is authorized by nothing in this milestone."
    ),
}


def render(contract: dict[str, Any]) -> str:
    out: list[str] = []

    def add(line: str) -> None:
        out.append(line)

    add(f"# MILESTONE-{contract['milestone'][1:]} — Current Authority")
    add("")
    add(f"**{contract['title']}**")
    add("")
    add(
        "Generated by `tools/render_m085_authority.py` from `current-authority.json`; "
        "do not edit by hand."
    )
    add(
        "The contract is validated against `current-authority.schema.json`, whose "
        "enumerations are closed and"
    )
    add(
        "whose list lengths are exact, so a claim this document does not already name "
        "cannot be added"
    )
    add("without changing the schema, and a claim removed from it fails the item counts.")
    add("")
    add(f"Authority version `{contract['authority_version']}`.")
    add("")
    add("## What it proves")
    add("")
    add("One authorization, one dispatch, and the records they leave establish:")
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

    # newline="\n" so the rendering is the same bytes on Windows and on POSIX.
    DOCUMENT.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {DOCUMENT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
