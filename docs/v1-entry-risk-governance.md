# V1 entry risk contract, version 2

Current v1 entries require explicit governed `maximum_position_quantity_shares`
(positive whole integer) and `maximum_planned_loss_per_trade` (positive finite
Decimal, serialized as a decimal string). The canonical save/validate/show
configuration commands remain the only configuration path. Specify
`risk_contract_version: 2`, an explicit configuration governance ID/version and
all existing mandatory policy fields. There are no new implicit defaults.

The original independent capital, cash reserve, daily loss, daily order, position,
liquidity, session and kill-switch gates remain in force. Sizing takes the minimum
of the existing quantity and configured share cap, rounded down to instrument
lots. A proposed entry that exceeds the independent loss cap is refused; it is
never silently repriced or assigned a different stop. Version 2 requires LIMIT.

Exact planned loss is `(approved entry ceiling - approved stop) * quantity`.
It is derived once from the deterministic proposal terms and persisted alongside
those terms and the limits. It is planned price risk, not a guarantee of realized
loss: stop slippage, gaps and costs can increase realized loss. No strategy or
profitability claim is made by execution acceptance.

The proposal fingerprint binds stop, target, quantity, ceiling, times and the
risk snapshot. The decision approves that fingerprint; the intent, submission
preview and execution authorization carry the same snapshot. The preview binding
and execution-policy fingerprints also bind the risk contract. The Owner card
and confirmation show quantity, ceiling, stop, target, evaluated planned loss and
both configured limits before approval. Changed terms require a new approval.

Immediately before HTTP send, the existing transport callback reads governed
policy again, compares it with approved evidence, and recomputes exact loss from
the immutable stop/ceiling/quantity. Changed caps, changed terms, missing evidence
or excess loss/quantity refuse before a broker write. No later stop lookup occurs.

## Additive database transition

Main Store B migration `c6e2a4f8b901` follows reviewed `b9f2c4d6a8e1`.
Store C remains `f083b6c29d17`. Nullable JSONB evidence is added to configuration,
proposal, intent, preview and authorization. Historical rows are not rewritten or
backfilled. Immutable triggers require v2 for new rows, enforce configured limits
and exact arithmetic, and compare evidence across the approved chain. No drop,
truncate, reset or destructive downgrade is provided.

Historical M084 v1 records retain their original values and proposal fingerprints.
They remain readable under historical schemas and as historical rows after the
upgrade. Missing limits never mean unlimited risk. On the current schema, the
runtime refuses legacy configurations for preview/send, and database insert
triggers independently refuse legacy new entries. Historical suites use their
historical heads; separate full-head tests prove the new boundary.

Startup requires the exact reviewed head and unchanged M085 physical contract,
plus new risk columns, enabled triggers and the exact risk-trigger implementation.
A stamp alone, removed column, disabled trigger or replaced function is refused.
See `external-review/RELEASE-V1/risk-governance/README.md` for formal M084 operational
supersession; original evidence is preserved separately.

## Backup and later deployment

This engineering change DOES NOT migrate the real PERSONAL_PAPER stores. They
remain at the previously initialized heads. Do not start the new runtime against
those old stores or relabel their external manifest to make a guard pass.

After separate Owner authorization, stop the relevant runtime, verify identities,
create and verify a timestamped B/C dump pair, then apply the reviewed additive
B migration to the explicit B target. Recheck B head, M085/v2 physical contracts,
C unchanged head, both identities and durable state. Only then record the new B
head in the independent safety manifest and take/verify a new baseline dump pair.
Keep the old pair and its original head metadata. Retention and scheduled backups
must never relabel an old dump as the new schema. Rehearse any restore in isolated
TEST databases using the procedure in `v1-database-loss-closure.md`; a pre-upgrade
backup restores the old head and must pass an explicitly reviewed forward upgrade
before the new runtime can use it. Never automatically downgrade or restore.

Owner configuration, plan generation and broker actions remain separate gates.
No real BUY, SELL, CANCEL or LIVE write is part of implementation or tests.
