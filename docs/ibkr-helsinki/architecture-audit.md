# IBKR Paper / Nasdaq Helsinki architecture audit (before implementation)

Base: reviewed release commit 81f1432ec50b268fbf3c84889e1b67c78da66986.
Dedicated branch feature/ibkr-helsinki-paper; no deployment or migration of Alpaca stores.

| Surface | Classification | Evidence / required boundary |
|---|---|---|
| Exact loss / quantity | BROKER_NEUTRAL | decision_candidate/entry_risk_contract.py: EntryRiskContract, planned_loss; reuse unchanged, add explicit surrounding currency identity |
| Approved stop/target/mandatory trigger | BROKER_NEUTRAL | decision_candidate/approved_plan.py: ApprovedPlan, evaluate_exit_trigger, atomic claim semantics; retain |
| Account / market input domain | NEEDS_ABSTRACTION | product_market_inputs.py currency-aware account but ticker-only quote, positions and open orders; broker contract binding is missing |
| M084 configuration / sizing | BROKER_NEUTRAL | operator_trading_configuration.py carries base currency; trade_proposal.py min-cap sizing and independent gates; preserve frozen history |
| Execution account snapshot | US_SPECIFIC | paper_execution.py PaperAccountSnapshot refuses currencies other than USD |
| Broker / market-data ports | ALPACA_SPECIFIC | paper_execution_repositories.py and position_exit_repositories.py protocols use HTTP statuses, Alpaca payload dictionaries and ticker strings |
| Endpoint / account health | ALPACA_SPECIFIC | _paper_composition.py pins paper-api.alpaca.markets; paper_operator_console.py health assumes same host |
| Instrument / order identity | NEEDS_ABSTRACTION | trade_approval.py and paper_execution.py bind symbol and client_order_id; no broker/conid/primary venue/currency identity |
| Calendar / session | ALPACA_SPECIFIC | Alpaca fetch_clock gates US session; market venue must choose authoritative schedule, never host weekday alone |
| Quote transport | ALPACA_SPECIFIC | alpaca_paper.py maps IEX/SIP quotes and us_equity; IBKR needs source timestamps, live-data type and resolved contract |
| Plan Manager | NEEDS_ABSTRACTION | position_plan_manager.py owns neutral trigger/claim logic but constructs Alpaca-shaped position_exit handlers; share manager, separate execution lifecycle boundary |
| Reconciliation | ALPACA_SPECIFIC | paper_execution.py and position_exit.py HTTP 403/422 and Alpaca status tables; IBKR callback/orderId/permId/execId cannot be relabeled as HTTP truth |
| History / P&L | NEEDS_ABSTRACTION | operator_console.py symbol-centric histories lack venue/currency route; scope by immutable broker+account+contract identity |
| UI | ALPACA_SPECIFIC | _operator_console_html.py labels all non-simulation traffic Alpaca; one console needs explicit market/broker/currency labels |
| Persistence | NEEDS_ABSTRACTION | existing B/C records and guards explicitly preserve M084/M085/M089 evidence; additive route-bound storage must not reinterpret those rows |
| Database protection | BROKER_NEUTRAL | database_safety.py explicit identity and TEST isolation; retain, never point tests at personal port 55433 |

## Integration decision

Use official TWS API Python SDK, connecting only to loopback TWS Paper / IB Gateway
Paper with an explicitly configured Paper account. Port alone is not account proof.
Bind managed-account handshake, broker account, client ID, full contract and currency
before accepting data or any approved dispatch. No Client Portal scraping or automatic
login. Start Owner setup in read-only API mode. Missing SDK/login/subscriptions are
setup failures, never fake connectivity or delayed data labeled live.

Official sources checked 2026-10-03 (Europe/Helsinki):
- https://www.interactivebrokers.com/docs/tws-api/doc/introduction
- https://www.interactivebrokers.com/docs/tws-api/doc/download-the-tws-api/install-the-tws-api-on-windows
- https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/order-id
- https://www.interactivebrokers.com/docs/tws-api/doc/contracts-financial-instruments/the-contract-object
- https://www.nasdaq.com/european-market-activity/trading-hours

Helsinki main-market equities use Europe/Helsinki and EUR. Published equity hours
are 10:00–18:30 local, with the last five minutes an auction rather than continuous
matching. Acceptance must leave the continuous market before that interval. Load
published year-specific holidays, reject unsupported years and reconcile contract
liquid hours with venue calendar. Do not copy Stockholm half-days into Helsinki.

## Delivery boundaries

Risk and full-plan trigger arithmetic remain shared. New approvals bind routing
identity in addition to immutable price/quantity/risk/expiry terms. Existing records
remain explicitly historical Alpaca evidence; no backfill to a generic broker.
Broker writes during engineering are forbidden. Real acceptance requires connected
Paper account, entitled live data, open session and separate exact-plan Owner approval.

## Subsequent implementation boundary decision

The frozen M084 architecture assertions forbid order SDK imports anywhere in the
core `src` tree. Those assertions and historical evidence remain unchanged.
The official SDK adapter is therefore a separately packaged optional integration
under `integrations/ibkr/src/empirical_ibkr`. Core domain/usecases depend on typed
market-access ports; explicit opt-in composition loads the integration. The new
`check_ibkr_architecture` gate restricts SDK imports to its session/adapter modules
and forbids that package from owning usecases or persistence. No allowlist was
added to the frozen core checker.

Alpaca-specific models were retained for truthful historical and runtime semantics.
New route-bound models surround the unchanged canonical risk/proposal and exit
trigger logic. The existing Plan Manager accepts an optional exit-cycle port;
there is no second manager thread. The new journal is a separate additive chain,
not a reinterpretation or migration of Store B/C. Read-only review/history routes
extend the existing console through explicit dependency injection.
