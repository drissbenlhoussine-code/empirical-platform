"""Explicit Paper route evidence in a separately selected market-access database.

No change to the reviewed Alpaca Store B/C migration chains or historical rows.
"""

from alembic import op

revision = "ibkr_market_access_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE market_configuration (
 governance_id text NOT NULL, version integer NOT NULL CHECK (version > 0),
 fingerprint text NOT NULL CHECK (length(fingerprint)=64), body jsonb NOT NULL,
 PRIMARY KEY(governance_id,version),
 CHECK (body->>'base_currency'='EUR'),
 CHECK ((body->>'risk_contract_version')::integer=2)
);
CREATE TABLE market_plan (
 plan_id text PRIMARY KEY, fingerprint text NOT NULL UNIQUE CHECK(length(fingerprint)=64),
 body jsonb NOT NULL, configuration_id text NOT NULL, configuration_version integer NOT NULL,
 owner_id text, approved_at timestamptz, trigger_kind text, triggered_at timestamptz,
 closed_at timestamptz, realized_price_pnl numeric,
 FOREIGN KEY(configuration_id,configuration_version) REFERENCES market_configuration,
 CHECK(body->'instrument'->>'broker'='IBKR_PAPER'),
 CHECK(body->'instrument'->>'venue'='XHEL'),
 CHECK(body->'instrument'->>'currency'='EUR'),
 CHECK ((owner_id IS NULL)=(approved_at IS NULL)),
 CHECK ((trigger_kind IS NULL)=(triggered_at IS NULL)),
 CHECK(trigger_kind IN ('STOP','TARGET','MANDATORY_EXIT')),
 CHECK((closed_at IS NULL)=(realized_price_pnl IS NULL))
);
CREATE TABLE market_dispatch (
 plan_id text NOT NULL REFERENCES market_plan, purpose text NOT NULL CHECK(purpose IN
('BUY','SELL_TO_CLOSE')),
 order_id bigint NOT NULL UNIQUE CHECK(order_id>=0), reference text NOT NULL UNIQUE,
 quantity numeric NOT NULL CHECK(quantity>0 AND quantity<=1),
 limit_price numeric NOT NULL CHECK(limit_price>0 AND limit_price::text NOT IN
('NaN','Infinity','-Infinity')),
 state text NOT NULL CHECK(state IN
('CLAIMED','UNKNOWN','WORKING','PARTIAL','FILLED','CANCELED','REJECTED')),
 created_at timestamptz NOT NULL, PRIMARY KEY(plan_id,purpose)
);
CREATE TABLE market_observation (
 sequence bigserial PRIMARY KEY, plan_id text NOT NULL, purpose text NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT now(), body jsonb,
 FOREIGN KEY(plan_id,purpose) REFERENCES market_dispatch
);
CREATE TABLE market_cancel_claim (
 plan_id text NOT NULL, purpose text NOT NULL, claimed_at timestamptz NOT NULL,
 PRIMARY KEY(plan_id,purpose), FOREIGN KEY(plan_id,purpose) REFERENCES market_dispatch
);
CREATE TABLE market_safety (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), engaged
boolean NOT NULL);
INSERT INTO market_safety(singleton,engaged) VALUES (true,true);
CREATE TABLE market_zero_verification (
 plan_id text PRIMARY KEY REFERENCES market_plan,
 observed_at timestamptz NOT NULL, account_fingerprint text NOT NULL,
 instrument_fingerprint text NOT NULL,
 exit_permanent_id bigint NOT NULL CHECK(exit_permanent_id>0),
 position_count integer NOT NULL CHECK(position_count=0)
);
CREATE FUNCTION market_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'market evidence cannot be deleted'; END IF;
 IF TG_TABLE_NAME IN ('market_configuration','market_observation','market_cancel_claim',
 'market_zero_verification') THEN
  RAISE EXCEPTION 'market evidence is immutable';
 ELSIF TG_TABLE_NAME='market_plan' THEN
  IF NEW.closed_at IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM market_zero_verification WHERE plan_id=NEW.plan_id) THEN
   RAISE EXCEPTION 'position zero evidence required'; END IF;
  IF NEW.body IS DISTINCT FROM OLD.body OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
   OR NEW.plan_id IS DISTINCT FROM OLD.plan_id OR NEW.configuration_id IS DISTINCT FROM
OLD.configuration_id
   OR NEW.configuration_version IS DISTINCT FROM OLD.configuration_version THEN
   RAISE EXCEPTION 'approved terms immutable'; END IF;
  IF OLD.owner_id IS NOT NULL AND (NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.approved_at
IS DISTINCT FROM OLD.approved_at) THEN
   RAISE EXCEPTION 'approval immutable'; END IF;
  IF OLD.trigger_kind IS NOT NULL AND (NEW.trigger_kind IS DISTINCT FROM OLD.trigger_kind OR
NEW.triggered_at IS DISTINCT FROM OLD.triggered_at) THEN
   RAISE EXCEPTION 'one trigger only'; END IF;
  IF OLD.closed_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'closed plan
immutable'; END IF;
 ELSIF TG_TABLE_NAME='market_dispatch' THEN
  IF (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') THEN RAISE EXCEPTION
'dispatch identity immutable'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_market_zero BEFORE UPDATE OR DELETE ON market_zero_verification
FOR EACH ROW EXECUTE FUNCTION market_immutable_guard();
CREATE TRIGGER immutable_market_configuration BEFORE UPDATE OR DELETE ON market_configuration
FOR EACH ROW EXECUTE FUNCTION market_immutable_guard();
CREATE TRIGGER immutable_market_plan BEFORE UPDATE OR DELETE ON market_plan FOR EACH ROW EXECUTE
FUNCTION market_immutable_guard();
CREATE TRIGGER immutable_market_dispatch BEFORE UPDATE OR DELETE ON market_dispatch FOR EACH ROW
EXECUTE FUNCTION market_immutable_guard();
CREATE TRIGGER immutable_market_observation BEFORE UPDATE OR DELETE ON market_observation FOR
EACH ROW EXECUTE FUNCTION market_immutable_guard();
CREATE TRIGGER immutable_market_cancel_claim BEFORE UPDATE OR DELETE ON market_cancel_claim FOR
EACH ROW EXECUTE FUNCTION market_immutable_guard();
""")


def downgrade() -> None:
    raise RuntimeError("market-access evidence cannot be destructively downgraded")
