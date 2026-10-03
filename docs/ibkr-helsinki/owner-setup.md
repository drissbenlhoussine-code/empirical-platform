# IBKR Paper Owner setup gate

Status: IBKR_OWNER_SETUP_REQUIRED. Owner update on 2026-10-03: the Individual
account application was successfully submitted; residential-address verification
is RECEIVED — BEING PROCESSED; account approval is pending. TWS / IB Gateway Paper
login is not available yet. This is Owner-reported status, not API verification.
No real IBKR connection, entitlement, fill, or round trip has been verified.
Test doubles and offline SDK serialization are engineering evidence only.
No broker writes were made during engineering.

**No account funding is requested to accelerate engineering.** All engineering
checks below run without an authenticated IBKR session. Do not poll or wait idle
for account approval. Resume real setup when the Owner confirms Paper login is
available; approval alone is not proof of Paper access or data entitlements.

## Minimal interactive steps

1. Once IBKR approval and Paper access are available, install [official TWS or IB Gateway](https://www.interactivebrokers.com/docs/tws-api/doc/download-tws-or-ib-gateway/download-tws-or-ib-gateway).
   Log in yourself to **Paper Trading**. Complete any required account activation
   and authentication in IBKR; never paste credentials or tokens into chat.
2. In API settings enable socket clients, restrict access to localhost, and leave
   **Read-Only API enabled**. Use Paper port 7497 for TWS or 4002 for Gateway.
   Reserve a dedicated nonzero client ID (71 is the probe default). Do not use
   Live ports, a Live login, or a shared client ID.
3. Verify the Paper account identifier is DU followed by digits, the account is
   ready, and explicit EUR **Paper simulated cash** is available without borrowing.
   This does not request a deposit into the real account. Verify Finland
   equity permissions and the live Nasdaq Helsinki data entitlement needed by
   the API. Delayed or missing quotes cannot pass acceptance.
4. Report only that Paper login and read-only API setup are ready, the chosen
   port/client ID, and the account identifier through the local configuration
   path. No password/API secret is required by this socket adapter.

Reference: [IBKR TWS API documentation](https://www.interactivebrokers.com/docs/tws-api/doc/introduction)
and [official SDK download](https://interactivebrokers.github.io/).

## Isolated Python setup and read-only probe

Use a new Python 3.13 environment in this branch's worktree, not the existing
Alpaca release environment. Install the core with persistence dependencies and
`integrations/ibkr` (which pins patched protobuf 5.29.6). Load the hash-verified
official Python client source through the isolated environment's PYTHONPATH.
Do not substitute an unrelated PyPI package named ibapi.

From the isolated worktree/environment:

```powershell
python -m pip install -e '.[persistence]'
python -m pip install -e ./integrations/ibkr
# Verify the downloaded SDK archive, then extract it into a dedicated SDK directory.
python tools/verify_ibkr_sdk_archive.py 'C:\path\to\twsapi_macunix.1050.02.zip'
# Set the actual extracted path for this isolated shell; do not run SDK setup.py.
$env:PYTHONPATH='C:\path\to\IBJts\source\pythonclient'
python -m pip check
python -m empirical_platform.entrypoints.ibkr_owner_setup --account <YOUR_DU_ACCOUNT> --client-id 71 --port 7497 --symbol NOKIA
```

The probe constructs neither a database journal nor a write-enabled adapter.
It checks the managed-account handshake, contract identity, EUR account evidence,
positions and orders; when the reviewed calendar is open it also checks a fresh
live quote. It explicitly reports that database guards have NOT been checked.
Any unresolved contract, foreign position, conflicting order, missing readiness
field, unsupported API response or missing entitlement fails closed. A successful
probe alone is not approval to deploy, enable writes, or submit an order.

Engineering inspected official SDK 10.50.2 from
`https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip`.
Archive SHA256:
`673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3`.
The repeatable `tests/ibkr_offline/verify_sdk.py` check passes the actual adapter's
bounded BUY and whole/partial-position SELL_TO_CLOSE to real EClient, captures each
protobuf frame in memory, decodes and
asserts its contract/account/quantity/limit/DAY/extended-hours/orderRef fields.
Both socket construction and connection helpers are blocked; read-only refusal
and final-gate refusal are checked before any frame is encoded. The dedicated CI job verifies the archive
digest before extraction and executes this check without broker credentials.
Callback and lifecycle tests use explicit fakes. The SDK is
not vendored, and its successful serialization does not establish broker acceptance.

**Dependency correction:** upstream SDK 10.50.2 and inspected 10.51.1 setup.py pin
protobuf 5.29.5, affected by [PYSEC-2026-1805](https://osv.dev/vulnerability/PYSEC-2026-1805).
Do not invoke their installer, which would downgrade the reviewed runtime. Use the
unchanged verified 10.50.2 source with protobuf 5.29.6 as above. This is an explicit
application runtime override, not an upstream SDK fix. The SDK's generated Python
code is compatible with the later patch runtime under the
[Protobuf compatibility policy](https://protobuf.dev/support/cross-version-runtime-guarantee/),
and the real SDK encoding tests pass with that runtime. Session startup checks the
actually imported protobuf version before SDK client construction or sockets.
The optional-integration CI job runs pip check and dependency audit; no vulnerability
suppression is used. Local audit of 5.29.6 found no known vulnerabilities.

## Deployment boundary after read-only connectivity

The Alpaca B/C schemas, release branch, existing SIM and Paper servers are not
modified by this track. The new journal has a separate migration chain,
`ibkr_market_access_01`, and requires an exact database identity on every transaction.
Online engineering migrations accept only an explicitly supplied TEST connection;
they never resolve a default Store B URL. No personal market journal was created.

Before activation, prepare and review a dedicated protected market database,
its identity `PERSONAL_PAPER:MARKET_ACCESS:<owner-selected-id>`, backup/retention
and explicit connection configuration. Do not apply this chain to Alpaca B/C.
Review offline SQL with `alembic -c alembic-market-access.ini upgrade head --sql`;
that command does not initialize a real database. Personal initialization needs
a separately reviewed deployment procedure, including identity and backup checks.

Persist the EUR Owner configuration with the existing
`SaveOperatorTradingConfigurationHandler` and `MarketConfigurationRepository`,
using the current v1 risk contract. The service requires XHEL/EUR, at most one
share, EUR 500 notional, EUR 5 planned loss and one simultaneous position.
Actual risk may be lower. Supply real instrument-specific cost evidence to the
canonical proposal engine; do not fabricate commissions, liquidity or prices.

`market_access_runtime` is read-only by default and takes explicit store/account/
configuration arguments. Its service can be injected into the existing single
`PositionPlanManager` via `market_exit_cycles`; its `reviews` can be injected into
the existing Paper console. These are opt-in composition hooks, not an activated
personal deployment or a second permanent console. `/markets` is a read-only setup
panel; `/markets/review` and `/markets/history` require the injected journal review
service. The setup panel does not pretend to be connected live health.

Only after protected persistence and runtime guards are verified may a fresh plan
be generated during the Helsinki continuous session. Show the exact broker,
account reference, conid, venue, EUR, quantity, bid/ask timestamps, ceiling, stop,
target, planned/max loss, gain, R:R, mandatory exit, expiry and fingerprints.
Then stop for explicit Owner approval of that full plan and its automatic exits.
Any expired quote/approval or changed term requires a new plan and approval.
Read-Only API must remain enabled throughout setup; disabling it and enabling the
runtime's approved dispatch capability belongs to a later supervised acceptance.

## Operational limits

- The reviewed exchange calendar covers **2026 only**, including Helsinki holidays
  and DST. Unsupported years fail closed. Broker liquid hours must also permit
  entry. Mandatory exit precedes the 18:25 closing-auction boundary; no overnight
  intention is a policy, not a promise that an unfilled limit will execute.
- Durable claims guarantee at-most-once platform dispatch, not guaranteed fills.
  Ambiguous responses become UNKNOWN and are reconciled, never blindly resent.
  Unresolved state blocks another entry. A rejected/unfilled close requires
  operator reconciliation; it cannot be silently replaced under old approval.
- A partial entry must become terminal before closing its exact attributable
  filled quantity. CLOSED requires confirmed full exit and a fresh subsequent
  position-zero snapshot of the same account, persisted as evidence.
- History reports **EUR price P&L before fees**. Net P&L is not claimed without
  broker commission evidence. A stop price bounds planned risk, not realized loss
  during gaps, outages or unavailable liquidity.
- The real twelve-part acceptance remains unproven until Owner setup and the
  separately approved Paper round trip. Engineering tests are not substitutes.

Calendar source: [Nasdaq European trading hours and holidays](https://www.nasdaq.com/european-market-activity/trading-hours).

Proof separation and the prepared deployment/acceptance sequence are recorded in
[`offline-closure.md`](offline-closure.md).
