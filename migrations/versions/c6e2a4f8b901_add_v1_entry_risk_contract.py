"""V1 governed entry-risk version 2. Additive; legacy NULL evidence is never backfilled.

Revision ID: c6e2a4f8b901
Revises: b9f2c4d6a8e1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c6e2a4f8b901"
down_revision: str | None = "b9f2c4d6a8e1"
branch_labels = None
depends_on = None

TABLES = (
    "operator_trading_configuration",
    "trade_proposal",
    "approved_order_intent",
    "paper_submission_preview",
    "paper_execution_authorization",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("risk_contract", postgresql.JSONB(), nullable=True))
    op.execute("""
CREATE FUNCTION public.v1_entry_risk_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public AS $$
DECLARE r jsonb; cfg jsonb; prior jsonb; entry numeric; stop numeric; qty numeric; cap
numeric; loss numeric;
BEGIN
 IF TG_OP = 'UPDATE' THEN
   IF NEW.risk_contract IS DISTINCT FROM OLD.risk_contract THEN
     RAISE EXCEPTION 'immutable approved risk contract cannot change';
   END IF;
   RETURN NEW;
 END IF;
 r := NEW.risk_contract;
 IF r IS NULL OR r->>'version' IS DISTINCT FROM '2' THEN
   RAISE EXCEPTION 'current v1 inserts require explicit risk contract version 2';
 END IF;
 IF TG_TABLE_NAME = 'operator_trading_configuration' THEN
   IF jsonb_typeof(r->'maximum_position_quantity_shares') IS DISTINCT FROM 'number'
      OR jsonb_typeof(r->'maximum_planned_loss_per_trade') IS DISTINCT FROM 'string' THEN
     RAISE EXCEPTION 'invalid risk limit types';
   END IF;
   qty := (r->>'maximum_position_quantity_shares')::numeric;
   cap := (r->>'maximum_planned_loss_per_trade')::numeric;
   IF qty IS NULL OR qty <= 0 OR qty <> trunc(qty) OR qty::text IN ('NaN','Infinity','-Infinity')
      OR cap IS NULL OR cap <= 0 OR cap::text IN ('NaN','Infinity','-Infinity') THEN
     RAISE EXCEPTION 'risk limits must be positive finite whole shares and dollars';
   END IF;
   RETURN NEW;
 END IF;
 SELECT risk_contract INTO cfg FROM public.operator_trading_configuration
 WHERE configuration_governance_id=NEW.configuration_governance_id
 AND configuration_version=NEW.configuration_version;
 IF cfg IS NULL OR cfg->>'version' IS DISTINCT FROM '2' THEN
   RAISE EXCEPTION 'legacy configuration cannot authorize current v1 entry';
 END IF;
 IF TG_TABLE_NAME = 'paper_submission_preview' THEN
   IF r->'maximum_position_quantity_shares' IS DISTINCT FROM
cfg->'maximum_position_quantity_shares'
      OR (r->>'maximum_planned_loss_per_trade')::numeric IS DISTINCT FROM
(cfg->>'maximum_planned_loss_per_trade')::numeric THEN
     RAISE EXCEPTION 'preview policy differs from configuration';
   END IF;
   r := r->'entry';
 END IF;
 IF r IS NULL OR r->>'version' IS DISTINCT FROM '2'
    OR r->'maximum_position_quantity_shares' IS DISTINCT FROM
cfg->'maximum_position_quantity_shares'
    OR (r->>'maximum_planned_loss_per_trade')::numeric IS DISTINCT FROM
(cfg->>'maximum_planned_loss_per_trade')::numeric THEN
   RAISE EXCEPTION 'missing or changed approved risk evidence';
 END IF;
 entry := (r->>'entry_ceiling')::numeric; stop := (r->>'stop_price')::numeric;
 qty := (r->>'quantity')::numeric; cap := (cfg->>'maximum_planned_loss_per_trade')::numeric;
 loss := (r->>'planned_loss')::numeric;
 IF entry IS NULL OR stop IS NULL OR qty IS NULL OR loss IS NULL
    OR entry::text IN ('NaN','Infinity','-Infinity') OR stop::text IN
('NaN','Infinity','-Infinity')
    OR qty::text IN ('NaN','Infinity','-Infinity') OR loss::text IN ('NaN','Infinity','-Infinity')
    OR stop <= 0 OR stop >= entry OR qty <= 0 OR qty <> trunc(qty)
    OR qty > (cfg->>'maximum_position_quantity_shares')::numeric
    OR loss <> (entry-stop)*qty OR loss < 0 OR loss > cap
    OR NEW.quantity::numeric <> qty OR NEW.limit_price IS DISTINCT FROM entry
    OR NEW.order_type <> 'LIMIT' THEN
   RAISE EXCEPTION 'approved entry risk invariant failed';
 END IF;
 IF TG_TABLE_NAME = 'trade_proposal' THEN
   IF NEW.stop_loss_price IS DISTINCT FROM stop THEN RAISE EXCEPTION 'proposal stop changed';
END IF;
 ELSIF TG_TABLE_NAME = 'approved_order_intent' THEN
   SELECT risk_contract INTO prior FROM public.trade_proposal WHERE
proposal_governance_id=NEW.proposal_governance_id;
   IF r IS DISTINCT FROM prior THEN RAISE EXCEPTION 'intent risk differs from approved
proposal'; END IF;
 ELSIF TG_TABLE_NAME = 'paper_submission_preview' THEN
   SELECT risk_contract INTO prior FROM public.approved_order_intent WHERE
intent_governance_id=NEW.intent_governance_id;
   IF r IS DISTINCT FROM prior THEN RAISE EXCEPTION 'preview risk differs from approved
intent'; END IF;
 ELSIF TG_TABLE_NAME = 'paper_execution_authorization' THEN
   SELECT risk_contract->'entry' INTO prior FROM public.paper_submission_preview WHERE
preview_id=NEW.preview_id;
   IF r IS DISTINCT FROM prior THEN RAISE EXCEPTION 'authorization risk differs from preview';
END IF;
 END IF;
 RETURN NEW;
END $$;
""")
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.v1_entry_risk_guard()"
        )


def downgrade() -> None:
    raise RuntimeError("risk evidence downgrade is prohibited; use a reviewed forward migration")
