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
after the restore, so "restored" is measured rather than assumed. A second digest
covers the whole source tree -- every file under src, tests, tools, migrations and
scripts -- before the first family and after the last, so a restoration that fixed
the intended file but left any other file changed is also caught.

Families run strictly one at a time: each mutates, tests and restores before the next
begins, and the restoration sits in a `finally` so an interrupted test run still
restores. PostgreSQL families need `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` and a
DISPOSABLE database; without it their tests skip, a skipped test cannot fail, and the
family is reported as a surviving mutation rather than as detected.
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

#: CORRECTIVE PASS: the files that carry the rules this pass added, and their tests.
_CORRECTIVE_MIGRATION = (
    "migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py"
)
_COMPOSITION = "src/empirical_platform/entrypoints/_paper_composition.py"
_ACCEPTANCE_TOOL = "tools/m085_paper_acceptance.py"
_CORRECTIVE_UNIT = "tests/unit/test_m085_corrective_pass_domain.py"
_CORRECTIVE_HANDLERS = "tests/unit/test_m085_corrective_pass_handlers.py"
_CORRECTIVE_POSTGRES = "tests/integration/test_m085_corrective_pass_postgres.py"
_COMPOSITION_TESTS = "tests/unit/test_m085_paper_composition.py"
_DRY_RUN_TESTS = "tests/unit/test_m085_paper_acceptance_dry_run.py"

#: IDENTITY-SAFETY CORRECTION (F1): the rules that make an existing broker identity a
#: reconciliation, never a refusal and never a resend, and the M084 mechanical freeze.
_IDENTITY_UNIT = "tests/unit/test_m085_identity_collision.py"
_IDENTITY_POSTGRES = "tests/integration/test_m085_identity_collision_postgres.py"
_FROZEN_GUARD = "tools/check_frozen_paths.py"
_FROZEN_TESTS = "tests/architecture/test_frozen_milestones.py"

#: SEND-BOUNDARY CORRECTION (A6): the final decision follows every slow read; observing an
#: order is not attributing it; refusal semantics are documented codes, never shape.
_SEND_BOUNDARY = "tests/unit/test_m085_send_boundary.py"
_LINEAGE_UNIT = "tests/unit/test_m085_identity_lineage.py"
_ACK_HTTP = "tests/integration/test_m085_acknowledgement_terms_http.py"

#: Everything a mutation could touch and every file a restoration must leave as it was.
#: Digested whole before the first family and after the last, so a campaign that
#: restored the file it meant to but left anything else changed is caught.
_TREE_ROOTS = ("src", "tests", "tools", "migrations", "scripts")


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
#: CORRECTIVE PASS: the rule moved from `before_send` into `final_send_refusal`, which
#: `before_send` now calls on freshly read evidence; the superseded text is gone.
_FINAL_INTENT_RULE = """\
    if host_now >= intent.expires_at or host_now >= intent.mandatory_liquidation_at:
        return "the approved intent or liquidation deadline expired"
    # BROKER TIMELINE: the same deadlines, each through the basis of the act that wrote it.
    deadline_refusal = m084_deadline_refusal_on_broker_time(
        intent=intent, provenance=provenance, broker_now=broker_now
    )
    if deadline_refusal is not None:
        return deadline_refusal"""

_BASIS_EXPIRY_RULE = """\
            and broker_now.possibly_at_or_after(
                authorization_basis.on_broker_timeline(self.expires_at)
            )"""

