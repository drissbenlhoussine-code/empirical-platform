# M085 identity-safety correction — an order that already exists under our identity

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Not pushed, not merged,
not frozen, not deployed. M086 NOT_STARTED. No Paper or Live order was submitted, no order
endpoint was called, and no acceptance-database row was created or changed in this round.

Previous corrective implementation: `b24c471592619b71dac296d538bb03715d4962da`
("fix(m085): send-time policy binds to configuration, uncertain broker outcomes stop being
terminal", 2026-09-25), on `feature/m085-alpaca-paper-human-approved-execution` (PR #15,
open, unmerged), base `master` `a224076754fb38909ee04c2464e50e51df12d7ad`. That commit
closed D1 and D2 of the 2026-09-14 review and is recorded in
[corrective-pass.md](corrective-pass.md). This document records what was found while
verifying it, and what changed afterwards. The commit that contains this document is the
final local candidate; its SHA is reported in the round report and will be pinned here by a
docs-only follow-up once CI has run on it, because a document cannot name the commit that
first contains it.

## 1. What was verified about `b24c471`, before anything changed

| Gate | Result |
|---|---|
| Working tree after the commit | clean; the four evidence files hidden by `.git/info/exclude` were force-added |
| D1 in production code | preview/submit take exactly three positional arguments; `ExecutionPolicy` is built only from the intent's persisted configuration version (`_policy_for`) or from a stored preview row that re-verifies its own fingerprint; compared pre-claim, in the in-connection final guard, and by the `paper_submission_preview_guard_policy` trigger |
| D2 in production code | `DEFINITIVE_BROKER_REFUSAL_STATUSES = {400, 401, 403, 422}`; connect-phase failure → not sent; send- and read-phase failure → ambiguous; every other status/body → ambiguous → `SUBMISSION_UNKNOWN`; reconciliation no longer skips `SUBMISSION_UNKNOWN`/`IN_PROGRESS` |
| D2 transport proof (scratch, production classes) | 96/96: 500/502/503/504/408/409/429 (+404/418/451/599) × {JSON, HTML, empty, truncated}; `ConnectionResetError`, `BrokenPipeError`, `TimeoutError`, `RemoteDisconnected`, `IncompleteRead` at send and read phases; wrong-order 200s; handler → UNKNOWN with exactly one submission across repeated submits and fresh authorizations |
| Migration chain | linear to `9c4b2e7d5a18`; upgrade installs 22 `paper_*` triggers, downgrade removes exactly the two corrective guards, re-upgrade restores 22; `require_exact_m085_schema_head` refuses `e61b3f9a4c27` and an empty `alembic_version` |
| PostgreSQL suites (temporal, time-basis, lifecycle, concurrency, corrective pass, authority contract, hostile HTTP, M084 file audit) | **430 passed, 0 failed, 0 skipped**, 4 m 59 s |
| Mutation campaign, focused (51 families: D1, D2, temporal, schema head, identity, endpoint) | **51/51 detected, 0 blockers**; whole-tree digest identical before and after ([corrective-pass-mutation-matrix-run3-b24c471.md](corrective-pass-mutation-matrix-run3-b24c471.md)) |
| Manual complementary mutations | **9/9 detected**, each restored and re-verified: 429 and 500 as definitive; reconciliation skipping UNKNOWN; a second dispatch for an attempted intent; the pre-claim policy-fingerprint check removed; submit and preview accepting extra CLI arguments; `min`→`max` on the liquidation deadline; the DB preview-policy guard ignoring the notional cap |
| Static gates | compileall, ruff format (740 files), ruff check, mypy (368 files), architecture positive/negative, frozen-path guard, secret scan `{}`, pip-audit, M083/M084/M085 authority renderers: all green |
| Non-PostgreSQL suite | 3651 passed / 0 failed / 783 skipped, coverage 79.39 % ≥ 79 % (same tree content, run before the commit) |
| Combined full suite, PostgreSQL on | **INTERRUPTED** at ~8 % — the host ran low on memory and the background run was stopped; not a test failure and not reused as evidence |

> **Correction (2026-09-26, A3):** the statement below that psycopg ran its pure-Python
> implementation is verified for the runs in §1 (the implementation was printed) but the
> Application Control block proved transient, and later runs in the same session may have loaded
> the bundled binary implementation (libpq 18.0.3) unannounced. The exact-SHA verification of the
> final candidate pinned and logged `PSYCOPG_IMPL=python`; see
> [final-candidate-2726f6f/README.md](final-candidate-2726f6f/README.md) §1 and §3.

