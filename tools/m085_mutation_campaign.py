"""MILESTONE-085 anti-vacuity campaign: mutate the rule, require the test to fail.

    python tools/m085_mutation_campaign.py                 # every family
    python tools/m085_mutation_campaign.py --family NAME    # one family
    python tools/m085_mutation_campaign.py --list           # names only

A green suite proves nothing on its own: it is equally consistent with a product
that enforces every rule and with a product whose tests never look. For each family
below the campaign

  1. names the detecting test FIRST, in the table -- not after seeing what broke;
  2. mutates the REAL governing rule, in production code, the migration or the
     schema;
  3. requires the named test to FAIL, and to fail for the INTENDED REASON rather
     than by import error, collection error or an unrelated assertion;
  4. restores the file and verifies the restoration by SHA-256 against the digest
     taken before the mutation;
  5. re-runs the named test and requires it to pass again.

A surviving mutation is a DEFECT, never a pass. A family whose test still passes
with the rule removed is a family with no test, and the campaign reports it as
EXECUTED_FAIL_BLOCKER.

WHY THE DIGEST MATTERS. Restoring by rewriting remembered text is how a campaign
silently leaves a mutation behind. The digest is taken before the edit and checked
after the restore, so "restored" is measured rather than assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "external-review" / "MILESTONE-085"
MATRIX = PACKAGE / "mutation-matrix.md"

_DOMAIN = "src/empirical_platform/decision_candidate/paper_execution.py"
_ADAPTER = "src/empirical_platform/shared/brokerage/alpaca_paper.py"
_USECASE = "src/empirical_platform/usecases/paper_execution.py"
_REPOSITORY = (
    "src/empirical_platform/shared/persistence/postgres_repositories/"
    "paper_execution_repositories.py"
)
_MIGRATION = "migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py"
_SCHEMA = "external-review/MILESTONE-085/current-authority.schema.json"
_CONTRACT = "external-review/MILESTONE-085/current-authority.json"

_UNIT = "tests/unit/test_m085_paper_execution_domain.py"
_HTTP = "tests/integration/test_m085_hostile_http.py"
_AUTHORITY = "tests/integration/test_m085_authority_contract.py"
_POSTGRES = "tests/integration/test_m085_paper_execution_postgres.py"
_CONCURRENCY = "tests/integration/test_m085_concurrency.py"


@dataclass(frozen=True, slots=True)
class Family:
    """One governing rule, the mutation that removes it, and its detecting test."""

    name: str
    rule: str
    path: str
    #: The exact text to replace. Must occur EXACTLY once, or the campaign refuses
    #: to run the family rather than mutating something it did not intend to.
    original: str
    mutated: str
    #: Named before the mutation is applied. This is the anti-vacuity contract.
    detecting_test: str
    #: What the failure must be about, so an import error cannot be read as
    #: detection.
    expected_fragment: str


#: The M084 deadline rule at the send boundary, in BOTH of its enforcement points.
#: They express the same condition while one process runs, so removing either alone
#: leaves the rule standing -- that is defence in depth working, not a missing test.
#: The campaign therefore mutates the RULE rather than one copy of it.
_FINAL_INTENT_RULE = """\
                if instant >= intent.expires_at or instant >= intent.mandatory_liquidation_at:
                    raise PaperExecutionRefusedError(
                        "the approved intent or liquidation deadline expired"
                    )
                _refuse_expired_m084_deadlines_on_broker_time(
                    authorization=authorization, intent=intent, broker_now=broker_instant
                )"""

_BASIS_EXPIRY_RULE = (
    "            and broker_now.possibly_at_or_after(self.on_broker_timeline(self.expires_at))"
)

#: Re-reading time AFTER the row lock is acquired, on both clocks. As with the
#: send-boundary rule above, the two re-reads express one rule while a process
#: runs, so the campaign removes both: it replaces them with the stale, pre-lock
#: instant and no broker instant at all, which is exactly the defect the rule
#: exists to prevent -- a lock wait that does not age the permission.
_CLAIM_LOCK_RULE = """\
                claimed_at = claim_clock()
                # The lock wait ages BOTH timelines, so both are re-read here.
                refusal = authorization.refusal_against(
                    request_fingerprint_now=request_fingerprint_now,
                    account_reference_now=account_reference_now,
                    instant=claimed_at,
                    broker_now=None if broker_clock is None else broker_clock(),
                )"""

_CLAIM_LOCK_MUTATED = """\
                refusal = authorization.refusal_against(
                    request_fingerprint_now=request_fingerprint_now,
                    account_reference_now=account_reference_now,
                    instant=claimed_at,
                    broker_now=None,
                )"""

FAMILIES: tuple[Family, ...] = (
    Family(
        name="broker_uncertainty_width",
        rule="The bound is as wide as the measured round trip",
        path="src/empirical_platform/shared/brokerage/paper_time.py",
        original="latest = timestamp + timedelta(seconds=round_trip)",
        mutated="latest = timestamp",
        detecting_test="tests/unit/test_m085_paper_time.py::test_the_uncertainty_width_is_exactly_the_measured_round_trip",
        expected_fragment="assert",
    ),
    Family(
        name="broker_clock_monotonicity",
        rule="A broker clock moving backwards refuses",
        path="src/empirical_platform/shared/brokerage/paper_time.py",
        original="if latest < previous_earliest + timedelta(seconds=elapsed):",
        mutated="if False:",
        detecting_test="tests/unit/test_m085_paper_time.py::test_a_broker_clock_that_moves_backwards_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="broker_certainty_margin",
        rule="Time too uncertain to decide the freshness margin refuses",
        path="src/empirical_platform/shared/brokerage/paper_time.py",
        original="if uncertainty >= margin_seconds:",
        mutated="if False:",
        detecting_test="tests/unit/test_m085_paper_time.py::test_uncertainty_at_or_beyond_the_margin_is_refused[60.0]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="broker_basis_recorded",
        rule="Authorizing records the broker time basis",
        path=_DOMAIN,
        original="        basis_host_at=authorized_at,",
        mutated="        basis_host_at=None,",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_a_backward_host_clock_step_between_processes_cannot_extend_an_approval",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="broker_basis_required",
        rule="An authorization carrying a basis cannot be checked without broker time",
        path=_DOMAIN,
        original="        if self.has_broker_time_basis and broker_now is None:",
        mutated="        if False:",
        detecting_test="tests/unit/test_m085_paper_execution_domain.py::TestAuthorizationIsNarrowAndExpiring::test_a_basis_cannot_be_checked_without_broker_time",
        expected_fragment="assert",
    ),
    Family(
        name="broker_basis_authorization_expiry",
        rule="An approval expires on the broker's clock, not only this host's",
        path=_DOMAIN,
        original=_BASIS_EXPIRY_RULE,
        mutated="            and False",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_a_backward_host_clock_step_between_processes_cannot_extend_an_approval",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="m084_deadline_on_broker_time",
        rule="M084 intent deadlines are enforced on the broker's clock too",
        path=_USECASE,
        original=(
            "        if broker_now.possibly_at_or_after("
            "authorization.on_broker_timeline(deadline)):"
        ),
        mutated="        if False:",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_a_backward_host_clock_step_cannot_extend_the_m084_intent_deadline",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="wall_clock_rollback",
        rule="Backward wall clock refuses",
        path="src/empirical_platform/shared/brokerage/paper_time.py",
        original="current.utc < self._last.utc",
        mutated="False",
        detecting_test="tests/unit/test_m085_paper_time.py::test_rollback_refuses[utc]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="post_fetch_time",
        rule="Post-fetch evaluation uses current time",
        path=_USECASE,
        original=(
            "        evaluated_at = timing.now()\n"
            "        broker_instant = timing.broker_now()\n"
            "        preview = build_submission_preview("
        ),
        mutated=(
            "        evaluated_at = command.created_at\n"
            "        broker_instant = timing.broker_now()\n"
            "        preview = build_submission_preview("
        ),
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestPreviewPaperSubmission::test_an_intent_expiring_during_the_fetch_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="final_authorization_expiry",
        rule="Authorization is still valid at HTTP send",
        path=_USECASE,
        original="if refusal is not None or instant < authorization.authorized_at:",
        mutated="if False:",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[authorization-connect]",
        expected_fragment="assert",
    ),
    Family(
        name="final_intent_expiry",
        rule="Intent expiry is checked after preparation",
        path=_USECASE,
        original=_FINAL_INTENT_RULE,
        mutated="                pass",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[intent-prepare]",
        expected_fragment="assert",
    ),
    Family(
        name="final_session_close",
        rule="Market close is checked after preparation",
        path=_USECASE,
        original="or broker_instant.possibly_at_or_after(evidence.market_next_close)",
        mutated="or False",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[session-prepare]",
        expected_fragment="assert",
    ),
    Family(
        name="final_quote_freshness",
        rule="Quote remains fresh after connection",
        path=_USECASE,
        original="if oldest_age > command.quote_maximum_age_seconds or oldest_age < 0:",
        mutated="if False:",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[quote-connect]",
        expected_fragment="assert",
    ),
    Family(
        name="monotonic_elapsed",
        rule="Elapsed work ages a stalled wall clock",
        path="src/empirical_platform/shared/brokerage/paper_time.py",
        original="upper = max(current.utc, self._first.utc + timedelta(seconds=elapsed))",
        mutated="upper = current.utc",
        detecting_test="tests/unit/test_m085_paper_time.py::test_stalled_wall_clock_does_not_stop_expiry",
        expected_fragment="assert",
    ),
    Family(
        name="http_final_guard",
        rule="Guard runs after connect before HTTP send",
        path=_ADAPTER,
        original=(
            "            if before_send is not None:\n"
            "                try:\n                    before_send()"
        ),
        mutated="            if False:\n                try:\n                    before_send()",
        detecting_test="tests/unit/test_m085_paper_time.py::test_final_guard_runs_after_connect_and_before_http_request[False]",
        expected_fragment="order bytes",
    ),
    Family(
        name="claim_time_after_lock",
        rule="A row-lock wait ages the permission: time is re-read after the lock",
        path=_REPOSITORY,
        original=_CLAIM_LOCK_RULE,
        mutated=_CLAIM_LOCK_MUTATED,
        detecting_test="tests/integration/test_m085_temporal_postgres.py::test_real_row_lock_wait_cannot_consume_expired_permission",
        #: Removing the post-lock re-reads does not merely fail to expire the
        #: permission -- it cannot even be expressed, because the claim then has no
        #: broker instant and the basis guard refuses outright. That refusal is the
        #: intended detection, and naming it here keeps the failure specific rather
        #: than accepting any assertion error as proof.
        expected_fragment="cannot be checked without the broker's current instant",
    ),
    Family(
        name="paper_hostname_pin",
        rule="Only paper-api.alpaca.markets may receive an order",
        path=_DOMAIN,
        original='PAPER_ENDPOINT_HOST = "paper-api.alpaca.markets"',
        mutated='PAPER_ENDPOINT_HOST = "api.alpaca.markets"',
        detecting_test=f"{_AUTHORITY}::TestTheMechanicalClaimsMatchTheCode"
        "::test_the_endpoint_host_claim_matches_the_pinned_constant",
        expected_fragment="assert",
    ),
    Family(
        name="https_requirement",
        rule="Only https may carry a credential",
        path=_ADAPTER,
        original='        if scheme != "https":',
        mutated='        if scheme not in {"https", "http"}:',
        detecting_test=f"{_HTTP}::TestTheEndpointItselfCannotBeMoved"
        "::test_a_non_paper_endpoint_is_refused[http://paper-api.alpaca.markets]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="redirect_refusal",
        rule="A redirect is refused, never followed",
        path=_ADAPTER,
        original="        if 300 <= status < 400:",
        mutated="        if False:",
        detecting_test=f"{_HTTP}::TestRedirectsAreRefusedNotFollowed",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="live_host_rejection",
        rule="An alternative host is refused even if it is a real Alpaca host",
        path=_ADAPTER,
        original="        if host != expected_host:",
        mutated="        if False:",
        detecting_test=f"{_HTTP}::TestTheEndpointItselfCannotBeMoved"
        "::test_a_non_paper_endpoint_is_refused[https://api.alpaca.markets]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="userinfo_rejection",
        rule="A URL carrying userinfo is refused",
        path=_ADAPTER,
        original='        if "@" in authority:',
        mutated="        if False:",
        detecting_test=f"{_HTTP}::TestTheEndpointItselfCannotBeMoved"
        "::test_userinfo_is_refused_by_the_userinfo_rule_specifically",
        # With the rule removed the HOST rule refuses these URLs with a
        # different message, so `pytest.raises(match=...)` fails on the match
        # rather than on a missing exception. That distinction is the whole
        # reason this family needed a message-asserting test.
        expected_fragment="AssertionError",
    ),
    Family(
        name="non_canonical_port_rejection",
        rule="A port outside the canonical HTTPS boundary is refused",
        path=_ADAPTER,
        original="        if port not in ALLOWED_PAPER_PORTS:",
        mutated="        if False:",
        detecting_test=f"{_HTTP}::TestTheEndpointItselfCannotBeMoved"
        "::test_a_non_paper_endpoint_is_refused[https://paper-api.alpaca.markets:8443]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="human_authorization_requirement",
        rule="A preview carrying refusals cannot be authorized",
        path=_DOMAIN,
        original="    if not preview.is_authorizable:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_a_refused_preview_cannot_be_authorized",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="account_binding",
        rule="An authorization does not permit a dispatch to another account",
        path=_DOMAIN,
        original="        if self.account_reference != account_reference_now:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_every_material_change_removes_the_permission"
        "[mutation1-different paper account]",
        expected_fragment="assert",
    ),
    Family(
        name="fingerprint_binding",
        rule="An authorization does not permit a changed order",
        path=_DOMAIN,
        original="        if self.request_fingerprint != request_fingerprint_now:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_every_material_change_removes_the_permission"
        "[mutation0-order changed after it was authorized]",
        expected_fragment="assert",
    ),
    Family(
        name="approval_expiry",
        rule="An expired authorization permits nothing",
        path=_DOMAIN,
        original="        if self.is_expired_at(instant):",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_every_material_change_removes_the_permission[mutation2-has expired]",
        expected_fragment="assert",
    ),
    Family(
        name="single_use_authorization",
        rule="A consumed authorization permits nothing further",
        path=_DOMAIN,
        original="        if self.is_consumed:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_a_consumed_authorization_permits_nothing_further",
        expected_fragment="assert",
    ),
    Family(
        name="deterministic_client_order_id",
        rule="The order identity is derived, not generated",
        path=_DOMAIN,
        original=(
            '    material = f"{intent_governance_id}|{account_reference}|{approved_fingerprint}"'
        ),
        mutated="    import uuid\n\n    material = uuid.uuid4().hex",
        detecting_test=f"{_UNIT}::TestTheClientOrderIdIsDerivedNotGenerated"
        "::test_it_is_a_pure_function_of_persisted_identity",
        expected_fragment="assert",
    ),
    Family(
        name="client_order_id_account_binding",
        rule="A different account yields a different order identity",
        path=_DOMAIN,
        original=(
            '    material = f"{intent_governance_id}|{account_reference}|{approved_fingerprint}"'
        ),
        mutated='    material = f"{intent_governance_id}|{approved_fingerprint}"',
        detecting_test=f"{_UNIT}::TestTheClientOrderIdIsDerivedNotGenerated"
        "::test_a_different_account_yields_a_different_order_identity",
        expected_fragment="assert",
    ),
    Family(
        name="unknown_outcome_state",
        rule="An ambiguous dispatch can be resolved but never retried",
        path=_DOMAIN,
        original="""            PaperExecutionState.SUBMISSION_UNKNOWN: frozenset(
                {
                    PaperExecutionState.PAPER_SUBMITTED,""",
        mutated="""            PaperExecutionState.SUBMISSION_UNKNOWN: frozenset(
                {
                    PaperExecutionState.SUBMISSION_IN_PROGRESS,
                    PaperExecutionState.PAPER_SUBMITTED,""",
        detecting_test=f"{_UNIT}::TestTheStateMachineIsClosed"
        "::test_an_unknown_outcome_can_be_resolved_but_never_retried",
        expected_fragment="assert",
    ),
    Family(
        name="terminal_states_are_terminal",
        rule="Nothing leaves a terminal state",
        path=_DOMAIN,
        original="        PaperExecutionState.FILLED: frozenset(),",
        mutated=(
            "        PaperExecutionState.FILLED: frozenset(\n"
            "            {PaperExecutionState.PAPER_SUBMITTED}\n"
            "        ),"
        ),
        detecting_test=f"{_UNIT}::TestTheStateMachineIsClosed"
        "::test_every_terminal_state_has_no_outgoing_edge",
        expected_fragment="assert",
    ),
    Family(
        name="long_only_rule",
        rule="A sell cannot be expressed",
        path=_DOMAIN,
        original='        if self.side != "BUY":',
        mutated='        if self.side not in {"BUY", "SELL"}:',
        detecting_test=f"{_UNIT}::TestTheOrderRequestCannotExpressWhatIsForbidden"
        "::test_a_forbidden_request_is_refused[override0-long-only]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="whole_share_rule",
        rule="A fractional quantity cannot be expressed",
        path=_DOMAIN,
        original=(
            "        if isinstance(self.quantity, bool) or not "
            "isinstance(self.quantity, int):\n"
            '            raise ValueError("quantity must be an int")'
        ),
        mutated='        if False:\n            raise ValueError("quantity must be an int")',
        detecting_test=f"{_UNIT}::TestTheOrderRequestCannotExpressWhatIsForbidden"
        "::test_a_fractional_quantity_is_not_even_representable",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="extended_hours_refusal",
        rule="Extended hours cannot be enabled",
        path=_DOMAIN,
        original="        if self.extended_hours is not False:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestTheOrderRequestCannotExpressWhatIsForbidden"
        "::test_a_forbidden_request_is_refused[override7-extended-hours]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="day_only_rule",
        rule="A time in force other than DAY cannot be expressed",
        path=_DOMAIN,
        original='        if self.time_in_force != "DAY":\n'
        '            raise ValueError("time_in_force must be DAY")',
        mutated='        if False:\n            raise ValueError("time_in_force must be DAY")',
        detecting_test=f"{_UNIT}::TestTheOrderRequestCannotExpressWhatIsForbidden"
        "::test_a_forbidden_request_is_refused[override5-DAY]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="kill_switch",
        rule="An engaged execution kill switch refuses a preview",
        path=_DOMAIN,
        original="    if execution_kill_switch_engaged:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override0-kill switch]",
        expected_fragment="assert",
    ),
    Family(
        name="quote_freshness",
        rule="A stale quote refuses a preview",
        path=_DOMAIN,
        original="        if oldest > quote_maximum_age_seconds:",
        mutated="        elif False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override13-older than the]",
        expected_fragment="assert",
    ),
    Family(
        name="quote_future_timestamp",
        rule="A quote after post-fetch evaluation time refuses authorization",
        path=_DOMAIN,
        original="        elif oldest < 0:",
        mutated="        elif False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal"
        "[override14-dated after the latest possible]",
        expected_fragment="assert",
    ),
    Family(
        name="buying_power_check",
        rule="A cost ceiling above paper buying power refuses a preview",
        path=_DOMAIN,
        original="    elif ceiling > account.buying_power:",
        mutated="    elif False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override11-exceeds paper buying power]",
        expected_fragment="assert",
    ),
    Family(
        name="notional_ceiling",
        rule="A cost ceiling above the configured limit refuses a preview",
        path=_DOMAIN,
        original="    elif ceiling > maximum_notional:",
        mutated="    elif False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override10-exceeds the limit]",
        expected_fragment="assert",
    ),
    Family(
        name="exposure_limit",
        rule="An existing position refuses a preview",
        path=_DOMAIN,
        original="    if existing_position_quantity != 0:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override9-position of 5 already exists]",
        expected_fragment="assert",
    ),
    Family(
        name="asset_tradability",
        rule="An untradable asset refuses a preview",
        path=_DOMAIN,
        original="    if not asset_tradable:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override6-not tradable]",
        expected_fragment="assert",
    ),
    Family(
        name="watchlist",
        rule="A symbol off the approved watchlist refuses a preview",
        path=_DOMAIN,
        original="    if intent.symbol not in approved_watchlist:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal"
        "[override5-not on the approved watchlist]",
        expected_fragment="assert",
    ),
    Family(
        name="account_dispatchability",
        rule="A blocked paper account refuses a preview",
        path=_DOMAIN,
        original="    if not account.is_dispatchable:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override1-does not permit orders]",
        expected_fragment="assert",
    ),
    Family(
        name="response_identity_validation",
        rule="An acknowledgement about another order is refused",
        path=_ADAPTER,
        original="        if view.client_order_id != order.client_order_id:",
        mutated="        if False:",
        detecting_test=f"{_HTTP}::TestAnAnswerAboutTheWrongOrderIsRefused"
        "::test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="response_quantity_validation",
        rule="An acknowledgement for a different quantity is refused",
        path=_ADAPTER,
        original="            if Decimal(view.quantity) != Decimal(order.quantity):",
        mutated="            if False:",
        detecting_test=f"{_HTTP}::TestAnAnswerAboutTheWrongOrderIsRefused"
        "::test_a_mismatched_acknowledgement_fails_closed[override3-quantity]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="credential_redaction",
        rule="A credential echoed by a peer is scrubbed before storage",
        path=_ADAPTER,
        original="    return _scrub_credentials(printable, credentials)",
        mutated="    return printable",
        detecting_test=f"{_HTTP}::TestACredentialNeverComesBackOut"
        "::test_a_peer_echoing_our_secret_has_it_scrubbed_before_storage",
        expected_fragment="assert",
    ),
    Family(
        name="maximum_diagnostic_body_size",
        rule="A stored broker response body is bounded",
        path=_ADAPTER,
        original="MAXIMUM_DIAGNOSTIC_BODY_BYTES: Final = 8192",
        mutated="MAXIMUM_DIAGNOSTIC_BODY_BYTES: Final = 10_000_000",
        detecting_test=f"{_HTTP}::TestMalformedAnswers"
        "::test_an_oversized_body_is_bounded_before_it_is_stored",
        expected_fragment="assert",
    ),
    Family(
        name="broker_status_map_closure",
        rule="An unmapped broker status does not become a known one",
        path=_USECASE,
        original='        "filled": PaperExecutionState.FILLED,',
        mutated='        "filled": PaperExecutionState.FILLED,\n'
        '        "calculated": PaperExecutionState.FILLED,',
        detecting_test=f"{_AUTHORITY}::TestTheMechanicalClaimsMatchTheCode"
        "::test_the_broker_status_map_is_exactly_this_closed_set",
        expected_fragment="assert",
    ),
    Family(
        name="authority_enum_closure",
        rule="A claim the schema does not name cannot enter the contract",
        path=_SCHEMA,
        original='      "minItems": 13,\n      "maxItems": 13,',
        mutated='      "minItems": 1,\n      "maxItems": 99,',
        detecting_test=f"{_AUTHORITY}::TestTheContractIsValidAndClosed"
        "::test_every_list_length_is_exact",
        expected_fragment="assert",
    ),
    Family(
        name="authority_version_const",
        rule="The authority version is frozen at 1",
        path=_SCHEMA,
        original='"authority_version": {\n      "const": 1\n    },',
        mutated='"authority_version": {\n      "type": "integer"\n    },',
        detecting_test=f"{_AUTHORITY}::TestTheContractIsValidAndClosed"
        "::test_the_authority_version_is_pinned_to_one",
        expected_fragment="assert",
    ),
    Family(
        name="deterministic_markdown_check",
        rule="The document is the deterministic rendering of the contract",
        path=_CONTRACT,
        original='"title": "Alpaca Paper Execution with Exact Human Approval"',
        mutated='"title": "Alpaca Paper Execution"',
        detecting_test=f"{_AUTHORITY}::TestTheDocumentIsTheRendering"
        "::test_the_markdown_is_byte_identical_to_the_rendering",
        expected_fragment="assert",
    ),
    Family(
        name="database_transition_trigger",
        rule="The database refuses an illegal execution transition",
        path=_MIGRATION,
        original="    IF NOT (NEW.state = ANY (allowed)) THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_POSTGRES}::TestTheTransitionTableIsClosedInTheDatabase"
        "::test_the_database_table_matches_the_domain_table_exactly",
        expected_fragment="assert",
    ),
    Family(
        name="database_single_use_trigger",
        rule="The database refuses a second consumption",
        path=_MIGRATION,
        original="    IF OLD.consumed_at IS NOT NULL THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_POSTGRES}::TestTheDatabaseEnforcesSingleUse"
        "::test_a_second_consumption_is_refused_by_the_trigger",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_attempt_insert_guard",
        rule="The database refuses an attempt without a consumed authorization",
        path=_MIGRATION,
        original="    IF authorization_row.consumed_at IS NULL THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_POSTGRES}::TestTheDatabaseEnforcesOneDispatchPerIntent"
        "::test_an_attempt_without_a_consumed_authorization_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="m084_intent_boundary",
        rule="A paper row naming an unknown intent is refused",
        path=_MIGRATION,
        original="    IF NOT EXISTS (\n        SELECT 1 FROM public.approved_order_intent",
        mutated="    IF FALSE AND NOT EXISTS (\n        SELECT 1 FROM public.approved_order_intent",
        detecting_test=f"{_POSTGRES}::TestMilestone084IsUntouched"
        "::test_a_paper_row_naming_an_unknown_intent_is_still_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="dispatch_claim_lease",
        rule="The claim is conditional, so two workers cannot both win",
        path=_REPOSITORY,
        original='    "WHERE authorization_id = :authorization_id AND consumed_at IS NULL "',
        mutated='    "WHERE authorization_id = :authorization_id "',
        detecting_test=f"{_CONCURRENCY}::TestTwoWorkersCannotBothClaimOneDispatch"
        "::test_exactly_one_wins_and_the_loser_receives_the_winner[repetition-1]",
        expected_fragment="assert",
    ),
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(test: str) -> tuple[int, str]:
    process = subprocess.run(  # noqa: S603 - fixed vector, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            test,
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return process.returncode, process.stdout + process.stderr


@dataclass(slots=True)
class Result:
    family: Family
    status: str
    detail: str


def run_family(family: Family) -> Result:
    path = REPO_ROOT / family.path
    source = path.read_text(encoding="utf-8")
    before = _digest(path)

    occurrences = source.count(family.original)
    if occurrences != 1:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            f"the mutation target occurs {occurrences} times in {family.path}; refusing to "
            "mutate something other than the intended rule",
        )

    # A green baseline first: a test that already fails cannot detect anything.
    baseline_code, baseline_output = _run(family.detecting_test)
    if baseline_code != 0:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            f"the detecting test does not pass before the mutation: {baseline_output[-400:]}",
        )

    path.write_text(source.replace(family.original, family.mutated), encoding="utf-8", newline="\n")
    try:
        mutated_code, mutated_output = _run(family.detecting_test)
    finally:
        path.write_text(source, encoding="utf-8", newline="\n")

    after = _digest(path)
    if after != before:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            f"restoration failed: digest {after} != {before}",
        )

    if mutated_code == 0:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            "THE MUTATION SURVIVED. The named test still passes with the rule removed, so it "
            "does not detect it.",
        )
    if family.expected_fragment not in mutated_output:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            f"the test failed, but not for the intended reason ({family.expected_fragment!r} "
            f"absent): {mutated_output[-400:]}",
        )

    restored_code, restored_output = _run(family.detecting_test)
    if restored_code != 0:
        return Result(
            family,
            "EXECUTED_FAIL_BLOCKER",
            f"the test does not pass again after restoration: {restored_output[-400:]}",
        )
    return Result(family, "EXECUTED_PASS", f"detected; restored to `{before[:16]}`")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", action="append", help="run only these families")
    parser.add_argument(
        "--output", type=Path, default=MATRIX, help="write this campaign separately"
    )
    parser.add_argument("--list", action="store_true", help="print family names and exit")
    arguments = parser.parse_args(argv)

    if arguments.list:
        for family in FAMILIES:
            print(family.name)
        return 0

    selected = (
        [family for family in FAMILIES if family.name in set(arguments.family)]
        if arguments.family
        else list(FAMILIES)
    )
    if not selected:
        print("no such family", file=sys.stderr)
        return 2

    results: list[Result] = []
    for index, family in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {family.name} ... ", end="", flush=True)
        result = run_family(family)
        results.append(result)
        print(result.status, flush=True)
        if result.status != "EXECUTED_PASS":
            print(f"    {result.detail}", flush=True)

    blockers = [result for result in results if result.status != "EXECUTED_PASS"]
    detected = len(results) - len(blockers)

    lines = [
        "# MILESTONE-085 — Mutation Matrix",
        "",
        f"**{detected} of {len(results)} families detected.** A surviving mutation is a defect,",
        "never a pass.",
        "",
        "Each row names its detecting test BEFORE the mutation was applied. For every family the",
        "campaign required a green baseline, applied the mutation to the real governing rule,",
        "required the named test to fail FOR THE INTENDED REASON, restored the file, verified the",
        "restoration by SHA-256 against the digest taken beforehand, and re-ran the test to",
        "require it green again.",
        "",
        "| Family | Rule removed | File | Detecting test | Status | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| `{result.family.name}` | {result.family.rule} | `{result.family.path}` | "
            f"`{result.family.detecting_test.split('::')[-1]}` | **{result.status}** | "
            f"{result.detail} |"
        )
    lines.append("")
    if blockers:
        lines.append("## Blockers")
        lines.append("")
        for result in blockers:
            lines.append(f"- `{result.family.name}`: {result.detail}")
        lines.append("")

    PACKAGE.mkdir(parents=True, exist_ok=True)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {arguments.output}")
    print(f"{detected}/{len(results)} detected, {len(blockers)} blockers")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
