"""Reviewed M085 physical contract retained by the integrated v1 schema.

Captured from PostgreSQL 16 after applying the committed main migration chain to
full v1 head on a disposable server. The deployment test compares this contract
against both historical M085 and full head. Keep definitions readable: a revision
stamp and table names alone do not prove policy, immutability or exactly-once guards.
Function entries are SHA-256 fingerprints of the committed PL/pgSQL bodies,
search path, security mode and language; grouped hex strings are public digests.
No runtime regeneration: changing this contract requires an explicit code review.
"""

from __future__ import annotations

M085_CONTRACT_SELECT = """
WITH required AS (
    SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname = ANY(:tables)
)
SELECT 'column:' || r.relname || '.' || a.attname AS object_key,
       format_type(a.atttypid, a.atttypmod) || ':' || a.attnotnull::text AS definition
FROM required r JOIN pg_attribute a ON a.attrelid=r.oid
WHERE a.attnum > 0 AND NOT a.attisdropped
UNION ALL
SELECT 'constraint:' || r.relname || '.' || c.conname,
       pg_get_constraintdef(c.oid) || ':' || c.convalidated::text
FROM required r JOIN pg_constraint c ON c.conrelid=r.oid
UNION ALL
SELECT 'trigger:' || r.relname || '.' || t.tgname,
       pg_get_triggerdef(t.oid) || ':' || t.tgenabled::text
FROM required r JOIN pg_trigger t ON t.tgrelid=r.oid WHERE NOT t.tgisinternal
UNION ALL
SELECT DISTINCT 'function:' || p.proname,
       encode(sha256(convert_to(p.prosrc || ':' || coalesce(array_to_string(p.proconfig, ','), '')
       || ':' || p.prosecdef::text || ':' || l.lanname, 'UTF8')), 'hex')
FROM required r JOIN pg_trigger t ON t.tgrelid=r.oid
JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_language l ON l.oid=p.prolang
WHERE NOT t.tgisinternal
"""