Environment evidence for every PostgreSQL result above and below: PostgreSQL 16.13 on
Windows, native service on 127.0.0.1:5432 with `trust` authentication for 127.0.0.1 (no
password was used, requested or recorded); disposable databases `m085_pgon_c7a41f0` and
`m085_pgon_b24c471` (both owned by `empirical_m085`, both proven empty of acceptance
identifiers before use; `m085_acceptance_2e5c38c` was not touched); psycopg's bundled DLL
is blocked by Windows Application Control on this host, so **psycopg ran its pure-Python
implementation over the system `libpq.dll` 16.0.13** from `C:\Program Files\PostgreSQL\16\bin`
(prefixed to `PATH` for the runs) — no project dependency was changed.

## 2. F1 — the identity-collision defect

**Found during the adversarial review of `b24c471`, not by any test.** The `client_order_id`
is derived — intent id, account reference, approved fingerprint — and never generated, so
that a retry after an ambiguous outcome cannot create a second order. The same property
means that a rebuilt or lost local database, or an earlier process, can produce **the same
identity for an order the broker already holds**. The code then did this:

1. the identity is derived and the order is sent;
2. Alpaca answers HTTP 422 `client_order_id must be unique` — its documented duplicate answer;
3. `is_definitive_broker_refusal` saw a 422 with a JSON body and called it a refusal;
4. the attempt became terminal `REJECTED`, reconciliation never ran on a terminal attempt;
5. the platform lost awareness that a broker-side order exists under its own identity.

No second order was created in that sequence, but the local state (`REJECTED`) and the
broker state (an order exists) diverged permanently and silently. Classified MEDIUM in the
round report; the Owner reclassified it as a **blocking identity-safety defect** and
required a production correction rather than a preflight condition.

## 3. The correction

Every rule below is enforced in production code and has a named detecting test and a
mutation family (section 5).

**422 is classified semantically** (`classify_broker_refusal`,
`decision_candidate/paper_execution.py`). An answer is judged only when it is the broker's
own error document — a JSON object with an integer `code` and a non-empty text `message`:

| Answer | Kind | Consequence |
|---|---|---|
| 400/401/403/422 + broker document, message not about the identity | `DEFINITIVE_REFUSAL` | terminal `REJECTED`, as before |
| 422 + broker document, message says the `client_order_id` must be unique / already exists | `CLIENT_ORDER_ID_EXISTS` | identity reconciliation (below) — never a refusal |
| any status + a message about the `client_order_id` that is not the duplicate answer | `UNCERTAIN` | `SUBMISSION_UNKNOWN`, reconciled |
| the duplicate words on 400/401/403 | `UNCERTAIN` | `SUBMISSION_UNKNOWN`, reconciled |
| malformed body, array, missing/non-integer/boolean `code`, missing/empty/non-text `message` | `UNCERTAIN` | `SUBMISSION_UNKNOWN`, reconciled |
| any status outside {400, 401, 403, 422} | `UNCERTAIN` | `SUBMISSION_UNKNOWN`, reconciled |

`is_definitive_broker_refusal` is now `classify(...) is DEFINITIVE_REFUSAL` and states the
status rule once (a second copy had masked the `definitive_refusal_statuses` mutation, see
section 5). The adapter raises `BrokerIdentityExistsError` for the duplicate answer; a test
that previously asserted the duplicate 422 "is returned as the broker sent it" is
superseded and now asserts the exception.

**The identity is asked about before anything is sent.** In the in-connection final guard
(`before_send`), after the kill switch, configuration, clock and quote are re-read, the
dispatcher calls `fetch_order_by_client_order_id` on the derived identity. Found → nothing is
sent; `BrokerIdentityExistsError(request_sent=False)`. Not found (404) → the send proceeds.
Anything else → nothing is sent and the attempt is `REJECTED` / `NOT_SENT` with the reason
("could not confirm that this client_order_id is unused"): an unconfirmed identity is not a
free one.

**One reconciliation path for both cases** (`_identity_collision` → `_resolve_identity`,
`usecases/paper_execution.py`): the attempt becomes `SUBMISSION_UNKNOWN` with
`failure_code = IDENTITY_EXISTS` and event `CLIENT_ORDER_ID_COLLISION`; the answer that
arrived is recorded as an acknowledgement; the identity is looked up once more; the broker's
order is compared with the authorized order **field by field** — `client_order_id`, symbol,
side, quantity, order type and, for a limit order, the limit price
(`order_identity_mismatches`; a field the broker did not report is a mismatch, not a match):

- exact match → `PAPER_SUBMITTED` then the broker status, event
  `IDENTITY_RECONCILED_EXACT_MATCH`, result note "adopted by identity reconciliation and
  nothing was sent again";
- any mismatch → the state stays `SUBMISSION_UNKNOWN`, event `IDENTITY_COLLISION_MISMATCH`
  naming the fields, result note "NOT adopted … an operator must resolve it";
- lookup failed or not found → the state stays `SUBMISSION_UNKNOWN`, event
  `IDENTITY_LOOKUP_UNRESOLVED`.

