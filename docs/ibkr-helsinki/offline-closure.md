# Offline closure and external acceptance boundary

Owner status, 2026-10-03: Individual application submitted, residential-address
verification RECEIVED — BEING PROCESSED, account approval pending. Paper login is
unavailable. This record is not an IBKR API observation. No funding is requested,
no account-approval polling is scheduled, and no broker writes are authorized.

## PROVEN_OFFLINE

| Requirement | Scope of proof |
|---|---|
| Explicit broker/instrument/account/EUR identity | Domain, immutable serialization and adversarial route-mismatch tests |
| XHEL calendar | Reviewed 2026 holidays, DST, auction exclusion and unsupported-year refusal; intersection with supplied broker liquid hours |
| Market-data validation | Synthetic stale, missing, crossed and wrong-route evidence refused; no synthetic quote claimed live |
| Governed proposal and risk | Existing canonical configuration/proposal/risk logic, whole-share cap, EUR notional/loss and independent gates |
| Owner approval | Exact fingerprint and immutable terms, original quote expiry, changed/expired terms refused |
| Official SDK compatibility | Hash-pinned unmodified 10.50.2 source with patched protobuf 5.29.6, actual adapter to real EClient to decoded protobuf; socket creation forbidden; exact BUY and whole/partial close fields, read-only default and final-gate refusal verified |
| Optional dependency security | Upstream vulnerable protobuf pin identified; reviewed patched runtime pinned and audited; missing/old/unreviewed runtime refused before any socket; no audit suppression |
| Dispatch/recovery | Real PostgreSQL atomic claims, duplicate prevention, UNKNOWN/restart and collision checks; callback doubles for execution observations |
| Partial fill and close | Terminal-entry reconciliation, exact attributable quantity, shared Plan Manager exit cycle, no-short refusal |
| Position zero | Durable zero snapshot required after exit fill before CLOSED; evidence survives restore |
| Backup and restore | Real pg_dump custom archive, pg_restore list validation, restore into a distinct independently marked TEST database; all journal rows compared including approval, UNKNOWN, zero and configuration |
| One console | Existing console's optional read-only review/history routes label broker, venue and EUR; shared manager hook tested |
| Alpaca preservation | Regression suites and unchanged release head/PR #26; no Alpaca database or running-console changes |

These proofs establish implementation behavior for the tested inputs. They do
not establish network availability, exchange permissions, order acceptance,
execution quality, guaranteed fills or net P&L. Price P&L remains before fees.

Repeatable entrypoints:

- Existing default suite and `tests/unit/test_ibkr_*.py` cover the pure contracts,
  callback seam, read-only setup failures, review routes and shared manager.
- `tests/integration/test_ibkr_market_journal.py` requires explicit TEST source;
  its restore rehearsal additionally requires `EMPIRICAL_IBKR_RESTORE_TEST_URL`.
  Destructive setup invokes `require_test_connection` before SQL; personal targets
  and ambiguous identities are refused. Source and restore targets must differ.
- `tests/ibkr_offline/verify_sdk.py` runs explicitly with the reviewed SDK source
  and patched protobuf runtime (see owner-setup.md; do not use upstream setup.py).
  It is intentionally outside default test filename discovery so the frozen
  core installation does not acquire a mandatory order SDK dependency.
- `.github/workflows/ibkr-helsinki.yml` runs both real-SDK offline verification and
  the full PostgreSQL regression in fresh isolated environments. Archive mismatch
  aborts before extraction; a missing SDK cannot silently skip the dedicated job.

## Prepared deployment sequence — not executed

No personal IBKR journal/configuration has been created. Preparation does not
invent an account ID, contract ID, commission estimate or market quote.

1. When Paper login exists, run the read-only connectivity probe from an isolated
   environment. Keep API Read-Only enabled. Obtain the actual DU account and a
   dedicated client ID; reconcile instrument identity and live-data availability.
2. Prepare the exact dedicated market-store endpoint and database identity.
   Never reuse Alpaca Store B/C or port 55433 for test tooling. Review the separate
   `ibkr_market_access_01` offline SQL and the intended personal identity before
   initialization. The engineering Alembic entrypoint deliberately accepts only
   an explicit TEST connection; do not bypass that guard for personal deployment.
3. For personal initialization, use a separately reviewed, bounded procedure that
   verifies the selected database is empty, records its explicit identity, applies
   only the reviewed additive chain and verifies the exact head. Do not DROP,
   TRUNCATE or reinterpret Alpaca history. This procedure needs exact Owner-selected
   endpoint/identity inputs; placeholders are not executable authorization.
4. Persist one canonical EUR configuration through
   `SaveOperatorTradingConfigurationHandler` and `MarketConfigurationRepository`.
   Record ID/version/fingerprint/effective time and exact bounds. No fixture config
   or synthetic acceptance history may be copied into the personal store.
5. Take a custom-format baseline pg_dump. Verify nonzero size, readable archive
   listing, SHA256, schema head, database marker, configuration fingerprint and
   table-state counts. Configure a dedicated protected backup location/retention
   before activation. The TEST restore rehearsal proves journal content recovery;
   it does not claim a deployed personal backup schedule.
6. Compose `market_access_runtime` with dispatch disabled and explicit inputs;
   inject its review service into the existing console and its exit cycle into
   the one existing Plan Manager. Verify its guarded store and read-only health.
   These hooks are available; the running Alpaca deployment was not changed.
7. During an open verified Helsinki session, obtain real quote/liquidity/cost
   evidence and generate one canonical governed plan. Stop at Owner approval.
   Only a later explicitly authorized acceptance may enable write capability.

Restore procedure: stop the affected IBKR runtime; preserve the damaged state
and incident evidence; validate backup digest and metadata; first restore into a
separate protected target; verify head, identity and all journal fingerprints.
Reconcile every nonterminal/UNKNOWN order against the same real Paper account
before enabling entry. Missing broker history is UNKNOWN, never absence proof.
Restoring a backup never cancels broker orders, repeats a dispatch, changes an
approval, or authorizes a new entry. Personal restore requires explicit approval;
this work performs only disposable TEST restore.

## REQUIRES_REAL_IBKR_PAPER_ACCEPTANCE

| Unproven item | Evidence needed after external access exists |
|---|---|
| Login and connectivity | Actual Paper managed-account handshake; explicit DU/client ID; no Live route |
| Account readiness/permissions | Real ready/EUR Paper cash observations and Helsinki trading permission |
| Contract and subscriptions | Unambiguous conid/HEX/EUR/STK resolution; entitled live bid/ask and last with timestamps; completed volume evidence |
| Session truth | Published reviewed calendar agrees with current broker clock and liquid hours |
| Personal deployment | Exact protected journal identity/head/configuration, baseline backup and runtime wiring verified against Owner-selected inputs |
| Entry | Fresh exact full-plan approval followed by one broker-accepted BUY, only in a separately authorized acceptance |
| Fill and exit | Actual execution/position attribution; automatic first approved STOP/TARGET/MANDATORY_EXIT; one full SELL_TO_CLOSE |
| Closure | Broker-confirmed fill, subsequent zero position and durable CLOSED evidence; real commission evidence before any net-P&L claim |

Account approval, login, permissions, market-data entitlement and fills must not
be inferred from successful tests. Approval delays are an external dependency,
not a reason to fund the account, fabricate evidence or keep an agent idle.

Final external gate: **IBKR_OWNER_SETUP_REQUIRED**.