M085_CONTRACT: dict[str, str] = {
    "column:paper_account_snapshot.account_blocked": "boolean:true",
    "column:paper_account_snapshot.account_reference": "character varying(64):true",
    "column:paper_account_snapshot.account_status": "character varying(32):true",
    "column:paper_account_snapshot.buying_power": "numeric(24,8):true",
    "column:paper_account_snapshot.captured_at": "timestamp with time zone:true",
    "column:paper_account_snapshot.cash": "numeric(24,8):true",
    "column:paper_account_snapshot.currency": "character varying(3):true",
    "column:paper_account_snapshot.endpoint_host": "character varying(64):true",
    "column:paper_account_snapshot.environment": "character varying(8):true",
    "column:paper_account_snapshot.equity": "numeric(24,8):true",
    "column:paper_account_snapshot.multiplier": "character varying(8):true",
    "column:paper_account_snapshot.shorting_enabled": "boolean:true",
    "column:paper_account_snapshot.snapshot_id": "character varying(64):true",
    "column:paper_account_snapshot.trade_suspended_by_user": "boolean:true",
    "column:paper_account_snapshot.trading_blocked": "boolean:true",
    "column:paper_account_snapshot.transfers_blocked": "boolean:true",
    "column:paper_broker_acknowledgement.acknowledgement_id": "character varying(64):true",
    "column:paper_broker_acknowledgement.attempt_id": "character varying(64):true",
    "column:paper_broker_acknowledgement.broker_order_id": "character varying(64):false",
    "column:paper_broker_acknowledgement.broker_status": "character varying(32):false",
    "column:paper_broker_acknowledgement.client_order_id_echo": ("character varying(64):false"),
    "column:paper_broker_acknowledgement.http_status": "integer:true",
    "column:paper_broker_acknowledgement.kind": "character varying(16):true",
    "column:paper_broker_acknowledgement.observed_at": "timestamp with time zone:true",
    "column:paper_broker_acknowledgement.payload_digest": "character varying(64):true",
    "column:paper_broker_acknowledgement.sanitized_payload": "text:true",
    "column:paper_broker_acknowledgement.sequence": "integer:true",
    "column:paper_decision_time_basis.approved_fingerprint": "character varying(64):true",
    "column:paper_decision_time_basis.basis_broker_earliest_at": ("timestamp with time zone:true"),
    "column:paper_decision_time_basis.basis_broker_latest_at": ("timestamp with time zone:true"),
    "column:paper_decision_time_basis.basis_host_at": "timestamp with time zone:true",
    "column:paper_decision_time_basis.basis_host_requested_at": ("timestamp with time zone:true"),
    "column:paper_decision_time_basis.broker_endpoint_host": "character varying(64):true",
    "column:paper_decision_time_basis.decided_at": "timestamp with time zone:true",
    "column:paper_decision_time_basis.decision_expires_at": ("timestamp with time zone:true"),
    "column:paper_decision_time_basis.decision_governance_id": ("character varying(64):true"),
    "column:paper_decision_time_basis.proposal_governance_id": ("character varying(64):true"),
    "column:paper_decision_time_basis.proposal_version": "integer:true",
    "column:paper_execution_attempt.acknowledged_at": "timestamp with time zone:false",
    "column:paper_execution_attempt.attempt_id": "character varying(64):true",
    "column:paper_execution_attempt.authorization_id": "character varying(64):true",
    "column:paper_execution_attempt.broker_order_id": "character varying(64):false",
    "column:paper_execution_attempt.broker_status": "character varying(32):false",
    "column:paper_execution_attempt.claimed_at": "timestamp with time zone:true",
    "column:paper_execution_attempt.client_order_id": "character varying(64):true",
    "column:paper_execution_attempt.failure_code": "character varying(32):false",
    "column:paper_execution_attempt.failure_detail": "character varying(500):false",
    "column:paper_execution_attempt.filled_avg_price": "numeric(20,8):false",
    "column:paper_execution_attempt.filled_quantity": "numeric(24,8):false",
    "column:paper_execution_attempt.intent_governance_id": "character varying(64):true",
    "column:paper_execution_attempt.request_fingerprint": "character varying(64):true",
    "column:paper_execution_attempt.state": "character varying(32):true",
    "column:paper_execution_attempt.submitted_at": "timestamp with time zone:false",
    "column:paper_execution_attempt.terminal_at": "timestamp with time zone:false",
    "column:paper_execution_authorization.account_reference": "character varying(64):true",
    "column:paper_execution_authorization.authorization_id": "character varying(64):true",
    "column:paper_execution_authorization.authorized_at": "timestamp with time zone:true",
    "column:paper_execution_authorization.authorized_by": "character varying(64):true",
    "column:paper_execution_authorization.basis_broker_earliest_at": (
        "timestamp with time zone:false"
    ),
    "column:paper_execution_authorization.basis_broker_latest_at": (
        "timestamp with time zone:false"
    ),
    "column:paper_execution_authorization.basis_host_at": "timestamp with time zone:false",
    "column:paper_execution_authorization.basis_host_requested_at": (
        "timestamp with time zone:false"
    ),
    "column:paper_execution_authorization.client_order_id": "character varying(64):true",
    "column:paper_execution_authorization.configuration_governance_id": (
        "character varying(64):true"
    ),
    "column:paper_execution_authorization.configuration_version": "integer:true",
    "column:paper_execution_authorization.consumed_at": "timestamp with time zone:false",
    "column:paper_execution_authorization.consumed_by_attempt_id": ("character varying(64):false"),
    "column:paper_execution_authorization.expires_at": "timestamp with time zone:true",
    "column:paper_execution_authorization.intent_governance_id": ("character varying(64):true"),
    "column:paper_execution_authorization.limit_price": "numeric(20,8):false",
    "column:paper_execution_authorization.maximum_notional": "numeric(20,8):true",
    "column:paper_execution_authorization.order_type": "character varying(16):true",
    "column:paper_execution_authorization.policy_fingerprint": ("character varying(64):true"),
    "column:paper_execution_authorization.preview_binding_fingerprint": (
        "character varying(64):true"
    ),
    "column:paper_execution_authorization.preview_id": "character varying(64):true",
    "column:paper_execution_authorization.preview_version": "integer:true",
    "column:paper_execution_authorization.quantity": "bigint:true",
    "column:paper_execution_authorization.quote_ask": "numeric(20,8):false",
    "column:paper_execution_authorization.quote_bid": "numeric(20,8):false",
    "column:paper_execution_authorization.quote_captured_at": ("timestamp with time zone:false"),
    "column:paper_execution_authorization.request_fingerprint": ("character varying(64):true"),
    "column:paper_execution_authorization.side": "character varying(8):true",
    "column:paper_execution_authorization.symbol": "character varying(32):true",
    "column:paper_execution_event.attempt_id": "character varying(64):false",
    "column:paper_execution_event.detail": "character varying(500):true",
    "column:paper_execution_event.event_id": "character varying(64):true",
    "column:paper_execution_event.event_type": "character varying(48):true",
    "column:paper_execution_event.intent_governance_id": "character varying(64):true",
    "column:paper_execution_event.occurred_at": "timestamp with time zone:true",
    "column:paper_execution_kill_switch.changed_at": "timestamp with time zone:true",
    "column:paper_execution_kill_switch.changed_by": "character varying(64):true",
    "column:paper_execution_kill_switch.engaged": "boolean:true",
    "column:paper_execution_kill_switch.kill_switch_id": "character varying(64):true",
    "column:paper_execution_kill_switch.reason": "character varying(200):true",
    "column:paper_execution_kill_switch.scope": "character varying(16):true",
    "column:paper_execution_kill_switch.version": "integer:true",
    "column:paper_intent_time_basis.approved_fingerprint": "character varying(64):true",
    "column:paper_intent_time_basis.basis_broker_earliest_at": ("timestamp with time zone:true"),
    "column:paper_intent_time_basis.basis_broker_latest_at": ("timestamp with time zone:true"),
    "column:paper_intent_time_basis.basis_host_at": "timestamp with time zone:true",
    "column:paper_intent_time_basis.basis_host_requested_at": ("timestamp with time zone:true"),
    "column:paper_intent_time_basis.broker_endpoint_host": "character varying(64):true",
    "column:paper_intent_time_basis.intent_created_at": "timestamp with time zone:true",
    "column:paper_intent_time_basis.intent_expires_at": "timestamp with time zone:true",
    "column:paper_intent_time_basis.intent_governance_id": "character varying(64):true",
    "column:paper_intent_time_basis.intent_mandatory_liquidation_at": (
        "timestamp with time zone:true"
    ),
    "column:paper_proposal_time_basis.basis_broker_earliest_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.basis_broker_latest_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.basis_host_at": "timestamp with time zone:true",
    "column:paper_proposal_time_basis.basis_host_requested_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.broker_endpoint_host": "character varying(64):true",
    "column:paper_proposal_time_basis.content_fingerprint": "character varying(64):true",
    "column:paper_proposal_time_basis.mandatory_liquidation_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.proposal_created_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.proposal_expires_at": ("timestamp with time zone:true"),
    "column:paper_proposal_time_basis.proposal_governance_id": ("character varying(64):true"),
    "column:paper_proposal_time_basis.proposal_version": "integer:true",
    "column:paper_reconciliation_round.account_reference": "character varying(96):true",
    "column:paper_reconciliation_round.acknowledgement_sequence": "integer:false",
    "column:paper_reconciliation_round.attempt_id": "character varying(64):true",
    "column:paper_reconciliation_round.authorization_id": "character varying(64):true",
    "column:paper_reconciliation_round.broker_earliest_at": ("timestamp with time zone:false"),
    "column:paper_reconciliation_round.broker_latest_at": "timestamp with time zone:false",
    "column:paper_reconciliation_round.client_order_id": "character varying(64):true",
    "column:paper_reconciliation_round.completed_at": "timestamp with time zone:false",
    "column:paper_reconciliation_round.detail": "character varying(500):false",
    "column:paper_reconciliation_round.intent_governance_id": "character varying(64):true",
    "column:paper_reconciliation_round.outcome": "character varying(16):false",
    "column:paper_reconciliation_round.round_id": "character varying(64):true",
    "column:paper_reconciliation_round.sequence": "integer:true",
    "column:paper_reconciliation_round.started_at": "timestamp with time zone:true",
    "column:paper_submission_preview.account_reference": "character varying(64):true",
    "column:paper_submission_preview.account_snapshot_id": "character varying(64):true",
    "column:paper_submission_preview.approved_fingerprint": "character varying(64):true",
    "column:paper_submission_preview.asset_class": "character varying(32):true",
    "column:paper_submission_preview.asset_exchange": "character varying(16):true",
    "column:paper_submission_preview.asset_fractionable": "boolean:true",
    "column:paper_submission_preview.asset_status": "character varying(16):true",
    "column:paper_submission_preview.asset_tradable": "boolean:true",
    "column:paper_submission_preview.binding_fingerprint": "character varying(64):true",
    "column:paper_submission_preview.client_order_id": "character varying(64):true",
    "column:paper_submission_preview.configuration_governance_id": ("character varying(64):true"),
    "column:paper_submission_preview.configuration_version": "integer:true",
    "column:paper_submission_preview.created_at": "timestamp with time zone:true",
    "column:paper_submission_preview.earliest_entry_time": "time without time zone:true",
    "column:paper_submission_preview.extended_hours": "boolean:true",
    "column:paper_submission_preview.intent_expires_at": "timestamp with time zone:true",
    "column:paper_submission_preview.intent_governance_id": "character varying(64):true",
    "column:paper_submission_preview.latest_entry_time": "time without time zone:true",
    "column:paper_submission_preview.limit_price": "numeric(20,8):false",
    "column:paper_submission_preview.market_is_open": "boolean:true",
    "column:paper_submission_preview.market_next_close": "timestamp with time zone:false",
    "column:paper_submission_preview.market_next_open": "timestamp with time zone:false",
    "column:paper_submission_preview.maximum_notional": "numeric(20,8):true",
    "column:paper_submission_preview.maximum_spread_percent": "numeric(20,8):true",
    "column:paper_submission_preview.operator_timezone": "character varying(64):true",
    "column:paper_submission_preview.order_type": "character varying(16):true",
    "column:paper_submission_preview.policy_fingerprint": "character varying(64):true",
    "column:paper_submission_preview.policy_prohibited_instruments": (
        "character varying(32)[]:true"
    ),
    "column:paper_submission_preview.policy_watchlist": "character varying(32)[]:true",
    "column:paper_submission_preview.preview_id": "character varying(64):true",
    "column:paper_submission_preview.preview_version": "integer:true",
    "column:paper_submission_preview.quantity": "bigint:true",
    "column:paper_submission_preview.quote_ask": "numeric(20,8):false",
    "column:paper_submission_preview.quote_bid": "numeric(20,8):false",
    "column:paper_submission_preview.quote_captured_at": "timestamp with time zone:false",
    "column:paper_submission_preview.quote_maximum_age_seconds": "integer:true",
    "column:paper_submission_preview.quote_source": "character varying(32):true",
    "column:paper_submission_preview.refusals": "text:true",
    "column:paper_submission_preview.request_fingerprint": "character varying(64):true",
    "column:paper_submission_preview.side": "character varying(8):true",
    "column:paper_submission_preview.symbol": "character varying(32):true",
    "column:paper_submission_preview.time_in_force": "character varying(8):true",
    "constraint:paper_account_snapshot.ck_paper_account_currency": (
        "CHECK (((currency)::text = 'USD'::text)):true"
    ),
    "constraint:paper_account_snapshot.ck_paper_account_endpoint_host": (
        "CHECK (((endpoint_host)::text = 'paper-api.alpaca.markets'::text)):true"
    ),
    "constraint:paper_account_snapshot.ck_paper_account_environment": (
        "CHECK (((environment)::text = 'PAPER'::text)):true"
    ),
    "constraint:paper_account_snapshot.ck_paper_account_id_present": (
        "CHECK ((btrim((snapshot_id)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f"
        " \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
        "\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_account_snapshot.ck_paper_account_reference_present": (
        "CHECK ((btrim((account_reference)::text, '\t\n\x0b"
        "\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
        "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> '"
        "'::text)):true"
    ),
    "constraint:paper_account_snapshot.paper_account_snapshot_pkey": (
        "PRIMARY KEY (snapshot_id):true"
    ),
    "constraint:paper_broker_acknowledgement.ck_paper_acknowledgement_id_present": (
        "CHECK ((btrim((acknowledgement_id)::text, '\t\n"
        "\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004"
        "\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text"
        ") <> ''::text)):true"
    ),
    "constraint:paper_broker_acknowledgement.ck_paper_acknowledgement_kind": (
        "CHECK (((kind)::text = ANY ((ARRAY['SUBMIT'::"
        "character varying, 'RECONCILE'::character var"
        "ying, 'CANCEL'::character varying])::text[]))"
        "):true"
    ),
    "constraint:paper_broker_acknowledgement.ck_paper_acknowledgement_payload_bounded": (
        "CHECK ((length(sanitized_payload) <= 8192)):true"
    ),
    "constraint:paper_broker_acknowledgement.ck_paper_acknowledgement_payload_digest": (
        "CHECK (((payload_digest)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_broker_acknowledgement.ck_paper_acknowledgement_sequence_positive": (
        "CHECK ((sequence >= 1)):true"
    ),
    "constraint:paper_broker_acknowledgement.fk_paper_acknowledgement_attempt": (
        "FOREIGN KEY (attempt_id) REFERENCES paper_execution_attempt(attempt_id):true"
    ),
    "constraint:paper_broker_acknowledgement.paper_broker_acknowledgement_pkey": (
        "PRIMARY KEY (acknowledgement_id):true"
    ),
    "constraint:paper_broker_acknowledgement.uq_paper_acknowledgement_attempt_sequence": (
        "UNIQUE (attempt_id, sequence):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_bound_to_decision": (
        "CHECK ((decided_at = basis_host_at)):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_broker_interval": (
        "CHECK ((basis_broker_earliest_at <= basis_broker_latest_at)):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_endpoint_host": (
        "CHECK (((broker_endpoint_host)::text = 'paper-api.alpaca.markets'::text)):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_expiry_follows": (
        "CHECK ((decision_expires_at > decided_at)):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_fingerprint": (
        "CHECK (((approved_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_decision_time_basis.ck_paper_decision_time_basis_host_interval": (
        "CHECK ((basis_host_requested_at <= basis_host_at)):true"
    ),
    "constraint:paper_decision_time_basis.paper_decision_time_basis_pkey": (
        "PRIMARY KEY (decision_governance_id):true"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_client_order_id_prefix": (
        "CHECK (((client_order_id)::text ~~ 'm085-%'::text)):true"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_filled_quantity_non_negative": (
        "CHECK (((filled_quantity IS NULL) OR (filled_quantity >= (0)::numeric))):true"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_id_present": (
        "CHECK ((btrim((attempt_id)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f "
        "\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
        "\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_request_fingerprint": (
        "CHECK (((request_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_state": (
        "CHECK (((state)::text = ANY ((ARRAY['DISPATCH"
        "_CLAIMED'::character varying, 'SUBMISSION_IN_"
        "PROGRESS'::character varying, 'PAPER_SUBMITTE"
        "D'::character varying, 'PAPER_ACCEPTED'::char"
        "acter varying, 'PARTIALLY_FILLED'::character "
        "varying, 'FILLED'::character varying, 'CANCEL"
        "_REQUESTED'::character varying, 'CANCELED'::c"
        "haracter varying, 'REJECTED'::character varyi"
        "ng, 'EXPIRED'::character varying, 'SUBMISSION"
        "_UNKNOWN'::character varying])::text[]))):tru"
        "e"
    ),
    "constraint:paper_execution_attempt.ck_paper_attempt_terminal_at_matches_state": (
        "CHECK (((((state)::text = ANY ((ARRAY['FILLED"
        "'::character varying, 'CANCELED'::character v"
        "arying, 'REJECTED'::character varying, 'EXPIR"
        "ED'::character varying])::text[])) AND (termi"
        "nal_at IS NOT NULL)) OR (((state)::text <> AL"
        "L ((ARRAY['FILLED'::character varying, 'CANCE"
        "LED'::character varying, 'REJECTED'::characte"
        "r varying, 'EXPIRED'::character varying])::te"
        "xt[])) AND (terminal_at IS NULL)))):true"
    ),
    "constraint:paper_execution_attempt.fk_paper_attempt_authorization": (
        "FOREIGN KEY (authorization_id) REFERENCES pap"
        "er_execution_authorization(authorization_id):"
        "true"
    ),
    "constraint:paper_execution_attempt.paper_execution_attempt_pkey": (
        "PRIMARY KEY (attempt_id):true"
    ),
    "constraint:paper_execution_attempt.uq_paper_attempt_client_order_id": (
        "UNIQUE (client_order_id):true"
    ),
    "constraint:paper_execution_attempt.uq_paper_attempt_one_per_authorization": (
        "UNIQUE (authorization_id):true"
    ),
    "constraint:paper_execution_attempt.uq_paper_attempt_one_per_intent": (
        "UNIQUE (intent_governance_id):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_actor_present": (
        "CHECK ((btrim((authorized_by)::text, '\t\n\x0b\x0c\r\x1c\x1d"
        "\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
        "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):tr"
        "ue"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_binding_fingerprint": (
        "CHECK (((preview_binding_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_client_order_id_prefix": (
        "CHECK (((client_order_id)::text ~~ 'm085-%'::text)):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_consumed_after_authorized": (
        "CHECK (((consumed_at IS NULL) OR (consumed_at >= authorized_at))):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_consumption_is_paired": (
        "CHECK ((((consumed_at IS NULL) AND (consumed_"
        "by_attempt_id IS NULL)) OR ((consumed_at IS N"
        "OT NULL) AND (consumed_by_attempt_id IS NOT N"
        "ULL)))):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_expiry_follows": (
        "CHECK ((expires_at > authorized_at)):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_id_present": (
        "CHECK ((btrim((authorization_id)::text, '\t\n\x0b\x0c"
        "\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
        "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> '"
        "'::text)):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_policy_fingerprint": (
        "CHECK (((policy_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_authorization_request_fingerprint": (
        "CHECK (((request_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    (
        "constraint:paper_execution_authorization."
        "ck_paper_execution_authorization_basis_interval_paired"
    ): ("CHECK (((basis_host_requested_at IS NULL) = (basis_broker_latest_at IS NULL))):true"),
    (
        "constraint:paper_execution_authorization."
        "ck_paper_execution_authorization_basis_interval_shape"
    ): (
        "CHECK (((basis_host_requested_at IS NULL) OR "
        "((basis_host_at IS NOT NULL) AND (basis_broke"
        "r_earliest_at IS NOT NULL) AND (basis_host_re"
        "quested_at <= basis_host_at) AND (basis_broke"
        "r_earliest_at <= basis_broker_latest_at) AND "
        "(authorized_at <= basis_host_at)))):true"
    ),
    "constraint:paper_execution_authorization.ck_paper_execution_authorization_basis_pair": (
        "CHECK (((basis_host_at IS NULL) = (basis_broker_earliest_at IS NULL))):true"
    ),
    "constraint:paper_execution_authorization.fk_paper_authorization_preview": (
        "FOREIGN KEY (preview_id) REFERENCES paper_submission_preview(preview_id):true"
    ),
    "constraint:paper_execution_authorization.paper_execution_authorization_pkey": (
        "PRIMARY KEY (authorization_id):true"
    ),
    "constraint:paper_execution_authorization.uq_paper_authorization_one_per_preview": (
        "UNIQUE (preview_id):true"
    ),
    "constraint:paper_execution_event.ck_paper_event_id_present": (
        "CHECK ((btrim((event_id)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0"
        "\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
        "\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_execution_event.ck_paper_event_type_present": (
        "CHECK ((btrim((event_type)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f "
        "\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
        "\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_execution_event.fk_paper_event_attempt": (
        "FOREIGN KEY (attempt_id) REFERENCES paper_execution_attempt(attempt_id):true"
    ),
    "constraint:paper_execution_event.paper_execution_event_pkey": ("PRIMARY KEY (event_id):true"),
    "constraint:paper_execution_kill_switch.ck_paper_kill_switch_actor_present": (
        "CHECK ((btrim((changed_by)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f "
        "\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
        "\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_execution_kill_switch.ck_paper_kill_switch_id_present": (
        "CHECK ((btrim((kill_switch_id)::text, '\t\n\x0b\x0c\r\x1c"
        "\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
        "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::tex"
        "t)):true"
    ),
    "constraint:paper_execution_kill_switch.ck_paper_kill_switch_scope": (
        "CHECK (((scope)::text = 'GLOBAL'::text)):true"
    ),
    "constraint:paper_execution_kill_switch.ck_paper_kill_switch_version_positive": (
        "CHECK ((version >= 1)):true"
    ),
    "constraint:paper_execution_kill_switch.paper_execution_kill_switch_pkey": (
        "PRIMARY KEY (kill_switch_id):true"
    ),
    "constraint:paper_execution_kill_switch.uq_paper_kill_switch_scope_version": (
        "UNIQUE (scope, version):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_bound_to_issuance": (
        "CHECK ((intent_created_at = basis_host_at)):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_broker_interval": (
        "CHECK ((basis_broker_earliest_at <= basis_broker_latest_at)):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_endpoint_host": (
        "CHECK (((broker_endpoint_host)::text = 'paper-api.alpaca.markets'::text)):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_expiry_follows": (
        "CHECK ((intent_expires_at > intent_created_at)):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_fingerprint": (
        "CHECK (((approved_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_intent_time_basis.ck_paper_intent_time_basis_host_interval": (
        "CHECK ((basis_host_requested_at <= basis_host_at)):true"
    ),
    "constraint:paper_intent_time_basis.paper_intent_time_basis_pkey": (
        "PRIMARY KEY (intent_governance_id):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_bound_to_evaluation": (
        "CHECK ((proposal_created_at = basis_host_at)):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_broker_interval": (
        "CHECK ((basis_broker_earliest_at <= basis_broker_latest_at)):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_endpoint_host": (
        "CHECK (((broker_endpoint_host)::text = 'paper-api.alpaca.markets'::text)):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_expiry_follows": (
        "CHECK ((proposal_expires_at > proposal_created_at)):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_fingerprint": (
        "CHECK (((content_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_proposal_time_basis.ck_paper_proposal_time_basis_host_interval": (
        "CHECK ((basis_host_requested_at <= basis_host_at)):true"
    ),
    "constraint:paper_proposal_time_basis.paper_proposal_time_basis_pkey": (
        "PRIMARY KEY (proposal_governance_id):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_account_present": (
        "CHECK ((length(btrim((account_reference)::text)) > 0)):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_ack_sequence_positive": (
        "CHECK (((acknowledgement_sequence IS NULL) OR (acknowledgement_sequence >= 1))):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_broker_interval_ordered": (
        "CHECK (((broker_latest_at IS NULL) OR (broker_latest_at >= broker_earliest_at))):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_broker_interval_pairs": (
        "CHECK (((broker_earliest_at IS NULL) = (broker_latest_at IS NULL))):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_completion_pairs": (
        "CHECK (((outcome IS NULL) = (completed_at IS NULL))):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_id_present": (
        "CHECK ((length(btrim((round_id)::text)) > 0)):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_outcome": (
        "CHECK (((outcome IS NULL) OR ((outcome)::text"
        " = ANY ((ARRAY['NOT_FOUND'::character varying"
        ", 'FOUND'::character varying, 'UNUSABLE'::cha"
        "racter varying, 'FAILED'::character varying])"
        "::text[])))):true"
    ),
    "constraint:paper_reconciliation_round.ck_paper_reconciliation_round_sequence_positive": (
        "CHECK ((sequence >= 1)):true"
    ),
    "constraint:paper_reconciliation_round.fk_paper_reconciliation_round_attempt": (
        "FOREIGN KEY (attempt_id) REFERENCES paper_execution_attempt(attempt_id):true"
    ),
    "constraint:paper_reconciliation_round.paper_reconciliation_round_pkey": (
        "PRIMARY KEY (round_id):true"
    ),
    "constraint:paper_reconciliation_round.uq_paper_reconciliation_round_attempt_sequence": (
        "UNIQUE (attempt_id, sequence):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_approved_fingerprint": (
        "CHECK (((approved_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_authorizable_within_cap": (
        "CHECK (((refusals <> '[]'::text) OR ((order_t"
        "ype)::text <> 'LIMIT'::text) OR (limit_price "
        "IS NULL) OR ((limit_price * (quantity)::numer"
        "ic) <= maximum_notional))):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_binding_fingerprint": (
        "CHECK (((binding_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_client_order_id_length": (
        "CHECK (((length((client_order_id)::text) >= 6"
        ") AND (length((client_order_id)::text) <= 64)"
        ")):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_client_order_id_prefix": (
        "CHECK (((client_order_id)::text ~~ 'm085-%'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_entry_window_ordered": (
        "CHECK ((earliest_entry_time < latest_entry_time)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_id_present": (
        "CHECK ((btrim((preview_id)::text, '\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f "
        "\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
        "\u2009\u200a\u2028\u2029\u202f\u205f\u3000'::text) <> ''::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_limit_price_shape": (
        "CHECK (((((order_type)::text = 'LIMIT'::text)"
        " AND (limit_price IS NOT NULL) AND (limit_pri"
        "ce > (0)::numeric)) OR (((order_type)::text <"
        "> 'LIMIT'::text) AND (limit_price IS NULL))))"
        ":true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_long_only": (
        "CHECK (((side)::text = 'BUY'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_no_extended_hours": (
        "CHECK ((extended_hours = false)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_notional_cap_positive": (
        "CHECK ((maximum_notional > (0)::numeric)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_order_type": (
        "CHECK (((order_type)::text = ANY ((ARRAY['MAR"
        "KET'::character varying, 'LIMIT'::character v"
        "arying])::text[]))):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_policy_fingerprint": (
        "CHECK (((policy_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_quantity_positive": (
        "CHECK ((quantity > 0)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_quote_age_positive": (
        "CHECK ((quote_maximum_age_seconds > 0)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_request_fingerprint": (
        "CHECK (((request_fingerprint)::text ~ '^[0-9a-f]{64}$'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_spread_limit_non_negative": (
        "CHECK ((maximum_spread_percent >= (0)::numeric)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_time_in_force": (
        "CHECK (((time_in_force)::text = 'DAY'::text)):true"
    ),
    "constraint:paper_submission_preview.ck_paper_preview_version_positive": (
        "CHECK ((preview_version >= 1)):true"
    ),
    "constraint:paper_submission_preview.fk_paper_preview_account_snapshot": (
        "FOREIGN KEY (account_snapshot_id) REFERENCES paper_account_snapshot(snapshot_id):true"
    ),
    "constraint:paper_submission_preview.paper_submission_preview_pkey": (
        "PRIMARY KEY (preview_id):true"
    ),
    "constraint:paper_submission_preview.uq_paper_preview_intent_version": (
        "UNIQUE (intent_governance_id, preview_version):true"
    ),
    "function:m085_append_only": (
        "bb9547f0ab69d04106281cbd1682ba0312a6262f05f135ecd70e282751701110"
    ),
    "function:paper_execution_attempt_guard_insert": (
        "b2cbb8d91161ca9ac0a03622a588c57b094d7785c6818bf2ac7671c9e5722ddd"
    ),
    "function:paper_execution_attempt_guard_update": (
        "c687f2a09c203105a3386d8715c163b8ac7231bfa14ed8be7f960099a406fdb3"
    ),
    "function:paper_execution_authorization_guard_insert": (
        "26fd2e40deb1c0fb378acc83a46f5e66ec0cd1ea662e76889a61287ff785c4b8"
    ),
    "function:paper_execution_authorization_guard_update": (
        "f1a5071ba16265d00408fd81bb41c738b4ea0dad16d44c01ef42438d44cb73ee"
    ),
    "function:paper_execution_decision_time_basis_guard_insert": (
        "93a8ed47d0004f8a28fe18a1e66e469cccfb60583f1360c58bf969f08d03e070"
    ),
    "function:paper_execution_intent_time_basis_guard_insert": (
        "e9066f7cafe1359e01bd1a415606b71dacf10626935d590d2d5fc2d624a472da"
    ),
    "function:paper_execution_proposal_time_basis_guard_insert": (
        "a03c2d862106e030bcea820862eb1d3829d49cbe40573ccb7c4673cee5a3b835"
    ),
    "function:paper_reconciliation_round_guard_insert": (
        "f145612633cabd93a595e775f9b139e730cccdb9be515626a426e3c8e3ee9552"
    ),
    "function:paper_reconciliation_round_guard_update": (
        "cd20f7efee3de38b10bc546753da80739ce37806f882fb345ff9f892dd123be4"
    ),
    "function:paper_requires_approved_intent": (
        "5136f3173febb30bb88b97b9aa1c8ed0296200ef554feffd63b85730dd1c60e2"
    ),
    "function:paper_submission_preview_guard_policy": (
        "0d8e0ac64c0f2fb4e2a39f18ee495a92b983cdfd0cf88c95b56ae09f8a85807c"
    ),
    "trigger:paper_account_snapshot.paper_account_snapshot_append_only_trigger": (
        "CREATE TRIGGER paper_account_snapshot_append_"
        "only_trigger BEFORE DELETE OR UPDATE ON publi"
        "c.paper_account_snapshot FOR EACH ROW EXECUTE"
        " FUNCTION m085_append_only():O"
    ),
    "trigger:paper_broker_acknowledgement.paper_broker_acknowledgement_append_only_trigger": (
        "CREATE TRIGGER paper_broker_acknowledgement_a"
        "ppend_only_trigger BEFORE DELETE OR UPDATE ON"
        " public.paper_broker_acknowledgement FOR EACH"
        " ROW EXECUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_decision_time_basis.paper_decision_time_basis_append_only_trigger": (
        "CREATE TRIGGER paper_decision_time_basis_appe"
        "nd_only_trigger BEFORE DELETE OR UPDATE ON pu"
        "blic.paper_decision_time_basis FOR EACH ROW E"
        "XECUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_decision_time_basis.paper_decision_time_basis_guard_insert_trigger": (
        "CREATE TRIGGER paper_decision_time_basis_guar"
        "d_insert_trigger BEFORE INSERT ON public.pape"
        "r_decision_time_basis FOR EACH ROW EXECUTE FU"
        "NCTION paper_execution_decision_time_basis_gu"
        "ard_insert():O"
    ),
    "trigger:paper_execution_attempt.paper_execution_attempt_guard_insert_trigger": (
        "CREATE TRIGGER paper_execution_attempt_guard_"
        "insert_trigger BEFORE INSERT ON public.paper_"
        "execution_attempt FOR EACH ROW EXECUTE FUNCTI"
        "ON paper_execution_attempt_guard_insert():O"
    ),
    "trigger:paper_execution_attempt.paper_execution_attempt_guard_update_trigger": (
        "CREATE TRIGGER paper_execution_attempt_guard_"
        "update_trigger BEFORE UPDATE ON public.paper_"
        "execution_attempt FOR EACH ROW EXECUTE FUNCTI"
        "ON paper_execution_attempt_guard_update():O"
    ),
    "trigger:paper_execution_attempt.paper_execution_attempt_refuse_delete_trigger": (
        "CREATE TRIGGER paper_execution_attempt_refuse"
        "_delete_trigger BEFORE DELETE ON public.paper"
        "_execution_attempt FOR EACH ROW EXECUTE FUNCT"
        "ION m085_append_only():O"
    ),
    "trigger:paper_execution_attempt.paper_execution_attempt_requires_intent_trigger": (
        "CREATE TRIGGER paper_execution_attempt_requir"
        "es_intent_trigger BEFORE INSERT ON public.pap"
        "er_execution_attempt FOR EACH ROW EXECUTE FUN"
        "CTION paper_requires_approved_intent():O"
    ),
    "trigger:paper_execution_authorization.paper_execution_authorization_guard_insert_trigger": (
        "CREATE TRIGGER paper_execution_authorization_"
        "guard_insert_trigger AFTER INSERT ON public.p"
        "aper_execution_authorization FOR EACH ROW EXE"
        "CUTE FUNCTION paper_execution_authorization_g"
        "uard_insert():O"
    ),
    "trigger:paper_execution_authorization.paper_execution_authorization_guard_update_trigger": (
        "CREATE TRIGGER paper_execution_authorization_"
        "guard_update_trigger BEFORE UPDATE ON public."
        "paper_execution_authorization FOR EACH ROW EX"
        "ECUTE FUNCTION paper_execution_authorization_"
        "guard_update():O"
    ),
    "trigger:paper_execution_authorization.paper_execution_authorization_refuse_delete_trigger": (
        "CREATE TRIGGER paper_execution_authorization_"
        "refuse_delete_trigger BEFORE DELETE ON public"
        ".paper_execution_authorization FOR EACH ROW E"
        "XECUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_execution_authorization.paper_execution_authorization_requires_intent_trigger": (
        "CREATE TRIGGER paper_execution_authorization_"
        "requires_intent_trigger BEFORE INSERT ON publ"
        "ic.paper_execution_authorization FOR EACH ROW"
        " EXECUTE FUNCTION paper_requires_approved_int"
        "ent():O"
    ),
    "trigger:paper_execution_event.paper_execution_event_append_only_trigger": (
        "CREATE TRIGGER paper_execution_event_append_o"
        "nly_trigger BEFORE DELETE OR UPDATE ON public"
        ".paper_execution_event FOR EACH ROW EXECUTE F"
        "UNCTION m085_append_only():O"
    ),
    "trigger:paper_execution_event.paper_execution_event_requires_intent_trigger": (
        "CREATE TRIGGER paper_execution_event_requires"
        "_intent_trigger BEFORE INSERT ON public.paper"
        "_execution_event FOR EACH ROW EXECUTE FUNCTIO"
        "N paper_requires_approved_intent():O"
    ),
    "trigger:paper_execution_kill_switch.paper_execution_kill_switch_append_only_trigger": (
        "CREATE TRIGGER paper_execution_kill_switch_ap"
        "pend_only_trigger BEFORE DELETE OR UPDATE ON "
        "public.paper_execution_kill_switch FOR EACH R"
        "OW EXECUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_intent_time_basis.paper_intent_time_basis_append_only_trigger": (
        "CREATE TRIGGER paper_intent_time_basis_append"
        "_only_trigger BEFORE DELETE OR UPDATE ON publ"
        "ic.paper_intent_time_basis FOR EACH ROW EXECU"
        "TE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_intent_time_basis.paper_intent_time_basis_guard_insert_trigger": (
        "CREATE TRIGGER paper_intent_time_basis_guard_"
        "insert_trigger BEFORE INSERT ON public.paper_"
        "intent_time_basis FOR EACH ROW EXECUTE FUNCTI"
        "ON paper_execution_intent_time_basis_guard_in"
        "sert():O"
    ),
    "trigger:paper_proposal_time_basis.paper_proposal_time_basis_append_only_trigger": (
        "CREATE TRIGGER paper_proposal_time_basis_appe"
        "nd_only_trigger BEFORE DELETE OR UPDATE ON pu"
        "blic.paper_proposal_time_basis FOR EACH ROW E"
        "XECUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_proposal_time_basis.paper_proposal_time_basis_guard_insert_trigger": (
        "CREATE TRIGGER paper_proposal_time_basis_guar"
        "d_insert_trigger BEFORE INSERT ON public.pape"
        "r_proposal_time_basis FOR EACH ROW EXECUTE FU"
        "NCTION paper_execution_proposal_time_basis_gu"
        "ard_insert():O"
    ),
    "trigger:paper_reconciliation_round.paper_reconciliation_round_append_only_trigger": (
        "CREATE TRIGGER paper_reconciliation_round_app"
        "end_only_trigger BEFORE DELETE ON public.pape"
        "r_reconciliation_round FOR EACH ROW EXECUTE F"
        "UNCTION m085_append_only():O"
    ),
    "trigger:paper_reconciliation_round.paper_reconciliation_round_guard_insert_trigger": (
        "CREATE TRIGGER paper_reconciliation_round_gua"
        "rd_insert_trigger AFTER INSERT ON public.pape"
        "r_reconciliation_round FOR EACH ROW EXECUTE F"
        "UNCTION paper_reconciliation_round_guard_inse"
        "rt():O"
    ),
    "trigger:paper_reconciliation_round.paper_reconciliation_round_guard_update_trigger": (
        "CREATE TRIGGER paper_reconciliation_round_gua"
        "rd_update_trigger BEFORE UPDATE ON public.pap"
        "er_reconciliation_round FOR EACH ROW EXECUTE "
        "FUNCTION paper_reconciliation_round_guard_upd"
        "ate():O"
    ),
    "trigger:paper_submission_preview.paper_submission_preview_append_only_trigger": (
        "CREATE TRIGGER paper_submission_preview_appen"
        "d_only_trigger BEFORE DELETE OR UPDATE ON pub"
        "lic.paper_submission_preview FOR EACH ROW EXE"
        "CUTE FUNCTION m085_append_only():O"
    ),
    "trigger:paper_submission_preview.paper_submission_preview_guard_policy_trigger": (
        "CREATE TRIGGER paper_submission_preview_guard"
        "_policy_trigger AFTER INSERT ON public.paper_"
        "submission_preview FOR EACH ROW EXECUTE FUNCT"
        "ION paper_submission_preview_guard_policy():O"
    ),
    "trigger:paper_submission_preview.paper_submission_preview_requires_intent_trigger": (
        "CREATE TRIGGER paper_submission_preview_requi"
        "res_intent_trigger BEFORE INSERT ON public.pa"
        "per_submission_preview FOR EACH ROW EXECUTE F"
        "UNCTION paper_requires_approved_intent():O"
    ),
}