The method contains no send. A second submit for the intent, in the same or a new process
or under a fresh human authorization, is refused by the existing-attempt check and by the
database's `UNIQUE (intent_governance_id)` and `UNIQUE (client_order_id)`. The
`client_order_id` is still derived, never replaced.

**Reconciliation compares before it adopts.** `ReconcilePaperOrderHandler` now takes the
authorization repository and applies the same field-by-field comparison to any order the
broker reports under the attempt's identity, before any transition; a mismatch is recorded
as `IDENTITY_COLLISION_MISMATCH` and the state does not move. The entrypoint
`empirical-platform-reconcile-paper-order` and `tools/m085_paper_acceptance.py` are wired
accordingly. The broker order view now carries `limit_price`.

**Fakes were made faithful, not permissive.** `FakeBroker` used to answer every lookup with
"found"; it now knows only the orders it received, echoing exactly what was sent, and
answers 404 otherwise — so the pre-send check passes for a fresh dispatch and finds the order
after a crash without any test saying so. Tests that had scripted a lookup answer describing
the unit fixture's order while the world's authorized order differed were corrected to
describe the authorized order (F1 now refuses the former, correctly).

## 4. What is proved, and how

Unit, fakes only (`tests/unit/test_m085_identity_collision.py`, 42 tests): the
classification table above, the mismatch function per field and for unreported fields, the
dispatch handler (fresh identity → one lookup, one send; exact match before sending →
adopted, no send; mismatch on symbol/quantity/side/limit/type → collision, no send, no
second dispatch under a new process or a fresh authorization; lookup 5xx → nothing sent;
duplicate 422 after a 404 pre-check → reconciled; duplicate raised by the adapter → same
path; duplicate whose lookup finds nothing → stays UNKNOWN), and recovery after restart
(UNKNOWN and IN_PROGRESS recovered by new handler instances through the same identity;
mismatch refused after restart; a rebuilt database meets the broker's exact order and sends
nothing; a rebuilt database meets a different order and records a collision).

Against PostgreSQL (`tests/integration/test_m085_identity_collision_postgres.py`, 6 tests;
production handlers over the real repositories, a controlled broker fake, separate
persistence services standing for separate processes): ambiguous answer → process ends → new
process recovers `SUBMISSION_UNKNOWN` by lookup, no resend; crash after the send
(`BaseException` from the broker) → `SUBMISSION_IN_PROGRESS` in the real table → new process
leaves it alone inside the not-found window, adopts the found order after it, no resend;
recovery refuses a different order under the identity; the database is truncated and rebuilt
with the same identity → the broker's exact order is adopted and nothing is sent, and the
database itself refuses a forged second attempt; a rebuilt database meets a different order →
collision recorded, nothing sent; a duplicate 422 after the send is stored (`SUBMIT 422`,
`RECONCILE 200`) and reconciled.

Adapter, real HTTP framing against a hostile local server
(`tests/integration/test_m085_hostile_http.py`): the duplicate 422 raises
`BrokerIdentityExistsError(request_sent=True)`; an ordinary 422 with the broker's document
is still a definitive refusal; six unknown 422 shapes and the duplicate words on a 400 are
ambiguous; a looked-up order reports its limit price; an uncertain 422 echoing a credential
is scrubbed on the exception path.

Suite results on the working tree that became the final candidate (before the commit):
M085 unit suites 686 passed; architecture 30 passed (including the new
`test_frozen_milestones.py`); hostile HTTP 123 passed; PostgreSQL identity suite 6 passed;
PostgreSQL temporal 7, corrective pass, lifecycle, concurrency, time-basis and authority
contract 292 passed after the fixture correction above; ruff format/check, mypy: clean.

## 5. Mutation evidence for this round

Campaign families added (`tools/m085_mutation_campaign.py`, 134 families in total), each
run with the repository tool — mutate the real rule, require the named test to fail for the
intended reason, restore by SHA-256, re-run green:

