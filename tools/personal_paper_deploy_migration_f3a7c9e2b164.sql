-- REVIEWED OFFLINE MIGRATION SQL for Store B (empirical_platform_paper) only.
--
-- Generated verbatim by (and must always match):
--   alembic -c alembic.ini upgrade 83e15e6bfae4:f3a7c9e2b164 --sql
--
-- This is the ONLY sanctioned way to apply f3a7c9e2b164 to a PERSONAL_PAPER-identified
-- database: `alembic upgrade` in ONLINE mode is unconditionally refused for Store B/C by
-- `refuse_unplanned_personal_migration` (see database_safety.py) before it ever connects.
-- `tools/personal_paper_deploy.py` pins this file's SHA-256 and refuses to run if the file
-- on disk does not match -- regenerate with the command above and re-pin deliberately if the
-- migration itself ever changes; never hand-edit this file.
--
-- Purely additive: four new NULLable columns, two new CHECK constraints trivially satisfied
-- by existing (all-NULL) rows, and a CREATE OR REPLACE of the existing trigger function
-- under its unchanged name. No existing row's data is read, rewritten or deleted.
BEGIN;

-- Running upgrade 83e15e6bfae4 -> f3a7c9e2b164

ALTER TABLE approved_plan ADD COLUMN triggered_exit_quote_bid NUMERIC(20, 8);

ALTER TABLE approved_plan ADD COLUMN triggered_exit_quote_ask NUMERIC(20, 8);

ALTER TABLE approved_plan ADD COLUMN triggered_exit_quote_captured_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE approved_plan ADD COLUMN triggered_exit_quote_source VARCHAR(32);

ALTER TABLE approved_plan ADD CONSTRAINT ck_approved_plan_trigger_quote_paired CHECK ((triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_ask IS NULL) AND (triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_captured_at IS NULL) AND (triggered_exit_quote_bid IS NULL) = (triggered_exit_quote_source IS NULL));

ALTER TABLE approved_plan ADD CONSTRAINT ck_approved_plan_trigger_quote_not_mandatory_exit CHECK (triggered_exit_kind IS DISTINCT FROM 'MANDATORY_EXIT' OR triggered_exit_quote_bid IS NULL);

CREATE OR REPLACE FUNCTION public.approved_plan_guard_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.candidate_id IS DISTINCT FROM OLD.candidate_id
        OR NEW.entry_intent_governance_id IS DISTINCT FROM OLD.entry_intent_governance_id
        OR NEW.symbol IS DISTINCT FROM OLD.symbol
        OR NEW.approved_quantity IS DISTINCT FROM OLD.approved_quantity
        OR NEW.stop_price IS DISTINCT FROM OLD.stop_price
        OR NEW.target_price IS DISTINCT FROM OLD.target_price
        OR NEW.mandatory_liquidation_at IS DISTINCT FROM OLD.mandatory_liquidation_at
        OR NEW.owner_approval_id IS DISTINCT FROM OLD.owner_approval_id
        OR NEW.system_identity IS DISTINCT FROM OLD.system_identity
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION
            'approved_plan % identity and terms are immutable; only the one exit-trigger '
            'claim may change', OLD.plan_id;
    END IF;

    IF OLD.triggered_exit_kind IS NOT NULL THEN
        RAISE EXCEPTION
            'approved_plan % already claimed (%); a second claim is refused',
            OLD.plan_id, OLD.triggered_exit_kind;
    END IF;

    IF (NEW.triggered_exit_kind IS NULL) <> (NEW.triggered_exit_at IS NULL) THEN
        RAISE EXCEPTION
            'approved_plan % triggered_exit_kind and triggered_exit_at must be set, or '
            'unset, together', OLD.plan_id;
    END IF;

    -- FORENSIC AUDIT FOLLOW-UP (f3a7c9e2b164): the four quote-evidence columns are
    -- all-or-nothing, and only STOP/TARGET (price-based) claims may carry them --
    -- MANDATORY_EXIT fires on time alone and never consults a quote, mirroring
    -- `evaluate_exit_trigger`'s own branches.
    IF (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_ask IS NULL)
        OR (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_captured_at IS NULL)
        OR (NEW.triggered_exit_quote_bid IS NULL) <> (NEW.triggered_exit_quote_source IS NULL)
    THEN
        RAISE EXCEPTION
            'approved_plan % quote evidence columns must be set, or unset, together',
            OLD.plan_id;
    END IF;

    IF NEW.triggered_exit_kind = 'MANDATORY_EXIT' AND NEW.triggered_exit_quote_bid IS NOT NULL THEN
        RAISE EXCEPTION
            'approved_plan % a MANDATORY_EXIT claim never consults a quote', OLD.plan_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, public;

UPDATE alembic_version SET version_num='f3a7c9e2b164' WHERE alembic_version.version_num = '83e15e6bfae4';

COMMIT;
