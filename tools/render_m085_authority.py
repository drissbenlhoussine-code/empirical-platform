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

THE RENDERED-MEANING DIGEST (authority version 2; review finding AUTH-1). The five
tables ARE the meaning of the identifiers, and until version 2 nothing bound them to
the contract: a sentence could be rewritten materially while `current-authority.json`
stayed byte-identical, and the document would re-render "from the contract" with a
different meaning. At `832b20b..673394e` exactly that happened to
`reconciliation_addresses_the_original_client_order_id_under_a_bounded_not_found_policy`.
The canonical contract therefore now carries `rendered_meaning_digest`: the SHA-256 of
the five tables (identifier -> sentence, canonical JSON, sorted keys), written as an
integer so that no hex token exists for the secret scanner to mistake. The schema pins
it as a `const`; this tool refuses to render, and `--check` fails, when the tables do
not digest to the value the contract declares. A material change of meaning is thereby
a visible change to the canonical contract and to its schema, never a renderer-only
edit. New guarantees get NEW identifiers; an existing identifier's sentence is not
widened to carry them.
"""

from __future__ import annotations

import argparse
import hashlib
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
    "every_reconciliation_network_attempt_is_a_durable_round_begun_before_its_network_work": (
        "that every reconciliation network attempt is a ROUND whose row is inserted and "
        "committed BEFORE the broker clock is sampled or the order is looked up, so a "
        "round that dies, raises or fails to record its answer is still visible as begun "
        "and incomplete -- and if the round cannot be begun, no lookup runs at all"
    ),
    "rounds_are_ordered_by_a_durable_per_attempt_sequence_never_by_reconciler_wall_clocks": (
        "that reconciliation rounds are ordered ONLY by a per-attempt sequence allocated "
        "in the database, never by a timestamp written by a reconciler's wall clock, so "
        "two hosts with skewed clocks cannot reorder a failure relative to the not-found "
        "answers around it"
    ),
    "a_failed_unusable_found_or_incomplete_round_ends_the_qualifying_not_found_run": (
        "that the qualifying run is the trailing consecutive run of COMPLETED not-found "
        "rounds in sequence order, and that a FAILED, UNUSABLE or FOUND round, or a round "
        "still incomplete, ends it -- a lookup that raised is completed FAILED and is never "
        "given a fabricated HTTP status"
    ),
    "absence_resolution_requires_unknown_and_no_bound_order_observation_found_or_open_round": (
        "that absence-based terminal resolution applies only to a SUBMISSION_UNKNOWN "
        "attempt with no bound broker order, no positive observation of its identity, no "
        "completed FOUND round and no incomplete round -- each of those keeps the attempt "
        "visible and reconcilable instead, and a bound or observed order is never revoked "
        "by absence"
    ),
    "absence_resolution_requires_two_completed_not_found_rounds_and_sixty_broker_seconds": (
        "that absence-based terminal resolution further requires at least TWO qualifying "
        "completed not-found rounds and a justified, conservative lower bound of at least "
        "SIXTY seconds of BROKER time between the anchor round and the current round"
    ),
    "waiting_interval_is_current_broker_earliest_minus_anchor_broker_latest_never_wall_clocks": (
        "that the waiting interval is `current.broker_earliest_at - anchor.broker_latest_at`, "
        "both endpoints being broker clock readings widened by the measuring process's own "
        "round trip and the anchor being the first completed round after the uncertain "
        "dispatch -- never `broker_now - host_submitted_at`, never a difference between two "
        "reconcilers' wall clocks, and never a monotonic value carried across processes"
    ),
    "missing_contradictory_or_incompatible_round_or_time_evidence_keeps_the_outcome_unresolved": (
        "that missing, contradictory or incompatible round or time evidence -- no anchor, "
        "no later completed round carrying an interval, a broker reading earlier than the "
        "anchor's, or acknowledgements without rounds -- keeps the outcome UNRESOLVED "
        "rather than defaulting any value"
    ),
    "absence_finalisation_revalidates_fresh_evidence_under_the_attempt_lock_not_a_snapshot": (
        "that the terminal absence write happens ONLY inside the repository, which locks "
        "the attempt row, re-reads the rounds, acknowledgements and events in that same "
        "transaction, re-evaluates the same pure policy on them and requires the exact "
        "round set the caller judged -- a stale snapshot, and any fresh evidence against "
        "the decision, returns without writing; no broker call happens inside that "
        "transaction"
    ),
    "round_sequence_allocation_holds_the_attempt_row_lock_so_a_race_waits_instead_of_colliding": (
        "that a round's sequence is allocated while holding the attempt row lock, so a "
        "racing reconciler WAITS and receives the next sequence instead of colliding on "
        "the unique constraint or duplicating a number"
    ),
    "the_order_endpoint_is_pinned_to_one_paper_host_and_every_redirect_is_refused": (
        "that orders can reach exactly one host, that HTTP, userinfo, an alternative "
        "host, an IP literal, a non-canonical port, a path, a query and a fragment are "
        "each refused, and that every redirect is refused rather than followed"
    ),
    "every_broker_answer_is_validated_field_by_field_against_the_request_that_was_sent": (
        "that a broker order view is compared field by field against the authorized "
        "request -- client order id, symbol, side, quantity, order type, the limit price "
        "where the order has one (and its absence where it has none), time in force and "
        "extended hours, plus the already bound broker order id where the attempt has one "
        "-- that a field the broker did not report is a mismatch and is never substituted, "
        "that a mismatch fails closed instead of being persisted, and that an order found "
        "by reconciliation is adopted only when the broker client's account is the "
        "authorized one"
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
    "each_m084_deadline_is_translated_only_through_the_basis_of_the_act_that_wrote_it": (
        "that each MILESTONE-084 deadline is placed on the broker's clock ONLY "
        "through the broker time basis measured in the act that wrote it -- the "
        "proposal's expiry and liquidation deadline through the evaluation's, the "
        "approval's expiry through the decision's -- and never through a basis "
        "measured later, so host clock drift between evaluation, approval, issuance "
        "and dispatch cannot extend any of them"
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
    "that_the_broker_never_accepted_an_order_the_bounded_absence_policy_resolved_as_rejected": (
        "that the broker never accepted an order which the bounded absence policy "
        "resolved as REJECTED / NOT_FOUND_AT_BROKER. The policy is a local, bounded, "
        "published choice over the evidence this product could gather -- not broker "
        "truth -- and it grants no permission to send again: the intent's single "
        "dispatch is spent"
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
    "time_basis_evidence_describes_the_exact_proposal_approval_or_intent_by_trigger": (
        "Time-basis evidence naming a proposal, approval or intent that does not "
        "exist, or describing different deadlines than the stored record, is refused"
    ),
    "time_basis_evidence_is_bound_to_the_instant_of_its_own_act_by_check_constraint": (
        "Time-basis evidence whose host reading is not the instant of the act it "
        "describes -- evaluation, decision or issuance -- cannot be stored"
    ),
    "time_basis_evidence_is_append_only_and_never_backfilled": (
        "Time-basis evidence refuses UPDATE and DELETE, and no migration writes any"
    ),
    "a_reconciliation_round_begins_incomplete_by_trigger": (
        "A reconciliation round cannot be inserted already completed, with an "
        "acknowledgement sequence, or with a broker clock interval"
    ),
    "a_round_is_bound_to_its_attempt_intent_authorization_and_client_order_id_by_trigger": (
        "A reconciliation round must name an attempt that exists and carry that "
        "attempt's own intent, authorization and client order id"
    ),
    "unique_reconciliation_round_sequence_per_attempt": (
        "No two reconciliation rounds of one attempt can hold the same sequence"
    ),
    "a_reconciliation_round_identity_is_immutable_by_trigger": (
        "A reconciliation round's id, attempt, intent, authorization, client order id, "
        "account reference, sequence and start instant cannot change"
    ),
    "a_round_is_completed_exactly_once_and_only_to_a_completed_outcome_by_trigger": (
        "A reconciliation round may be updated only from incomplete to a completed "
        "outcome with its completion instant, and a completed round refuses every "
        "further update"
    ),
    "reconciliation_rounds_refuse_delete": "Reconciliation rounds refuse DELETE",
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
    "the_waiting_interval_assumes_a_monotone_broker_clock_not_evidence_of_processing": (
        "The waiting interval ASSUMES that the broker's clock advances monotonically "
        "between rounds (a reading that contradicts this yields no interval), and it "
        "treats a broker clock sample as ordering evidence only: a sample says nothing "
        "about whether the broker finished processing any order. The database checks the "
        "interval's shape and pairing, not that the clock was actually read."
    ),
    "legacy_acknowledgements_without_rounds_are_operator_evidence_and_never_count": (
        "Attempts reconciled before the round journal existed carry acknowledgements but "
        "no rounds. Those acknowledgements are operator evidence and never rounds: no time "
        "basis is fabricated and no round history is invented for them, so resolving such "
        "an attempt requires two new completed rounds with justified broker time."
    ),
    "the_external_paper_submission_completed_once_unfilled_and_canceled": (
        "The bounded external paper submission was MEASURED COMPLETED, not blocked: the "
        "order was dispatched, acknowledged by the broker (`pending_new`), cancellation "
        "was requested immediately, and reconciliation observed a terminal broker state "
        "of CANCELED with a filled quantity of zero. This is a single occurrence and is "
        "not a proof of fillability, repeatability, or of any latency, queueing or "
        "execution-quality property; see `paper-acceptance-results.md` for the measured "
        "numbers. The earlier 2026-09-10 MEASURED BLOCKED run remains recorded in git "
        "history and is not restated here."
    ),
    "the_account_reference_is_a_digest_so_two_accounts_are_only_distinguishable_not_identifiable": (
        "The paper account is stored as a stable digest, not an account number. Two "
        "accounts are distinguishable from each other but no account is identifiable "
        "from the stored value -- which is the intent, and also a limit on what an "
        "auditor can do with it alone."
    ),
    "an_m084_only_proposal_approval_or_intent_has_no_time_basis_and_is_never_dispatchable": (
        "A proposal, approval or intent created through MILESTONE-084 alone has no "
        "broker time basis, because none can be measured for an instant that has "
        "passed. It is refused for Paper at approval, issuance, preview and dispatch, "
        "and it is never backfilled."
    ),
    "a_writer_with_insert_privilege_can_store_correctly_shaped_evidence_nobody_measured": (
        "The database checks that time-basis evidence describes the exact record and "
        "the instant of its act. It cannot check that the broker clock was actually "
        "read: a writer with INSERT privilege can store correctly shaped evidence "
        "that nobody measured."
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

#: The five tables, in the shape the digest is taken over. Named once so the digest
#: and the bijection tests describe the same object.
MEANING_TABLES: dict[str, dict[str, str]] = {
    "proves": _PROVES,
    "does_not_prove": _DOES_NOT_PROVE,
    "database_enforcement": _ENFORCEMENT,
    "structural_limitations": _LIMITATIONS,
    "intended_future_use": _FUTURE,
}


def rendered_meaning_digest(tables: dict[str, dict[str, str]] = MEANING_TABLES) -> int:
    """SHA-256 of the identifier -> sentence tables, as an integer.

    Canonical JSON (sorted keys, no whitespace, ASCII-escaped) so the value is the same
    bytes on every platform. An integer rather than a hex string on purpose: the
    repository's secret scanner treats any 64-hex token as a possible credential, and
    the right answer to that is not an allow-list entry but a value with no such token.
    """
    canonical = json.dumps(tables, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return int(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), 16)


class MeaningDriftError(AssertionError):
    """The renderer's sentences no longer digest to what the canonical contract declares."""