| Family | Rule removed | Result |
|---|---|---|
| `duplicate_identity_422_is_not_a_refusal` | the duplicate 422 is an existing identity | EXECUTED_PASS |
| `unknown_422_shape_fails_closed` | a 422 without an integer `code` is uncertain | EXECUTED_PASS |
| `identity_collision_looks_the_identity_up` | a collision looks the SAME identity up | EXECUTED_PASS |
| `pre_send_lookup_uses_the_derived_identity` | the pre-send lookup asks about the derived id, not a replacement | EXECUTED_PASS |
| `no_resend_after_a_collision` | an intent with any attempt is never dispatched again | EXECUTED_PASS |
| `identity_match_checks_the_symbol` | a different symbol is never adopted | EXECUTED_PASS |
| `identity_match_checks_the_quantity` | a different quantity is never adopted | EXECUTED_PASS |
| `identity_match_checks_the_side` | a different side is never adopted | EXECUTED_PASS |
| `reconcile_recovers_unknown_after_restart` | a new process reconciles UNKNOWN | EXECUTED_PASS |
| `reconcile_refuses_a_mismatching_order` | reconciliation never adopts a differing order | EXECUTED_PASS |
| `database_rebuilt_meets_existing_identity` | against PostgreSQL, a rebuilt database sends nothing | EXECUTED_PASS |
| `frozen_path_guard_covers_m084` | the guard governs M084 | EXECUTED_PASS |
| `frozen_path_guard_pins_m084_to_the_ratified_commit` | M084 is compared against `1127134` | EXECUTED_PASS (see below) |
| `adapter_uncertain_status_is_ambiguous` (retargeted) | adapter classifies, not `status >= 400` | EXECUTED_PASS |
| `definitive_refusal_requires_the_brokers_document` (retargeted) | a non-object is not a document | EXECUTED_PASS |
| `definitive_refusal_statuses` | only 400/401/403/422 can be definitive | EXECUTED_PASS (see below) |

Two campaign findings, both repaired and re-run, recorded rather than hidden
([mutation-matrix-identity-and-freeze.md](mutation-matrix-identity-and-freeze.md) first run
16/18; [mutation-matrix-identity-and-freeze-rerun.md](mutation-matrix-identity-and-freeze-rerun.md)
6/7; [mutation-matrix-definitive-statuses-rerun.md](mutation-matrix-definitive-statuses-rerun.md)
1/1):

- `definitive_refusal_statuses` **survived** its first run: F1 had made the document shape a
  separate rule, so the detecting test's bodies (which carried no `code`) were refused by
  the shape rule whether or not the status rule existed, and a second copy of the status
  check in `is_definitive_broker_refusal` masked the mutation. Repaired by stating the status
  rule once and by adding the broker's complete document on 404/408/409/429/500/503/504 to
  the detecting test. Detected on re-run.
- `frozen_path_guard_pins_m084_to_the_ratified_commit` was **detected** but the campaign
  reported "the test does not pass again after restoration": the mutated and original commit
  ids are both forty characters, so the byte-compiled cache written from the mutated source
  was reused by the restored run (Python validates `.pyc` by size and one-second mtime).
  Repaired in the campaign tool — the mutated module's cache is deleted before and after each
  run and pytest runs with `-B` — a harness correction, not a product one. Detected on
  re-run.

## 6. M084 governance: Owner ratification and mechanical freeze

Recorded in `PROJECT_CHECKPOINT.md` section 119 and the `M084_POST_FREEZE_*` /
`M084_FROZEN_PATH_*` fields. The Owner ratified `1127134623b25178b4d98236d5ab75f8f2134760`
for exactly its six audit-tooling files; history is not rewritten. `tools/check_frozen_paths.py`
now governs M083 (27 paths, base `707161a1`) **and** M084 (69 paths, base `1127134`,
manifest [m084-frozen-path-digests.json](m084-frozen-path-digests.json), kept in this package
because it governs M084's own). Proved by `tests/architecture/test_frozen_milestones.py`: an
M084 mutation is detected, an M083 mutation is still detected, the exact ratified state
passes, the manifest is the content at `1127134`, the six ratified files are governed, the
M084 freeze record, authority documents and migration are byte-identical to the ratified
commit, and the checkpoint record exists. The guard runs in CI through `python -m pytest`.
The secret scanner's one remaining exemption -- a manifest line is cleared only when it maps
a tracked path to the blob id git itself records for that path -- now covers both generated
manifests; found when the exact-SHA gate run flagged the new manifest's 69 blob ids, repaired
in `tools/secret_scan_targets.py` with tests for both manifests and for an invented id.

## 7. What this round did not do

No proposal, approval, Paper intent, acceptance-database mutation, Alpaca order or M086
work. CI has not run on the final candidate; the `foundation` and `M085 temporal PostgreSQL`
workflows last validated `754ceda`. The exact-SHA regression on the final candidate is
reported in the round report, not here, and will be appended by a docs-only follow-up.

## 8. Residual limits

- The identity comparison uses what the broker reports; a broker that reports our
  identity with our exact terms for an order that is nevertheless not ours (an
  operator-placed order carrying the same `client_order_id`) is adopted. Nothing in the
  broker's answer can distinguish that case, and the terms adopted are the authorized ones.
- A lookup that fails before the send leaves the intent with a terminal `NOT_SENT` attempt,
  so a new intent is needed to try again. This is the fail-closed choice; its operator cost
  is disclosed.
- `RECONCILE_UNUSABLE_ANSWER` still reuses one event id per attempt (pre-existing).
