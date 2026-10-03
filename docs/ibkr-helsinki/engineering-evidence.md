# Engineering evidence — IBKR Paper / Helsinki

Date: 2026-10-03. Base: reviewed `release/v1-personal-paper` (81f1432).
Scope: isolated `feature/ibkr-helsinki-paper`; no merge or personal deployment.

## Local verification

- Full default suite, with the new journal's real PostgreSQL fixture enabled:
  **5,285 passed, 1,325 skipped**, one warning; 293.07 seconds.
  Core branch coverage **79.19%**, preserving the existing 79% floor.
  Skips are existing opt-in integration suites, not claimed as passing here.
- Full PostgreSQL integration attempt: 1,706 passed, 16 skipped, one failure and
  19 setup errors. The failure was the backup rehearsal's missing `pg_dump` PATH;
  the errors were the required `_paper_exit_test` database-name suffix.
  After correcting only the isolated test environment, the affected Store C,
  integrated deployment and market-journal group passed **25 tests**; the backup
  rehearsal separately passed **one test**. The dedicated CI workflow repeats the
  entire PostgreSQL suite in a fresh cluster with these corrections.
- Focused IBKR identity, risk, canonical proposal, SDK callback, review/setup and
  shared-manager checks: **82 passed**, optional adapter coverage **83.53%** against
  an independent 80% floor. No socket connection to a broker was made.
- Ruff, format, both architecture checkers, strict mypy (445 source files), core
  package build and optional integration package build passed.
- Dependency audit: no known vulnerabilities in the installed verification
  environment (local project itself is not a PyPI dependency to audit).
- Repository secret scan identified only dummy CI credential assignments. Those
  were changed to derive from the disposable test user; the changed workflow
  rescanned with zero findings. No scanner rules or frozen assertions were relaxed.
- Real SDK 10.50.2 serialization was exercised against an in-memory transport,
  never a socket. SDK provenance and limitations are in `owner-setup.md`.

Local PostgreSQL used a new disposable cluster on **127.0.0.1:55437**, with explicit
EMPIRICAL:TEST database markers. No tests targeted personal port 55433. Destructive
fixture setup requires the existing test-identity guard before SQL.

## Safety proof map

| Property | Evidence |
|---|---|
| Broker/conid/venue/currency/account binding | market identity, immutable plan codec and SDK boundary tests |
| Stale/wrong quote, closed/unsupported session | market access and candidate tests; reviewed 2026 calendar |
| Shared quantity/loss/notional and independent gates | canonical proposal usecase exercised with explicit EUR evidence |
| Exact Owner approval and expired-term refusal | plan fingerprint, original quote expiry and persisted approval tests |
| Duplicate entry / exit / collision / restart | atomic PostgreSQL journal claims and shared-manager lifecycle tests |
| Partial fills / UNKNOWN | exact execution reconciliation, no blind resend and partial cancel-before-close tests |
| No short / no Live / cross-routing refusal | default-disabled adapter, exact position/route checks and adversarial tests |
| Position zero | durable post-fill snapshot required before CLOSED, checked in PostgreSQL |
| Alpaca compatibility | default optional hooks are empty; full default and PostgreSQL regression suites |
| Frozen M084 evidence | original checker and frozen tests preserved; SDK is separately packaged |

## Unproven real acceptance

Owner reports TWS/Gateway is not installed or configured. Account readiness,
permissions, live Helsinki data, real contract resolution and the Paper round trip
remain **unverified**. The separate personal market journal, canonical EUR Owner
configuration and opt-in runtime wiring have not been deployed. No existing
Alpaca Store B/C migration or configuration was performed.

History currently labels price P&L before fees; it does not claim net broker P&L.
Missing evidence, unavailable history or ambiguous order state fails closed and
may require operator attention. At-most-once dispatch is not guaranteed execution.

Broker writes during engineering: Alpaca BUY 0, SELL 0, CANCEL 0; IBKR BUY 0,
SELL 0, CANCEL 0; LIVE 0. Real acceptance requires a separate exact-plan Owner
approval after read-only setup and deployment verification.

Final operational gate: **IBKR_OWNER_SETUP_REQUIRED**. CI results are attached to
the dedicated PR and must be green before advancing to acceptance.