def require_declared_meaning(contract: dict[str, Any]) -> None:
    """Refuse to render a meaning the canonical contract has not declared."""
    declared = contract["rendered_meaning_digest"]
    actual = rendered_meaning_digest()
    if declared != actual:
        raise MeaningDriftError(
            "the renderer's identifier -> sentence tables digest to a value the canonical "
            "contract does not declare; a change of meaning must be made in "
            "current-authority.json (rendered_meaning_digest) and its schema, with a new "
            "identifier for any new guarantee"
        )


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
    add(
        f"Rendered-meaning digest `{contract['rendered_meaning_digest']}`: the SHA-256, as an "
        "integer, of the renderer's identifier-to-sentence tables. The contract declares it "
        "and the schema pins it, so the meaning of an identifier cannot change without a "
        "visible change to the canonical contract."
    )
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
    parser.add_argument(
        "--print-meaning-digest",
        action="store_true",
        help="print the digest of the current tables and exit (for updating the contract)",
    )
    args = parser.parse_args(argv)

    if args.print_meaning_digest:
        print(rendered_meaning_digest())
        return 0

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    validate(contract, json.loads(SCHEMA.read_text(encoding="utf-8")))
    try:
        require_declared_meaning(contract)
    except MeaningDriftError as error:
        print(f"{CONTRACT}: {error}", file=sys.stderr)
        return 1
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