_PAPER_TIME = "src/empirical_platform/shared/brokerage/paper_time.py"
_BASIS_MIGRATION = "migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py"
_PROVENANCE_MIGRATION = (
    "migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py"
)
_HANDLERS = "tests/unit/test_m085_paper_execution_handlers.py"
_TIME_BASIS_POSTGRES = "tests/integration/test_m085_time_basis_postgres.py"

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
    # -- the AUTHORIZATION-time basis: measured when a human authorizes --------
    Family(
        name="authorization_basis_pairs_the_post_response_host_reading",
        rule="The basis pairs the broker timestamp with the host reading AFTER the response",
        path=_PAPER_TIME,
        original="        host_at = self.now()",
        mutated="        host_at = host_requested_at",
        detecting_test=f"{_HANDLERS}::TestSubmitAuthorizedPaperOrder"
        "::test_broker_fetch_latency_cannot_extend_the_authorization_deadline",
        expected_fragment="assert",
    ),
    Family(
        name="authorization_basis_interval_required",
        rule="An authorization without an interval-shaped basis is not dispatchable",
        path=_DOMAIN,
        original=(
            "        if authorization_basis is None:\n"
            "            return NO_AUTHORIZATION_TIME_BASIS"
        ),
        mutated="        if False:\n            return NO_AUTHORIZATION_TIME_BASIS",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_the_replaced_pre_fetch_pairing_is_no_longer_trusted",
        expected_fragment="assert",
    ),
    Family(
        name="broker_basis_required",
        rule="An authorization carrying a basis cannot be checked without broker time",
        path=_DOMAIN,
        original="        if broker_now is None:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestAuthorizationIsNarrowAndExpiring"
        "::test_a_basis_cannot_be_checked_without_broker_time",
        expected_fragment="assert",
    ),
    Family(
        name="broker_basis_authorization_expiry",
        rule="An approval expires on the broker's clock, through its own basis",
        path=_DOMAIN,
        original=_BASIS_EXPIRY_RULE,
        mutated="            and False",
        detecting_test=f"{_HANDLERS}::TestSubmitAuthorizedPaperOrder"
        "::test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization",
        # CORRECTIVE PASS run 1 named `DID NOT RAISE` and was a blocker. The final send
        # guard now also refuses a dispatch whose host clock reads before `authorized_at`,
        # so with this rule removed the same dispatch is still refused -- as future-dated
        # rather than as expired. The test's message match is what detects the removal;
        # in this scenario the two rules are defence in depth.
        expected_fragment="the authorization is future-dated",
    ),
    Family(
        name="authorization_not_future_dated_against_its_basis",
        rule="authorized_at may not postdate the host reading its expiry is mapped with",
        path=_DOMAIN,
        original=(
            "        if authorization_basis is not None and "
            "self.authorized_at > authorization_basis.host_at:"
        ),
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_a_future_dated_authorization_cannot_be_mapped",
        expected_fragment="DID NOT RAISE",
    ),
    # -- PER-ACT PROVENANCE: each deadline through the basis of the act that wrote it
    # SUPERSEDED: `m084_deadline_on_intent_time_basis` mutated the rule that mapped
    # the intent's deadlines through the ISSUANCE basis. That rule was the defect
    # reproduced at `73a2f96`, so the family now mutates the proposal-time rule.
    Family(
        name="m084_deadline_on_proposal_time_basis",
        rule="M084 deadlines are enforced on the broker's clock through the proposal's own basis",
        path=_DOMAIN,
        # CORRECTIVE PASS: the deadlines are placed on the broker timeline first (the
        # liquidation deadline through `effective_liquidation_deadline`), then compared.
        original="        if broker_now.possibly_at_or_after(deadline):\n            return label",
        mutated="        if False:\n            return label",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_the_intent_deadline_is_mapped_through_the_proposal_basis",
        expected_fragment="assert",
    ),
    Family(
        name="m084_deadline_never_through_a_later_basis",
        rule="A deadline written at evaluation is never translated through the issuance basis",
        path=_DOMAIN,
        original="    proposal_basis = provenance.proposal.time_basis",
        mutated="    proposal_basis = (provenance.intent or provenance.proposal).time_basis",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_the_intent_deadline_is_mapped_through_the_proposal_basis",
        expected_fragment="assert",
    ),
    Family(
        name="proposal_basis_required",
        rule="A proposal evaluated without its own basis cannot be issued for Paper",
        path=_DOMAIN,
        original="    if evidence is None:\n        return NO_PROPOSAL_TIME_BASIS",
        mutated="    if evidence is None:\n        return None",
        detecting_test=f"{_HANDLERS}::TestIssuePaperBoundOrderIntent"
        "::test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="decision_basis_required",
        rule="An approval recorded without its own basis cannot be issued for Paper",
        path=_DOMAIN,
        original="    if evidence is None:\n        return NO_DECISION_TIME_BASIS",
        mutated="    if evidence is None:\n        return None",
        detecting_test=f"{_HANDLERS}::TestIssuePaperBoundOrderIntent"
        "::test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="proposal_basis_matches_the_exact_proposal",
        rule="Proposal evidence describing different deadlines is refused",
        path=_DOMAIN,
        original='            ("expires_at", expires_at, evidence.proposal_expires_at),\n',
        mutated="",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_proposal_evidence_describing_another_proposal_refuses_the_preview",
        expected_fragment="assert",
    ),
    Family(
        name="approval_before_proposal_expiry_on_broker_time",
        rule="An approval recorded after the proposal expired on the broker's clock is refused",
        path=_DOMAIN,
        original="    if _broker_interval(decision_basis).possibly_at_or_after(proposal_expiry):",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_an_approval_recorded_after_the_proposal_expired_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="approval_expiry_at_issuance_through_the_decision_basis",
        rule="An intent issued after the approval expired on the broker's clock is refused",
        path=_DOMAIN,
        original=(
            "        (\n"
            "            decision_basis.on_broker_timeline(decision.decision_expires_at),\n"
            "            \"the approval had expired on the broker's clock when the intent "
            'was issued",\n'
            "        ),\n"
        ),
        mutated="",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_an_approval_that_expired_before_issuance_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="stale_proposal_refused_at_issuance",
        rule="Issuance is refused when a deadline it relies on passed on the broker's clock",
        path=_USECASE,
        original=(
            "            if chronology is not None:\n"
            "                raise PaperExecutionRefusedError(chronology)"
        ),
        mutated="            del chronology",
        detecting_test=f"{_TIME_BASIS_POSTGRES}::TestAStaleProposalAndApprovalCannotReachTheBroker"
        "::test_the_chain_is_refused_somewhere_and_nothing_is_sent",
        expected_fragment="assert",
    ),
    Family(
        name="approval_refused_for_a_proposal_expired_on_broker_time",
        rule="A human cannot approve a proposal that may have expired on the broker's clock",
        path=_USECASE,
        original="            if deciding.possibly_at_or_after(",
        mutated="            if False and deciding.possibly_at_or_after(",
        detecting_test=f"{_HANDLERS}::TestDecidePaperBoundTradeProposal"
        "::test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="evaluation_uses_the_measured_host_reading",
        rule="The proposal is evaluated at the basis host reading, not at an unmeasured instant",
        path=_USECASE,
        original="                evaluated_at=time_basis.host_at,",
        mutated="                evaluated_at=time_basis.host_requested_at,",
        detecting_test=f"{_HANDLERS}::TestPreparePaperBoundTradeProposal"
        "::test_the_proposal_is_evaluated_at_the_host_reading_taken_after_the_clock_response",
        # The real binder refuses first: evidence whose host reading is not the
        # evaluation instant cannot be built. Run 1 named `assert` and was a blocker.
        expected_fragment="after the fact",
    ),
    Family(
        name="decision_uses_the_measured_host_reading",
        rule="The approval is decided at the basis host reading, not at an unmeasured instant",
        path=_USECASE,
        original="                decided_at=time_basis.host_at,",
        mutated="                decided_at=time_basis.host_requested_at,",
        detecting_test=f"{_HANDLERS}::TestDecidePaperBoundTradeProposal"
        "::test_an_approval_is_decided_at_the_host_reading_taken_after_the_clock_response",
        expected_fragment="assert",
    ),
    # -- the INTENT-time basis: measured when the M084 intent is issued ------
    Family(
        name="intent_basis_required",
        rule="An intent issued without its own basis is not dispatchable",
        path=_DOMAIN,
        original="    if evidence is None:\n        return NO_INTENT_TIME_BASIS",
        mutated="    if evidence is None:\n        return None",
        detecting_test=f"{_HANDLERS}::TestSubmitAuthorizedPaperOrder"
        "::test_an_intent_without_its_own_basis_is_refused_before_any_broker_call",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="intent_basis_matches_the_exact_intent",
        rule="Evidence describing a different intent is refused",
        path=_DOMAIN,
        original='            ("expires_at", intent.expires_at, evidence.intent_expires_at),\n',
        mutated="",
        detecting_test=f"{_HANDLERS}::TestSubmitAuthorizedPaperOrder"
        "::test_evidence_describing_a_different_intent_is_refused[expires_at]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="intent_basis_bound_to_issuance",
        rule="An intent-time basis cannot be attached after the intent was issued",
        path=_DOMAIN,
        original="        if self.intent_created_at != self.basis_host_at:",
        mutated="        if False:",
        detecting_test=f"{_UNIT}::TestTheTwoTimeBasesHaveDistinctProvenance"
        "::test_intent_evidence_cannot_be_attached_after_issuance",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="issuance_uses_the_measured_host_reading",
        rule="The intent is issued at the basis host reading, not at an unmeasured instant",
        path=_USECASE,
        original="                created_at=time_basis.host_at,",
        mutated="                created_at=time_basis.host_requested_at,",
        detecting_test=f"{_HANDLERS}::TestIssuePaperBoundOrderIntent"
        "::test_the_intent_is_issued_at_the_host_reading_taken_after_the_clock_response",
        expected_fragment="after the fact",
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
        path=_DOMAIN,
        original=(
            "    if refusal is not None:\n"
            "        return refusal\n"
            "    if host_now < authorization.authorized_at:"
        ),
        mutated="    if host_now < authorization.authorized_at:",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[authorization-connect]",
        expected_fragment="assert",
    ),
    Family(
        name="final_intent_expiry",
        rule="Intent expiry is checked after preparation",
        path=_DOMAIN,
        original=_FINAL_INTENT_RULE,
        mutated="    pass",
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[intent-prepare]",
        expected_fragment="assert",
    ),
    Family(
        name="final_session_close",
        rule="Market close is checked after preparation",
        path=_DOMAIN,
        original=(
            "        or broker_now.possibly_at_or_after(market_next_close)\n"
            "    ):\n"
            '        return "the regular market session is closed"\n'
        ),
        mutated='        or False\n    ):\n        return "the regular market session is closed"\n',
        detecting_test="tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_elapsed_work_cannot_extend_a_deadline[session-prepare]",
        expected_fragment="assert",
    ),
    Family(
        name="final_quote_freshness",
        rule="Quote remains fresh after connection",
        # CORRECTIVE PASS: one shared `quote_refusal`, under the configuration's limit.
        path=_DOMAIN,
        original="    if oldest > policy.quote_maximum_age_seconds:",
        mutated="    if False:",
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
        # CORRECTIVE PASS run 1 named `DID NOT RAISE` and was a blocker: an order POST
        # answered by a redirect is now SUBMISSION_UNKNOWN, so with the rule removed an
        # ambiguous error is still raised -- about HTTP 301, not about a redirect.
        expected_fragment="Regex pattern did not match",
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
        # CORRECTIVE PASS: the refusal is asked in `authorize_submission` AND in the
        # binding check it ends with, so the property both read is what is removed.
        original="        return not self.refusals",
        mutated="        return True",
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
        # CORRECTIVE PASS: the authorization now repeats this check for its own copy of
        # the quantity, so the target is anchored on the order request's side rule.
        original=(
            '            raise ValueError("side must be BUY: this product is long-only")\n'
            "        if isinstance(self.quantity, bool) or not "
            "isinstance(self.quantity, int):\n"
            '            raise ValueError("quantity must be an int")'
        ),
        mutated=(
            '            raise ValueError("side must be BUY: this product is long-only")\n'
            '        if False:\n            raise ValueError("quantity must be an int")'
        ),
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
        original="    if oldest > policy.quote_maximum_age_seconds:",
        mutated="    if False:",
        detecting_test=f"{_UNIT}::TestThePreviewCollectsEveryRefusal"
        "::test_each_condition_produces_its_own_refusal[override13-older than the]",
        expected_fragment="assert",
    ),
    Family(
        name="quote_future_timestamp",
        rule="A quote after post-fetch evaluation time refuses authorization",
        path=_DOMAIN,
        original="    if oldest < 0:",
        mutated="    if False:",
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
        original="    elif ceiling > policy.maximum_notional:",
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
        original="    if intent.symbol not in policy.watchlist:",
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
        original="        mismatches = list(order_terms_mismatches(expected=order, actual=view))",
        mutated="        mismatches: list[str] = []",
        detecting_test=f"{_HTTP}::TestAnAnswerAboutTheWrongOrderIsRefused"
        "::test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="response_quantity_validation",
        rule="An acknowledgement for a different quantity is refused",
        path=_DOMAIN,
        # The adapter delegates to the canonical comparison; the quantity rule lives there.
        original=(
            '        if Decimal(actual_text("quantity") or "x") '
            '!= Decimal(getattr(expected, "quantity", -1)):'
        ),
        mutated="        if False:",
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
        original='      "minItems": 14,\n      "maxItems": 14,',
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
        # CORRECTIVE PASS run 1 SURVIVED here: `9c4b2e7d5a18` replaces the attempt update
        # guard, so mutating `b1e9d47c30a5`'s copy changed nothing installed at head.
        path=_CORRECTIVE_MIGRATION,
        original="    IF NOT (NEW.state = ANY (allowed)) THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_POSTGRES}::TestTheTransitionTableIsClosedInTheDatabase"
        "::test_the_database_table_matches_the_domain_table_exactly",
        expected_fragment="assert",
    ),
    Family(
        name="database_single_use_trigger",
        rule="The database refuses a second consumption",
        # `d4f18a6c2e97` replaces the authorization guard (to freeze the basis
        # columns), so the guard ENFORCED at head is that migration's copy. Mutating
        # the original text in `b1e9d47c30a5` changed nothing that runs, and the
        # family survived until it was pointed here.
        path=_BASIS_MIGRATION,
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
    # -- the two bases, at the database boundary ------------------------------
    Family(
        name="database_basis_interval_shape",
        rule="The database refuses an authorization dated after its basis host reading",
        path=_BASIS_MIGRATION,
        original='        " AND authorized_at <= basis_host_at)",',
        mutated='        ")",',
        detecting_test=f"{_TIME_BASIS_POSTGRES}::TestTheDatabaseRefusesAMalformedAuthorizationBasis"
        "::test_a_malformed_basis_is_refused[authorized-after-the-basis-reading]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_basis_immutable",
        rule="The consuming UPDATE cannot rewrite the authorization basis",
        path=_BASIS_MIGRATION,
        original=(
            "        OR NEW.basis_broker_earliest_at IS DISTINCT FROM "
            "OLD.basis_broker_earliest_at\n"
        ),
        mutated="",
        detecting_test=f"{_TIME_BASIS_POSTGRES}::TestTheDatabaseRefusesAMalformedAuthorizationBasis"
        "::test_the_basis_cannot_be_rewritten_by_the_consuming_update[basis_broker_earliest_at]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_intent_basis_matches_intent",
        rule="The database refuses evidence that does not describe the exact stored intent",
        path=_BASIS_MIGRATION,
        original="        OR intent_row.expires_at IS DISTINCT FROM NEW.intent_expires_at\n",
        mutated="",
        detecting_test=f"{_TIME_BASIS_POSTGRES}::TestTheDatabaseBindsIntentEvidenceToTheExactIntent"
        "::test_evidence_describing_another_intent_is_refused[expires_at]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_intent_basis_bound_to_issuance",
        rule="The database refuses evidence whose host reading is not the issuance instant",
        path=_BASIS_MIGRATION,
        original='            "intent_created_at = basis_host_at",',
        mutated='            "true",',
        detecting_test=f"{_TIME_BASIS_POSTGRES}::TestTheDatabaseBindsIntentEvidenceToTheExactIntent"
        "::test_evidence_not_bound_to_the_issuance_instant_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_proposal_basis_matches_proposal",
        rule="The database refuses proposal evidence that does not describe the stored proposal",
        path=_PROVENANCE_MIGRATION,
        original="        OR proposal_row.expires_at IS DISTINCT FROM NEW.proposal_expires_at\n",
        mutated="",
        detecting_test=f"{_TIME_BASIS_POSTGRES}"
        "::TestTheDatabaseBindsProposalAndDecisionEvidenceToTheirActs"
        "::test_proposal_evidence_describing_another_proposal_is_refused[expires_at]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_decision_basis_matches_approval",
        rule="The database refuses decision evidence that does not describe the stored approval",
        path=_PROVENANCE_MIGRATION,
        original="        OR decision_row.expires_at IS DISTINCT FROM NEW.decision_expires_at\n",
        mutated="",
        detecting_test=f"{_TIME_BASIS_POSTGRES}"
        "::TestTheDatabaseBindsProposalAndDecisionEvidenceToTheirActs"
        "::test_decision_evidence_describing_another_approval_is_refused[decision_expires_at]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_proposal_basis_bound_to_evaluation",
        rule="The database refuses proposal evidence whose host reading is not the evaluation",
        path=_PROVENANCE_MIGRATION,
        original='            "proposal_created_at = basis_host_at",',
        mutated='            "true",',
        detecting_test=f"{_TIME_BASIS_POSTGRES}"
        "::TestTheDatabaseBindsProposalAndDecisionEvidenceToTheirActs"
        "::test_proposal_evidence_not_bound_to_the_evaluation_instant_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_decision_basis_bound_to_decision",
        rule="The database refuses decision evidence whose host reading is not the decision",
        path=_PROVENANCE_MIGRATION,
        original='            "decided_at = basis_host_at",',
        mutated='            "true",',
        detecting_test=f"{_TIME_BASIS_POSTGRES}"
        "::TestTheDatabaseBindsProposalAndDecisionEvidenceToTheirActs"
        "::test_decision_evidence_not_bound_to_the_decision_instant_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="authority_contract_reads_the_sql_installed_at_head",
        rule="An enforcement claim is checked against the guard installed at head",
        # The expiry rule ENFORCED at head is `d4f18a6c2e97`'s replacement guard. The
        # original text in `b1e9d47c30a5` still contains the same message, so a contract
        # reading only that file -- as it did until this correction -- survived this.
        path=_BASIS_MIGRATION,
        original="            'authorization % expired at % and cannot be consumed at %',",
        mutated="            'authorization % expired at %',",
        detecting_test=f"{_AUTHORITY}::TestTheMechanicalClaimsMatchTheCode"
        "::test_every_database_enforcement_claim_names_sql_installed_at_head",
        expected_fragment="expired_authorization_cannot_be_consumed",
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
    # == CORRECTIVE PASS =====================================================
    # D1 -- the send-time limits are the configuration's, bound to the authorization
    Family(
        name="policy_derived_from_the_configuration",
        rule="The quote age limit is the stored configuration's, not a constant or argument",
        path=_DOMAIN,
        original="        quote_maximum_age_seconds=configuration.maximum_market_data_age_seconds,",
        mutated="        quote_maximum_age_seconds=3600,",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestThePolicyComesFromTheConfigurationOnly"
        "::test_every_send_time_limit_is_the_configurations",
        expected_fragment="assert",
    ),
    Family(
        name="policy_fingerprint_covers_every_limit",
        rule="Changing the quote age limit changes the policy fingerprint",
        path=_DOMAIN,
        original='                "quote_maximum_age_seconds": self.quote_maximum_age_seconds,\n',
        mutated="",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestThePolicyComesFromTheConfigurationOnly"
        "::test_every_limit_is_part_of_the_policy_fingerprint",
        expected_fragment="assert",
    ),
    Family(
        name="final_guard_policy_fingerprint",
        rule="A re-derived policy other than the authorized one refuses the send",
        path=_DOMAIN,
        original="    if authorization.policy_fingerprint != policy_now.fingerprint:",
        mutated="    if False:",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestTheFinalSendGuard"
        "::test_a_loosened_configuration_cannot_satisfy_an_authorization",
        expected_fragment="assert",
    ),
    Family(
        name="spread_limit",
        rule="A spread above the configured limit refuses",
        path=_DOMAIN,
        original="    if spread > policy.maximum_spread_percent:",
        mutated="    if False:",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestTheSpreadBoundary"
        "::test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not",
        expected_fragment="assert",
    ),
    Family(
        name="entry_window",
        rule="A broker instant that may be outside the entry window refuses",
        path=_DOMAIN,
        original=(
            "        earliest.timetz().replace(tzinfo=None) < policy.earliest_entry_time\n"
            "        or latest.timetz().replace(tzinfo=None) > policy.latest_entry_time"
        ),
        mutated="        False",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestTheEntryWindowIsJudgedOnTheBrokerClock",
        expected_fragment="assert",
    ),
    # P3 -- the authorization is exactly the preview it names
    Family(
        name="authorization_binds_every_field",
        rule="An authorization whose quote ask is not the preview's permits nothing",
        path=_DOMAIN,
        original='        ("quote_ask", preview.quote_ask, authorization.quote_ask),\n',
        mutated="",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestAnAuthorizationIsBoundToItsExactPreview"
        "::test_tampering_with_any_bound_field_is_named",
        expected_fragment="assert",
    ),
    Family(
        name="authorization_never_outlives_the_intent",
        rule="A stored authorization expiring after its intent permits nothing",
        path=_DOMAIN,
        original=(
            "    if authorization.expires_at > preview.intent_expires_at:\n"
            '        return "the authorization outlives'
        ),
        mutated='    if False:\n        return "the authorization outlives',
        detecting_test=f"{_CORRECTIVE_UNIT}::TestAnAuthorizationIsBoundToItsExactPreview"
        "::test_a_stored_authorization_outliving_its_intent_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="authorization_after_preview_freshness",
        rule="A preview older than the configured freshness limit cannot be authorized",
        path=_DOMAIN,
        original="    if (time_basis.host_at - preview.created_at).total_seconds() > (",
        mutated="    if False and (time_basis.host_at - preview.created_at).total_seconds() > (",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestAnAuthorizationIsBoundToItsExactPreview"
        "::test_a_preview_older_than_the_freshness_limit_cannot_be_authorized",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="dispatch_checks_the_binding",
        rule="The submit handler refuses a stored authorization that does not describe its preview",
        path=_USECASE,
        original=(
            "        if binding_refusal is not None:\n"
            '            raise PaperExecutionRefusedError(f"this dispatch is not authorized: '
            '{binding_refusal}")'
        ),
        mutated=(
            "        if False:\n"
            '            raise PaperExecutionRefusedError(f"this dispatch is not authorized: '
            '{binding_refusal}")'
        ),
        detecting_test=f"{_CORRECTIVE_HANDLERS}"
        "::TestNothingOutsideTheConfigurationCanLoosenAnAuthorization"
        "::test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]",
        expected_fragment="DID NOT RAISE",
    ),
    # Item 7 -- every input to the final guard is read again
    Family(
        name="final_guard_reads_the_kill_switch_again",
        rule="The kill switch is re-read after the claim",
        path=_USECASE,
        original="                kill_switch_engaged = self._kill_switch.is_engaged()",
        mutated="                kill_switch_engaged = evidence.kill_switch_engaged",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestTheFinalGuardReadsEverythingAgain"
        "::test_a_kill_switch_engaged_after_the_claim_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="final_guard_reads_the_configuration_again",
        rule="The configuration is re-loaded and re-derived after the claim",
        path=_USECASE,
        original="                policy_now = _policy_for(intent, self._configurations)",
        mutated="                policy_now = policy",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestTheFinalGuardReadsEverythingAgain"
        "::test_a_configuration_changed_after_the_claim_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="final_guard_reads_the_market_session_again",
        rule="The session is judged from the clock fetched after the claim",
        path=_USECASE,
        original=(
            "                    market_is_open=clock.is_open,\n"
            "                    market_next_close=clock.next_close,"
        ),
        mutated=(
            "                    market_is_open=evidence.market_is_open,\n"
            "                    market_next_close=evidence.market_next_close,"
        ),
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestTheFinalGuardReadsEverythingAgain"
        "::test_a_market_that_closes_after_the_claim_is_refused",
        expected_fragment="assert",
    ),
    Family(
        name="final_guard_reads_the_quote_again",
        rule="The quote is judged as fetched after the claim",
        path=_USECASE,
        original=(
            "                    quote_bid=_decimal_or_none("
            "None if quote is None else quote.bid),\n"
            "                    quote_ask=_decimal_or_none("
            "None if quote is None else quote.ask),\n"
            "                    quote_captured_at=None if quote is None else quote.captured_at,"
        ),
        mutated=(
            "                    quote_bid=evidence.quote_bid,\n"
            "                    quote_ask=evidence.quote_ask,\n"
            "                    quote_captured_at=evidence.quote_captured_at,"
        ),
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestTheFinalGuardReadsEverythingAgain"
        "::test_a_quote_that_goes_stale_after_the_claim_is_refused",
        expected_fragment="assert",
    ),
    # T1 -- the liquidation deadline is never extended by host skew
    Family(
        name="liquidation_deadline_never_later_than_the_calendar",
        rule="Host skew can shorten the liquidation deadline but never extend it",
        path=_DOMAIN,
        original=(
            "    return min(liquidation_at, proposal_basis.on_broker_timeline(liquidation_at))"
        ),
        mutated="    return proposal_basis.on_broker_timeline(liquidation_at)",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestTheLiquidationDeadlineIsNeverExtendedBySkew"
        "::test_a_slow_host_at_evaluation_does_not_move_the_deadline_later",
        expected_fragment="assert",
    ),
    Family(
        name="liquidation_deadline_at_dispatch",
        rule="A dispatch at 15:50 after a slow-host evaluation never submits",
        path=_DOMAIN,
        original=(
            "    return min(liquidation_at, proposal_basis.on_broker_timeline(liquidation_at))"
        ),
        mutated="    return proposal_basis.on_broker_timeline(liquidation_at)",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestTheLiquidationDeadlineAtDispatch"
        "::test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline",
        # Run 1 was a blocker: under the test's 15:30 entry window, and then its 300 s
        # authorization, another rule refused first. With both widened in the test, the
        # rule's removal lets the 15:50 dispatch through -- the defect itself.
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="liquidation_deadline_for_another_date",
        rule="A liquidation deadline written for another date cannot be evaluated, so it refuses",
        path=_DOMAIN,
        original=(
            "        broker_now.earliest.astimezone(zone).date() != written_for\n"
            "        or broker_now.latest.astimezone(zone).date() != written_for"
        ),
        mutated="        False",
        detecting_test=f"{_CORRECTIVE_UNIT}::TestTheLiquidationDeadlineIsNeverExtendedBySkew"
        "::test_a_deadline_written_for_another_date_cannot_be_evaluated",
        expected_fragment="assert",
    ),
    # D2 -- an uncertain outcome is never a refusal and never a second submission
    Family(
        name="definitive_refusal_statuses",
        rule="Only 400, 401, 403 and 422 can prove an order was refused",
        path=_DOMAIN,
        # SEND-BOUNDARY CORRECTION: the status set is the key set of the documented-code
        # table and is derived from it, so the table is the ONE place the rule can be
        # broken. The former early `status not in DEFINITIVE_...` exit was removed
        # because the table's `.get(status, frozenset())` made it a masking duplicate
        # (found as a surviving mutation in the exact-SHA verification of 80d1faa).
        original=(
            "        422: frozenset({40010001, 42210000}),\n"
            "    }\n"
            ")\n"
            "\n"
            "#: HTTP statuses on `POST /v2/orders` under which"
        ),
        mutated=(
            "        422: frozenset({40010001, 42210000}),\n"
            "        500: frozenset({50010000}),\n"
            "    }\n"
            ")\n"
            "\n"
            "#: HTTP statuses on `POST /v2/orders` under which"
        ),
        detecting_test=f"{_CORRECTIVE_UNIT}::TestOnlyADefinitiveRefusalIsARefusal"
        "::test_anything_else_is_uncertain",
        expected_fragment="assert",
    ),
    Family(
        name="definitive_refusal_requires_the_brokers_document",
        rule="A definitive status proves nothing without the broker's JSON error object",
        path=_DOMAIN,
        original="    if not isinstance(parsed, dict):\n        return None",
        mutated=(
            "    if not isinstance(parsed, dict):\n"
            '        return {"code": 42210000, "message": "x"}'
        ),
        # The 422 list-body case turns into a "document" carrying a DOCUMENTED code and is
        # then a refusal. (A fabricated code 0 is refused by the code table regardless, so
        # that earlier mutation had become equivalent -- exact-SHA verification of 80d1faa.)
        detecting_test=f"{_CORRECTIVE_UNIT}::TestOnlyADefinitiveRefusalIsARefusal"
        "::test_anything_else_is_uncertain",
        expected_fragment="assert",
    ),
    Family(
        name="adapter_uncertain_status_is_ambiguous",
        rule="The adapter reports a non-definitive order answer as ambiguous, not as a refusal",
        path=_ADAPTER,
        original="        kind = classify_broker_refusal(status, sanitized)",
        mutated=(
            "        kind = (\n"
            "            BrokerRefusalKind.DEFINITIVE_REFUSAL\n"
            "            if status >= 400\n"
            "            else classify_broker_refusal(status, sanitized)\n"
            "        )"
        ),
        detecting_test=f"{_HTTP}::TestErrorStatusesAreReportedFaithfully"
        "::test_an_uncertain_status_is_never_reported_as_a_refusal",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="dispatch_uncertain_status_is_unknown",
        rule="The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED",
        path=_USECASE,
        original="            if view is None and is_definitive_broker_refusal(status, sanitized):",
        mutated="            if view is None:",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnUncertainOutcomeIsResolvedNotRetried"
        "::test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission"
        "[fake-500-without-view]",
        expected_fragment="assert",
    ),
    Family(
        name="dispatch_ambiguous_is_unknown",
        rule="A possibly delivered request is SUBMISSION_UNKNOWN, never terminal",
        path=_USECASE,
        original=(
            "                target=PaperExecutionState.SUBMISSION_UNKNOWN,\n"
            "                at=at,\n"
            '                failure_code="AMBIGUOUS",'
        ),
        mutated=(
            "                target=PaperExecutionState.REJECTED,\n"
            "                at=at,\n"
            '                failure_code="AMBIGUOUS",'
        ),
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnUncertainOutcomeIsResolvedNotRetried"
        "::test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission"
        "[timeout-after-send]",
        expected_fragment="assert",
    ),
    Family(
        name="dispatch_unexpected_fault_is_unknown",
        rule="A fault after the send guard passed is recorded as SUBMISSION_UNKNOWN",
        path=_USECASE,
        original="        except Exception as error:  # noqa: BLE001 - see below",
        mutated="        except BrokerNotSentError as error:  # mutated",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnUncertainOutcomeIsResolvedNotRetried"
        "::test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission"
        "[unexpected-fault-after-send]",
        expected_fragment="the process misbehaved",
    ),
    # D3 -- an interrupted dispatch can be reconciled, a live one is left alone
    Family(
        name="reconcile_a_stale_in_progress_attempt",
        rule="An attempt left IN_PROGRESS is reconciled to the broker's answer",
        path=_USECASE,
        original=(
            "        if attempt.state in {\n"
            "            PaperExecutionState.SUBMISSION_IN_PROGRESS,\n"
            "            PaperExecutionState.SUBMISSION_UNKNOWN,\n"
            "        }:"
        ),
        mutated=(
            "        if attempt.state in {\n"
            "            PaperExecutionState.SUBMISSION_UNKNOWN,\n"
            "        }:"
        ),
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnInterruptedDispatchCanBeReconciled"
        "::test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer",
        expected_fragment="FILLED",
    ),
    Family(
        name="reconcile_leaves_a_live_dispatch_alone",
        rule="An attempt IN_PROGRESS for less than the not-found window is not looked up",
        path=_USECASE,
        original=(
            "            if (command.at - started).total_seconds() < "
            "MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS:\n"
            "                return attempt"
        ),
        mutated="            if False:\n                return attempt",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnInterruptedDispatchCanBeReconciled"
        "::test_a_live_dispatch_is_left_to_finish",
        # Run 1 named `lookups`: the state assertion that precedes it fails first.
        expected_fragment="SUBMISSION_IN_PROGRESS",
    ),
    Family(
        name="reconcile_absence_never_rejects_a_live_dispatch",
        rule="A not-found answer never resolves an attempt that may still be sending",
        path=_USECASE,
        original="        if dispatch_may_be_live:",
        mutated="        if False:",
        detecting_test=f"{_CORRECTIVE_HANDLERS}::TestAnInterruptedDispatchCanBeReconciled"
        "::test_absence_while_the_dispatcher_is_still_sending_never_rejects",
        # Without the rule the second not-found answer records REJECTED, the order is
        # sent anyway, and recording its acknowledgement hits the immutable terminal row.
        expected_fragment="terminal and is immutable",
    ),
    # P2 -- a terminal attempt is immutable
    Family(
        name="repository_refuses_a_terminal_transition",
        rule="The repository refuses any transition of a terminal attempt, legibly",
        path=_REPOSITORY,
        original=(
            '            if current and _member(current[0], "state", PaperExecutionState) in ('
        ),
        mutated=(
            '            if False and current and _member(current[0], "state", '
            "PaperExecutionState) in ("
        ),
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestATerminalAttemptIsImmutableInTheDatabase"
        "::test_the_repository_refuses_before_the_database_is_asked",
        expected_fragment="terminal and is immutable",
    ),
    Family(
        name="database_terminal_attempt_immutable",
        rule="The database refuses every UPDATE of a terminal attempt, same-state included",
        path=_CORRECTIVE_MIGRATION,
        original=(
            "    IF OLD.state IN (__TERMINAL__) THEN\n"
            "        RAISE EXCEPTION\n"
            "            'attempt % is terminal in state % and is immutable',"
        ),
        mutated=(
            "    IF FALSE THEN\n"
            "        RAISE EXCEPTION\n"
            "            'attempt % is terminal in state % and is immutable',"
        ),
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestATerminalAttemptIsImmutableInTheDatabase"
        "::test_no_update_of_a_filled_attempt_is_accepted[identical-same-state]",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_broker_identity_written_once",
        rule="The database refuses rewriting a recorded broker order id or instant",
        path=_CORRECTIVE_MIGRATION,
        original="    IF (OLD.broker_order_id IS NOT NULL",
        mutated="    IF FALSE AND (OLD.broker_order_id IS NOT NULL",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestATerminalAttemptIsImmutableInTheDatabase"
        "::test_a_live_attempt_cannot_rewrite_what_was_already_recorded[broker_order_id]",
        expected_fragment="DID NOT RAISE",
    ),
    # P3 and D1 at the database boundary
    Family(
        name="database_authorization_equals_its_preview",
        rule="The database refuses an authorization whose quote ask is not the preview's",
        path=_CORRECTIVE_MIGRATION,
        original="        OR preview_row.quote_ask IS DISTINCT FROM NEW.quote_ask\n",
        mutated="",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAnAuthorizationEqualsThePreviewItNames"
        "::test_any_field_other_than_the_previews_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_authorization_inserted_unconsumed",
        rule="The database refuses an authorization inserted already consumed",
        path=_CORRECTIVE_MIGRATION,
        original=(
            "    IF NEW.consumed_at IS NOT NULL OR NEW.consumed_by_attempt_id IS NOT NULL THEN"
        ),
        mutated="    IF FALSE THEN",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAnAuthorizationEqualsThePreviewItNames"
        "::test_an_authorization_inserted_already_consumed_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_authorization_never_outlives_the_intent",
        rule="The database refuses an authorization expiring after its intent",
        path=_CORRECTIVE_MIGRATION,
        original="    IF NEW.expires_at > preview_row.intent_expires_at THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAnAuthorizationEqualsThePreviewItNames"
        "::test_an_authorization_outliving_its_intent_is_refused_to_the_tick",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_authorization_within_preview_freshness",
        rule="The database refuses an authorization granted after the preview's freshness limit",
        path=_CORRECTIVE_MIGRATION,
        original="    IF NEW.basis_host_at IS NOT NULL\n",
        mutated="    IF FALSE AND NEW.basis_host_at IS NOT NULL\n",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAnAuthorizationEqualsThePreviewItNames"
        "::test_an_authorization_after_the_previews_freshness_limit_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_refused_preview_not_authorizable",
        rule="The database refuses authorizing a preview that carries refusals",
        path=_CORRECTIVE_MIGRATION,
        original="    IF preview_row.refusals <> '[]' THEN",
        mutated="    IF FALSE THEN",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAnAuthorizationEqualsThePreviewItNames"
        "::test_a_preview_with_refusals_cannot_be_authorized",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_preview_carries_the_configuration_policy",
        rule="The database refuses a preview whose quote age limit is not the configuration's",
        path=_CORRECTIVE_MIGRATION,
        original=(
            "        OR configuration_row.maximum_market_data_age_seconds\n"
            "            IS DISTINCT FROM NEW.quote_maximum_age_seconds\n"
        ),
        mutated="",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAPreviewCarriesTheConfigurationsPolicy"
        "::test_a_looser_or_different_policy_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_preview_carries_the_intent_order",
        rule="The database refuses a preview whose limit price is not the intent's",
        path=_CORRECTIVE_MIGRATION,
        original="        OR intent_row.limit_price IS DISTINCT FROM NEW.limit_price\n",
        mutated="",
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAPreviewCarriesTheConfigurationsPolicy"
        "::test_an_order_other_than_the_intents_is_refused",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="database_authorizable_preview_within_its_cap",
        rule="The database CHECK refuses an authorizable preview priced above its cap",
        path=_CORRECTIVE_MIGRATION,
        original='            "OR limit_price * quantity <= maximum_notional",',
        mutated='            "OR true",',
        detecting_test=f"{_CORRECTIVE_POSTGRES}::TestAPreviewCarriesTheConfigurationsPolicy"
        "::test_an_authorizable_preview_above_its_cap_is_refused_by_check",
        # The AFTER INSERT policy guard still refuses the row, with its own message and
        # a different exception class; that it reports itself is the detection.
        expected_fragment="does not carry the send-time policy",
    ),
    # Item 4 -- the exact schema head
    Family(
        name="schema_head_exact",
        rule="Any revision set other than exactly the M085 head refuses",
        path=_REPOSITORY,
        original="    if revisions != [M085_SCHEMA_HEAD]:",
        mutated="    if False:",
        detecting_test=f"{_COMPOSITION_TESTS}::TestTheSchemaHeadIsExact"
        "::test_any_other_revision_refuses_before_the_body_runs",
        # Run 1 named `DID NOT RAISE`: with the check removed the body runs, and the
        # test's own `pytest.fail` inside it is what reports the mutation.
        expected_fragment="the body must not run against a mismatched schema",
    ),
    Family(
        name="schema_head_checked_by_the_composition",
        rule="The paper runtime checks the schema head before handing anything out",
        path=_COMPOSITION,
        original="        require_exact_m085_schema_head(service)\n",
        mutated="",
        detecting_test=f"{_COMPOSITION_TESTS}::TestTheSchemaHeadIsExact"
        "::test_any_other_revision_refuses_before_the_body_runs",
        # Run 1 named `DID NOT RAISE`: with the check removed the body runs, and the
        # test's own `pytest.fail` inside it is what reports the mutation.
        expected_fragment="the body must not run against a mismatched schema",
    ),
    # Item 8 -- the legacy dry run is refused, not run
    Family(
        name="legacy_dry_run_refused",
        rule="--dry-run refuses before any runtime, writer, socket or file is touched",
        path=_ACCEPTANCE_TOOL,
        original="    if arguments.dry_run:",
        mutated="    if False:",
        detecting_test=f"{_DRY_RUN_TESTS}"
        "::test_dry_run_is_refused_before_any_record_connection_or_file",
        expected_fragment="the dry run reached",
    ),
    # == IDENTITY-SAFETY CORRECTION (F1) =====================================
    Family(
        name="duplicate_identity_422_is_not_a_refusal",
        rule="Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal",
        path=_DOMAIN,
        original="    if about_identity:",
        mutated="    if False:",
        detecting_test=f"{_IDENTITY_UNIT}::TestA422IsClassifiedSemantically"
        "::test_the_documented_duplicate_answer_is_an_existing_identity",
        expected_fragment="assert",
    ),
    Family(
        name="unknown_422_shape_fails_closed",
        rule="A 422 without the broker's integer code is uncertain, not a refusal",
        path=_DOMAIN,
        original="    if isinstance(code, bool) or not isinstance(code, int):\n        return None",
        mutated="    if False:\n        return None",
        detecting_test=f"{_IDENTITY_UNIT}::TestA422IsClassifiedSemantically"
        "::test_an_unknown_shape_is_uncertain",
        expected_fragment="assert",
    ),
    Family(
        name="identity_collision_looks_the_identity_up",
        rule="A collision is resolved by looking up the SAME client_order_id, not by guessing",
        path=_USECASE,
        original=(
            "            status, view, sanitized = self._broker.fetch_order_by_client_order_id(\n"
            "                order.client_order_id\n"
            "            )\n"
            "        except Exception as error:  # noqa: BLE001 - recorded, never retried"
        ),
        mutated=(
            '            status, view, sanitized = 404, None, "{}"\n'
            "        except Exception as error:  # noqa: BLE001 - recorded, never retried"
        ),
        detecting_test=f"{_LINEAGE_UNIT}::TestAnIdentityObservedBeforeTheSendIsNotAttributed"
        "::test_an_exact_match_found_before_sending_is_observed_not_adopted",
        expected_fragment="assert",
    ),
    Family(
        name="pre_send_lookup_uses_the_derived_identity",
        rule="The identity asked about before sending is the derived one, not a replacement",
        path=_USECASE,
        original=(
            "                    self._broker.fetch_order_by_client_order_id("
            "fresh.order.client_order_id)"
        ),
        mutated=(
            "                    self._broker.fetch_order_by_client_order_id("
            'fresh.order.client_order_id + "-2")'
        ),
        detecting_test=f"{_LINEAGE_UNIT}::TestAnIdentityObservedBeforeTheSendIsNotAttributed"
        "::test_an_exact_match_found_before_sending_is_observed_not_adopted",
        expected_fragment="assert",
    ),
    Family(
        name="no_resend_after_a_collision",
        rule="An intent with any attempt is never dispatched again, collision included",
        path=_USECASE,
        original=(
            "        existing = self._attempts.for_intent(command.intent_governance_id)\n"
            "        if existing is not None:"
        ),
        mutated=(
            "        existing = self._attempts.for_intent(command.intent_governance_id)\n"
            "        if False:"
        ),
        detecting_test=f"{_IDENTITY_UNIT}::TestAnExistingIdentityIsReconciledNotRejected"
        "::test_a_collision_is_never_followed_by_a_second_dispatch",
        expected_fragment="assert",
    ),
    Family(
        name="identity_match_checks_the_symbol",
        rule="A broker order with another symbol is never adopted as ours",
        path=_DOMAIN,
        original=(
            '    if symbol is None or symbol.upper() != getattr(expected, "symbol", None):\n'
            '        mismatches.append("symbol")'
        ),
        mutated='    if False:\n        mismatches.append("symbol")',
        detecting_test=f"{_IDENTITY_UNIT}::TestOnlyTheExactAuthorizedOrderIsAdopted"
        "::test_a_mismatched_field_is_a_collision[symbol-TSLA]",
        expected_fragment="assert",
    ),
    Family(
        name="identity_match_checks_the_quantity",
        rule="A broker order with another quantity is never adopted as ours",
        path=_DOMAIN,
        original=(
            '        if Decimal(actual_text("quantity") or "x") != '
            'Decimal(getattr(expected, "quantity", -1)):\n'
            '            mismatches.append("quantity")'
        ),
        mutated='        if False:\n            mismatches.append("quantity")',
        detecting_test=f"{_IDENTITY_UNIT}::TestOnlyTheExactAuthorizedOrderIsAdopted"
        "::test_a_mismatched_field_is_a_collision[quantity-2]",
        expected_fragment="assert",
    ),
    Family(
        name="identity_match_checks_the_side",
        rule="A broker order with another side is never adopted as ours",
        path=_DOMAIN,
        original=(
            '    if side is None or side.upper() != str(getattr(expected, "side", "")).upper():\n'
            '        mismatches.append("side")'
        ),
        mutated='    if False:\n        mismatches.append("side")',
        detecting_test=f"{_IDENTITY_UNIT}::TestOnlyTheExactAuthorizedOrderIsAdopted"
        "::test_a_mismatched_field_is_a_collision[side-sell]",
        expected_fragment="assert",
    ),
    Family(
        name="reconcile_recovers_unknown_after_restart",
        rule="A new process reconciles an UNKNOWN attempt instead of leaving it",
        path=_USECASE,
        original=(
            "        if attempt.is_terminal:\n"
            "            return attempt\n"
            "        if attempt.state is PaperExecutionState.SUBMISSION_IN_PROGRESS:"
        ),
        mutated=(
            "        if attempt.is_terminal or attempt.state is "
            "PaperExecutionState.SUBMISSION_UNKNOWN:\n"
            "            return attempt\n"
            "        if attempt.state is PaperExecutionState.SUBMISSION_IN_PROGRESS:"
        ),
        detecting_test=f"{_IDENTITY_UNIT}::TestRecoveryAfterRestart"
        "::test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity",
        expected_fragment="assert",
    ),
    Family(
        name="reconcile_refuses_a_mismatching_order",
        rule="Reconciliation never adopts a broker order that differs from the authorized one",
        path=_USECASE,
        original=(
            "        if mismatches:\n"
            "            self._events.append(\n"
            "                PaperExecutionEvent(\n"
            '                    event_id=f"EVT-{attempt.attempt_id}-RECON-MISMATCH-'
            '{sequence}"[:64],'
        ),
        mutated=(
            "        if False:\n"
            "            self._events.append(\n"
            "                PaperExecutionEvent(\n"
            '                    event_id=f"EVT-{attempt.attempt_id}-RECON-MISMATCH-'
            '{sequence}"[:64],'
        ),
        detecting_test=f"{_LINEAGE_UNIT}::TestLegitimateRecoveryAfterALostAcknowledgement"
        "::test_a_differing_term_is_never_adopted_even_with_lineage[symbol-TSLA]",
        expected_fragment="assert",
    ),
    Family(
        name="database_rebuilt_meets_existing_identity",
        rule="Against PostgreSQL, a rebuilt database meets the broker's order and sends nothing",
        path=_USECASE,
        original=(
            "                if existing_order is not None:\n"
            "                    raise BrokerIdentityExistsError("
        ),
        mutated=("                if False:\n                    raise BrokerIdentityExistsError("),
        detecting_test=f"{_IDENTITY_POSTGRES}"
        "::test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending",
        expected_fragment="assert",
    ),
    # == M084 mechanical freeze ==============================================
    Family(
        name="frozen_path_guard_covers_m084",
        rule="The frozen-path guard governs MILESTONE-084 as well as MILESTONE-083",
        path=_FROZEN_GUARD,
        original=(
            '    "M084": (\n'
            '        r"^src/empirical_platform/decision_candidate/(evaluation_context|"'
        ),
        mutated=(
            '    "M084_UNFROZEN": (\n'
            '        r"^src/empirical_platform/decision_candidate/(evaluation_context|"'
        ),
        detecting_test=f"{_FROZEN_TESTS}::TestBothMilestonesAreGoverned"
        "::test_the_guard_freezes_exactly_m083_and_m084",
        expected_fragment="assert",
    ),
    Family(
        name="frozen_path_guard_pins_m084_to_the_ratified_commit",
        rule="M084 is compared against the ratified commit, not against whatever HEAD holds",
        path=_FROZEN_GUARD,
        original='_M084_BASE_GROUPS = ("11271346", "23b25178", "b4d98236", "d5ab75f8", "f2134760")',
        mutated='_M084_BASE_GROUPS = ("a2240767", "54fb3890", "9ee04c24", "64e50e51", "df12d7ad")',
        detecting_test=f"{_FROZEN_TESTS}::TestBothMilestonesAreGoverned"
        "::test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base",
        expected_fragment="assert",
    ),
    # == SEND-BOUNDARY CORRECTION (A6) =========================================
    Family(
        name="send_boundary_no_read_after_the_decision",
        rule="Nothing sits between the final decision and the transport's POST",
        path=_USECASE,
        original="                # 5. Nothing else. The transport sends on return.",
        mutated=(
            "                self._broker.fetch_order_by_client_order_id("
            "fresh.order.client_order_id)"
        ),
        detecting_test=f"{_SEND_BOUNDARY}"
        "::test_the_boundary_reads_everything_before_the_kill_switch_and_samples_time_last",
        expected_fragment="assert",
    ),
    Family(
        name="send_boundary_kill_switch_read_after_the_slow_reads",
        rule="The kill switch is read fresh after the slow reads, not from the pre-claim snapshot",
        path=_USECASE,
        original=(
            "                kill_switch_engaged = self._kill_switch.is_engaged()\n"
            "                # 4."
        ),
        mutated=(
            "                kill_switch_engaged = evidence.kill_switch_engaged\n"
            "                # 4."
        ),
        detecting_test=f"{_SEND_BOUNDARY}"
        "::test_the_kill_switch_engaged_during_a_slow_read_stops_the_post[lookup]",
        expected_fragment="assert",
    ),
    Family(
        name="send_boundary_time_sampled_after_the_reads",
        rule="Deadlines are judged on time sampled after every slow read",
        path=_USECASE,
        original=(
            "                    host_now=timing.now(),\n"
            "                    broker_now=timing.broker_now(),"
        ),
        mutated=(
            "                    host_now=command.at,\n"
            "                    broker_now=BoundedInstant(earliest=command.at, latest=command.at),"
        ),
        detecting_test=f"{_SEND_BOUNDARY}"
        "::test_the_authorization_expiring_during_a_slow_read_stops_the_post[lookup]",
        expected_fragment="assert",
    ),
    Family(
        name="inconclusive_lookup_is_not_a_rejection",
        rule="An inconclusive pre-send identity lookup is recoverable, not a terminal refusal",
        path=_USECASE,
        original=(
            "                    raise BrokerIdentityUnresolvedError(\n"
            '                        "the broker could not confirm that this client_order_id '
            'is unused "'
        ),
        mutated=(
            "                    raise PaperExecutionRefusedError(\n"
            '                        "the broker could not confirm that this client_order_id '
            'is unused "'
        ),
        detecting_test=f"{_LINEAGE_UNIT}::TestAnInconclusiveLookupBeforeTheSendStaysRecoverable"
        "::test_it_becomes_unknown_with_nothing_sent[http-500]",
        expected_fragment="assert",
    ),
    Family(
        name="unresolved_identity_recovered_after_restart",
        rule="A new process reconciles an unresolved identity instead of leaving it",
        path=_USECASE,
        original=(
            "        if attempt.is_terminal:\n"
            "            return attempt\n"
            "        if attempt.state is PaperExecutionState.SUBMISSION_IN_PROGRESS:"
        ),
        mutated=(
            "        if attempt.is_terminal or attempt.state is "
            "PaperExecutionState.SUBMISSION_UNKNOWN:\n"
            "            return attempt\n"
            "        if attempt.state is PaperExecutionState.SUBMISSION_IN_PROGRESS:"
        ),
        detecting_test=f"{_LINEAGE_UNIT}::TestAnInconclusiveLookupBeforeTheSendStaysRecoverable"
        "::test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it",
        expected_fragment="assert",
    ),
    Family(
        name="reconcile_requires_lineage_before_adoption",
        rule="An order under our identity is adopted only by an attempt that may have sent it",
        path=_USECASE,
        original="            if not attempt_may_have_transmitted(",
        mutated="            if False and not attempt_may_have_transmitted(",
        detecting_test=f"{_LINEAGE_UNIT}::TestAnIdentityObservedBeforeTheSendIsNotAttributed"
        "::test_nothing_is_ever_resent_and_no_later_authorization_reopens_it",
        expected_fragment="assert",
    ),
    Family(
        name="reconcile_verifies_the_account",
        rule="A found order is adopted only when the broker client's account is the authorized one",
        path=_USECASE,
        original="                if account.account_reference != authorization.account_reference:",
        mutated="                if False:",
        detecting_test=f"{_LINEAGE_UNIT}::TestLegitimateRecoveryAfterALostAcknowledgement"
        "::test_an_account_that_is_not_the_authorized_one_is_never_adopted",
        expected_fragment="assert",
    ),
    Family(
        name="lineage_unsent_never_attributed",
        rule="An attempt recorded as not having sent can never be attributed a found order",
        path=_DOMAIN,
        original="    if recorded_unsent or code in UNSENT_IDENTITY_FAILURE_CODES:",
        mutated="    if False:",
        detecting_test=f"{_LINEAGE_UNIT}::TestLineage"
        "::test_an_event_recording_no_send_outranks_a_state_that_would_otherwise_qualify"
        "[SUBMISSION_UNKNOWN-AMBIGUOUS-CLIENT_ORDER_ID_COLLISION]",
        expected_fragment="assert",
    ),
    Family(
        name="unknown_error_code_is_uncertain",
        rule="A refusal code Alpaca does not document for that status proves nothing",
        path=_DOMAIN,
        original="    if code not in RECOGNIZED_DEFINITIVE_REFUSAL_CODES.get(status, frozenset()):",
        mutated="    if False:",
        detecting_test=f"{_LINEAGE_UNIT}::TestRefusalsAreClassifiedByDocumentedSemantics"
        "::test_unknown_or_inconsistent_semantics_are_uncertain",
        expected_fragment="assert",
    ),
    Family(
        name="acknowledgement_terms_compared_canonically",
        rule="Our own POST's acknowledgement is compared on every authorized term",
        path=_ADAPTER,
        original="        mismatches = list(order_terms_mismatches(expected=order, actual=view))",
        mutated="        mismatches: list[str] = []",
        detecting_test=f"{_ACK_HTTP}::test_a_differing_acknowledgement_is_uncertain",
        expected_fragment="DID NOT RAISE",
    ),
    Family(
        name="terms_compare_limit_price",
        rule="A broker order with another limit price is never ours",
        path=_DOMAIN,
        original='                mismatches.append("limit_price")',
        mutated="                pass",
        detecting_test=f"{_LINEAGE_UNIT}::TestTheCanonicalTermsComparison"
        "::test_every_authorized_term_is_compared[limit_price-5.00]",
        expected_fragment="assert",
    ),
    Family(
        name="terms_compare_time_in_force",
        rule="A broker order with another time_in_force is never ours",
        path=_DOMAIN,
        original='        mismatches.append("time_in_force")',
        mutated="        pass",
        detecting_test=f"{_LINEAGE_UNIT}::TestTheCanonicalTermsComparison"
        "::test_every_authorized_term_is_compared[time_in_force-gtc]",
        expected_fragment="assert",
    ),
    Family(
        name="terms_compare_extended_hours",
        rule="A broker order with another extended_hours flag is never ours",
        path=_DOMAIN,
        original='        mismatches.append("extended_hours")',
        mutated="        pass",
        detecting_test=f"{_LINEAGE_UNIT}::TestTheCanonicalTermsComparison"
        "::test_every_authorized_term_is_compared[extended_hours-True]",
        expected_fragment="assert",
    ),
    Family(
        name="terms_compare_bound_broker_order_id",
        rule="A broker id already bound to the attempt must stay consistent",
        path=_DOMAIN,
        original='        mismatches.append("broker_order_id")',
        mutated="        pass",
        detecting_test=f"{_LINEAGE_UNIT}::TestTheCanonicalTermsComparison"
        "::test_a_bound_broker_order_id_must_stay_consistent",
        expected_fragment="assert",
    ),
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest() -> str:
    """One SHA-256 over the path and bytes of every file under `_TREE_ROOTS`.

    Byte-compiled caches are excluded: running a test writes them, and they are not
    source. Anything else that differs after the campaign is a restoration failure.
    """
    digest = hashlib.sha256()
    for root in _TREE_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(_digest(path).encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def _forget_bytecode(path: Path) -> None:
    """Delete the byte-compiled cache of one source file.

    Python validates a `.pyc` by the source's size and mtime at one-second
    resolution. A mutation whose replacement has the SAME LENGTH as the original,
    written and restored within one second, therefore leaves a cache compiled from
    the MUTATED source that the restored run happily imports -- and the campaign then
    reports a real detection as "does not pass again after restoration" (found by the
    M084 frozen-path-pin family, whose two commit ids are both forty characters).
    """
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for compiled in cache.glob(f"{path.stem}.*.pyc"):
            compiled.unlink(missing_ok=True)


def _run(test: str) -> tuple[int, str]:
    process = subprocess.run(  # noqa: S603 - fixed vector, no shell
        [
            sys.executable,
            "-B",
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
    _forget_bytecode(path)
    try:
        mutated_code, mutated_output = _run(family.detecting_test)
    finally:
        path.write_text(source, encoding="utf-8", newline="\n")
        _forget_bytecode(path)

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

    tree_before = tree_digest()
    print(f"tree digest before: {tree_before}", flush=True)
    results: list[Result] = []
    for index, family in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {family.name} ... ", end="", flush=True)
        result = run_family(family)
        results.append(result)
        print(result.status, flush=True)
        if result.status != "EXECUTED_PASS":
            print(f"    {result.detail}", flush=True)

    tree_after = tree_digest()
    print(f"tree digest after:  {tree_after}", flush=True)
    tree_restored = tree_after == tree_before

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
        f"**Tree-wide restoration: {'VERIFIED' if tree_restored else 'FAILED'}.** "
        f"SHA-256 over every file under {', '.join(_TREE_ROOTS)} (byte-compiled caches "
        f"excluded): before `{tree_before}`, after `{tree_after}`.",
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
    if not tree_restored:
        print("TREE-WIDE RESTORATION FAILED", file=sys.stderr)
        return 1
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
