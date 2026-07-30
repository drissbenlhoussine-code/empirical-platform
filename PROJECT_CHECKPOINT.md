# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative checkpoint for the latest frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Checkpoint content baseline (HEAD this content was authored against) | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (`chore: freeze MILESTONE-028 Application Query/QueryHandler Contracts implementation`, pushed) |
| Checkpoint content baseline origin/master | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (identical — pushed) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

**On self-reference:** the values in this table and in the `CHECKPOINT_CONTENT_BASELINE_*` fields below describe the repository state this checkpoint content was authored against. They are not a live, self-updating record of Git HEAD. A document cannot cite the hash of the commit that first contains it without creating a recursive follow-up-commit cycle. To find live repository truth, run `git rev-parse HEAD` and `git status --short --branch` directly.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-028
CHECKPOINT_CONTENT_BASELINE_BRANCH=master
CHECKPOINT_CONTENT_BASELINE_HEAD=fc5e8659d5a35b609c96a689b8b250f7f869d73d
CHECKPOINT_CONTENT_BASELINE_ORIGIN=fc5e8659d5a35b609c96a689b8b250f7f869d73d
CHECKPOINT_CONTENT_BASELINE_STATUS=PUSHED_UP_TO_DATE_AT_M028_IMPLEMENTATION_FREEZE_M029_SCOPE_SELECTED

M020_STATUS=APPROVED_AND_FROZEN
M020_DESIGN_COMMIT=fd96b70366a7bbed2172a8f51d7d7cc52b60bc41
M020_IMPLEMENTATION_COMMIT=e20bc76d2dc0be359cea2c385c210e081fb48a35
M020_CORRECTION_COMMIT=efed86be608471fdaa2956f7827fc9236209763a
M020_FREEZE_COMMIT=40dd6b6a0c02e710e3f7efe84e8959af51f839f9

M021_STATUS=APPROVED_AND_FROZEN
M021_DESIGN_COMMIT=06d22defd6f06b96d0a46c5e91bc169e55e674e5
M021_DESIGN_FREEZE_COMMIT=abeba5a1407a8d31ce6d07fe3e071804d2385457
M021_IMPLEMENTATION_COMMIT=73ffd3647bce749dff5c8f228f90f3be79413a9c
M021_IMPLEMENTATION_FREEZE_COMMIT=fdb180a2b21776cf37fe36826741a54ef7b43ad4

M022_STATUS=APPROVED_AND_FROZEN
M022_DESIGN_COMMIT=ccd1077a733915e4a345001e505e25bee33696a9
M022_DESIGN_CORRECTION_COMMIT=1179e307782549401157cf2b251276614fe10fa2
M022_DESIGN_FREEZE_COMMIT=4ce351d6d933c9199310337add4490cafcca4d20
M022_IMPLEMENTATION_COMMIT=69920125214b577485096406b9a2b2b573bead81
M022_IMPLEMENTATION_CORRECTION_COMMIT=c7d75334ae9f7fd760e67135eb90248f1747f1b5
M022_IMPLEMENTATION_FREEZE_COMMIT=10425e85b63a0b6f18b73b962355f22176cb279c

M023_STATUS=APPROVED_AND_FROZEN
M023_DESIGN_COMMIT=a6e1350b8c37467d3a33b73c6e254c34ce4aab1b
M023_DESIGN_CORRECTION_COMMITS=7dcc7c10e247163d6e029fb6520fd76846e328d6,0f5c982a23f1b8c51ed5d56ff0a0cdab0c03c4bb,7933b567129e525ec4cf6235de3f22e3d737860f
M023_DESIGN_FREEZE_COMMIT=cb6ff16788b2ad8a26ed9f82a903d276daa6d3c4
M023_IMPLEMENTATION_COMMIT=4a93e44ea937885d45f5ce6587c2b963452ac8ff
M023_EVIDENCE_CORRECTION_COMMITS=f3f7fc097db37470dc731009176e065df1d5a70b,c6fb2c9d7f153d1b3fbee97a7b647d7ecca6d5af,5679034cf2f3887f7329cf56c5c73c1865208451
M023_IMPLEMENTATION_FREEZE_COMMIT=4ce800d3609ba7c621eadffc338bc5bc2503228d

M024_STATUS=APPROVED_AND_FROZEN
M024_SCOPE=Multi-Aggregate Persistence Unit of Work
M024_DESIGN_COMMIT=f2a22817cb433142960dba6509c50b4b39066ebe
M024_DESIGN_CORRECTION_COMMIT=03d640fa8e0f34fb3348226c4bc0eeaa386832b4
M024_DESIGN_FREEZE_COMMIT=ed0a4198dab515c4d204f3046ea2cfc114390bef
M024_IMPLEMENTATION_COMMIT=5fd00247bdb25b01a4f5de831b5b9baa483af6a5
M024_IMPLEMENTATION_CORRECTION_COMMIT=9f8bb60507f52ee410f1fd3010ad11641884f329
M024_IMPLEMENTATION_FREEZE_COMMIT=b2283281f670703c95de0b6fe8ee83d58c5e3ac1

M025_SCOPE=Repository Runtime Composition
M025_DESIGN_COMMIT=e9db9292982f3795cc51c29de290af2e34e1b33b
M025_DESIGN_CORRECTION_COMMIT=ec6e8db23dddf20ae8ab2efec17908dc61a69be4
M025_DESIGN_FREEZE_COMMIT=fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad
M025_IMPLEMENTATION_COMMIT=907eb9c0f6ca04f0b5c660c8bcf1da09e3deeb9b
M025_TRUTH_CORRECTION_COMMIT=956f4f85c5e08d76c7f1a54aa1a6ff8b40645fc8
M025_IMPLEMENTATION_FREEZE_COMMIT=0d57c36adf8b60ea3be9e86fa3814d1e2b459253
M025_STATUS=APPROVED_AND_FROZEN

M026_SCOPE=Foundation Runtime Repository Composition
M026_DESIGN_COMMIT=110bdab25a7867798ec1d14faba816f22738a7d2
M026_DESIGN_CORRECTION_COMMIT=1664c8e17cedac80715b9eb82ffff14620423191
M026_DESIGN_FREEZE_COMMIT=bb434cd19a21cf25571ab14326cfdbd536de441c
M026_IMPLEMENTATION_COMMIT=c6802c5d3f3b295368fa36d8d50cd26ecca8f460
M026_IMPLEMENTATION_FREEZE_COMMIT=45f4916d1fcdd76b28fffa81c23704f6b0355c3d
M026_STATUS=APPROVED_AND_FROZEN

M027_SCOPE=Application Command/Handler Contracts
M027_DESIGN_COMMIT=2b914ffdf4425d7d6904caaa681d39142d73ba7e
M027_DESIGN_CORRECTION_COMMIT=7753b135bb324a7c1337c542d87660a855c3ee0f
M027_DESIGN_FREEZE_COMMIT=64abc16156b949491ded4ff239d2c249aac569a8
M027_DESIGN_STATUS=APPROVED_AND_FROZEN
M027_IMPLEMENTATION_COMMIT=c7bc632a1568203f33635191ea70b4e5784e1d86
M027_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M027_IMPLEMENTATION_APPROVAL=APPROVED
M027_IMPLEMENTATION_FREEZE=FROZEN
M027_STATUS=APPROVED_AND_FROZEN

M028_SCOPE=Application Query/QueryHandler Contracts
M028_DESIGN_COMMIT=db99194277aecef7b5a5c74f576a940d6e24e399
M028_DESIGN_CORRECTION_COMMIT=bff0865f7f2495b1854a86d04c0db66ecb0512b1
M028_DESIGN_FREEZE_COMMIT=e062d14ef80feb3df4f4862c3e117fb930b41c01
M028_DESIGN_STATUS=APPROVED_AND_FROZEN
M028_IMPLEMENTATION_COMMIT=a71de466c707f5665f6826f0fcb35f1aee90181c
M028_IMPLEMENTATION_CORRECTION_COMMIT=8d3069a464ba58d53b51e687d142a7e42474e7af
M028_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M028_IMPLEMENTATION_APPROVAL=APPROVED
M028_IMPLEMENTATION_FREEZE=FROZEN
M028_STATUS=APPROVED_AND_FROZEN

M029_SCOPE=Application Service Orchestration
M029_SCOPE_SELECTION_COMMIT=449d7ef3005402e4c92052fc8720dbd19b623102
M029_SCOPE_SELECTION_STATUS=SCOPE_SELECTED_READY_FOR_RE_REVIEW
M029_SCOPE_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M029_SCOPE_STATUS=APPROVED_AND_FROZEN
M029_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M029_SCOPE_FREEZE_COMMIT=22cec98d4bd724e00754551034b896236989acec
M029_DESIGN_STATUS=APPROVED_AND_FROZEN
M029_DESIGN_COMMIT=f047d3a33fcd8ba4849a5be1f75abc74c64a362f
M029_DESIGN_FREEZE_COMMIT=81650aeb58e073134127062e8451de6d241f7c5e
M029_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M029_IMPLEMENTATION_COMMIT=5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986
M029_IMPLEMENTATION_HASH_RECORDING_COMMIT=231584e1bb95cd24f88f86691703564bbe6237de
M029_EVIDENCE_GOVERNANCE_CORRECTION_COMMIT=a2a64d6bbf166b1d0ef63cbdbb4a6842d50f7ba5
M029_IMPLEMENTATION_OWNER_FREEZE_STATUS=APPROVED_AND_FROZEN
M029_IMPLEMENTATION_FREEZE_COMMIT=8a076c69314e5ea0fba5835fc1c9d165c7498a2c
M029_STATUS=APPROVED_AND_FROZEN
NEXT_PERMITTED_ACTION=MILESTONE-030 SCOPE SELECTION
```

## 3. Frozen Milestone Summary

M020 froze persistence-neutral domain repository and optimistic-concurrency contracts for Campaign, Run, EvidencePackage, and Review.

M021 froze mapper contracts and durable-record shapes for the same four aggregates.

M022 froze the PostgreSQL schema and Alembic migration that persist those durable records.

M023 froze concrete PostgreSQL mappers and repository adapters implementing M020/M021 over M022.

M024 froze the low-level multi-aggregate persistence Unit of Work primitive, exposed only as `PostgresPersistenceService.run_composed(operations)`, allowing multiple repository operations that share one `PostgresPersistenceService` to commit or roll back atomically without changing repository Protocols or concrete repository adapter source files.

M025 froze the repository runtime composition boundary, `PostgresRepositoryRuntime`, composing the four M023 repository adapters over one shared, caller-owned `PostgresPersistenceService` and delegating cross-repository atomic execution to the frozen M024 `run_composed` primitive, with eager one-time construction, `is`-stable property identity, mandatory constructor validation, no readiness probe, and independent-root support governed by the existing M024 same-service-identity rule.

M026 froze the extension of the existing `FoundationRuntime` process-startup composition root with a `repository_runtime: PostgresRepositoryRuntime | None` field, constructed inside `initialize_infrastructure_runtime` and `initialize_foundation_runtime_with_postgresql` only when the persistence service in use is a real `PostgresPersistenceService` (an `isinstance` guard that leaves the field `None` for every `FakePersistenceService`-based caller, preserving all pre-existing bootstrap test behavior unmodified), with the identical same-service-identity, no-second-cleanup-entry, and repr/credential-safety discipline M025 already established.

M027 froze the persistence-neutral, domain-agnostic `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol in `shared/contracts/command.py` — the application-layer command/write-side vocabulary — with verified contravariant/covariant generics, a mypy-checked positive conformance proof, and an isolated, empirically verified negative type-check fixture mechanism kept outside the canonical `mypy` gate. No concrete command, handler, orchestration, dispatcher, registry, or error hierarchy was introduced.

M028 froze the persistence-neutral, domain-agnostic `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol in `shared/contracts/query.py` — the application-layer query/read-side counterpart to M027's `CommandHandler` — with the identical verified contravariant/covariant generics pattern, a mypy-checked positive conformance proof, the identical negative type-check fixture mechanism, and an explicit frozen distinction between the two contracts' declared relationship (no inheritance, shared base, alias, or cross-import) and Python's structural-typing reality (a single concrete class may satisfy both Protocols simultaneously when types align, which this design does not attempt to prevent). Read-side intent is semantic only; no mechanical read-only enforcement exists. No concrete query, handler, orchestration, dispatcher, registry, cache, pagination wrapper, or error hierarchy was introduced.

## 4. MILESTONE-024 Closure Evidence

M024 implementation freeze commit: `b2283281f670703c95de0b6fe8ee83d58c5e3ac1`.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `366 passed, 96 skipped`, coverage `82.15%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 255 targets |
| Ruff format/check | PASS |
| mypy | PASS - 79 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `87 passed` across M022/M023/M024 integration suites |

M024 does not authorize repository runtime composition, application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution.

## 5. MILESTONE-025 Closure Evidence

M025 implementation freeze commit: `0d57c36adf8b60ea3be9e86fa3814d1e2b459253`.

Authority chain: design `e9db9292982f3795cc51c29de290af2e34e1b33b` → design correction `ec6e8db23dddf20ae8ab2efec17908dc61a69be4` → design freeze `fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad` → implementation `907eb9c0f6ca04f0b5c660c8bcf1da09e3deeb9b` → truth correction `956f4f85c5e08d76c7f1a54aa1a6ff8b40645fc8` → implementation freeze `0d57c36adf8b60ea3be9e86fa3814d1e2b459253`. Repository evidence after M024 identified the scope as **Repository Runtime Composition** (M024 Design Section 21 explicitly deferred "Candidate E, repository runtime composition"; M024 Implementation Freeze Section 7 explicitly did not authorize it).

Independent review found one MAJOR finding at the design stage (repeated-access identity and eager-vs-lazy construction were undefined; corrected in the design-correction commit) and one MAJOR governance-truth finding at the implementation stage (`PROJECT_CHECKPOINT.md` and the external review package described the implementation as uncommitted after the implementation commit already existed; corrected in the truth-correction commit, verified byte-for-byte consistent across all governance artifacts on final re-review). No functional, architectural, PostgreSQL, test, or security defect was found at any stage.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `389 passed, 105 skipped`, coverage `82.60%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 264 targets |
| Ruff format/check | PASS |
| mypy | PASS - 80 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `96 passed` across M022/M023/M024/M025 integration suites |
| External review package | PASS - `complete.diff` byte-identical to Git, 28/28 manifest hashes verified, ZIP SHA-256 `5785fd5bb4e1f9e8a0aec7952e9a08fd940f68cc88da409ba12c807c671c9fb9` |

M025 does not authorize application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution, or any MILESTONE-026 implementation.

## 6. MILESTONE-026 Closure Evidence

M026 implementation freeze commit: `45f4916d1fcdd76b28fffa81c23704f6b0355c3d`.

Authority chain: design `110bdab25a7867798ec1d14faba816f22738a7d2` → design correction `1664c8e17cedac80715b9eb82ffff14620423191` → design freeze `bb434cd19a21cf25571ab14326cfdbd536de441c` → implementation `c6802c5d3f3b295368fa36d8d50cd26ecca8f460` → implementation freeze `45f4916d1fcdd76b28fffa81c23704f6b0355c3d`. Repository evidence after M025 identified the scope as **Foundation Runtime Repository Composition** (the one process-startup composition root, `FoundationRuntime`, had no way to obtain a `PostgresRepositoryRuntime`, and the existing bootstrap test suite revealed the `FakePersistenceService`-compatibility constraint the design had to resolve).

Independent review found exactly two MINOR documentation-completeness findings at the design stage (repr/credential-safety rule and test obligation; post-construction failure and cleanup semantics — both corrected in the design-correction commit) and no finding at all at the implementation stage. No functional, architectural, PostgreSQL, test, or security defect was found at any stage.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `406 passed, 110 skipped`, coverage `82.70%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 271-272 targets |
| Ruff format/check | PASS |
| mypy | PASS - 80 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| Disposable PostgreSQL regression | PASS - `101 passed` across M022/M023/M024/M025/M026 integration suites |
| External review package | PASS - `complete.diff` byte-identical to Git, 29/29 manifest hashes verified, ZIP SHA-256 `5be251764869a1a2069ee46148d0b0e650517b0f5c53b6fe29c2f769e169ee9a` |

M026 does not authorize application services, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data behavior, vendor behavior, trading behavior, or any empirical campaign execution, or any MILESTONE-027 implementation.

## 7. MILESTONE-027 Closure Evidence

Authority chain: design `2b914ffdf4425d7d6904caaa681d39142d73ba7e` → design correction `7753b135bb324a7c1337c542d87660a855c3ee0f` → design freeze `64abc16156b949491ded4ff239d2c249aac569a8` → implementation `c7bc632a1568203f33635191ea70b4e5784e1d86` → implementation freeze recorded via `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md` (this checkpoint update is bundled into that same freeze commit; see that document for the exact freeze commit's own hash, which this content cannot self-cite without a recursive cycle — see Section 1's self-reference note). Repository evidence after M026 identified the scope as **Application Command/Handler Contracts** (no `Command`/`Handler` type existed anywhere in the codebase; M020's repository-Protocol precedent was the direct model for freezing a contract before any concrete implementation).

Independent review found two MAJOR findings at the design stage (generic variance was invariant rather than contravariant/covariant — an actual `mypy`-rejected Protocol definition, verified by direct experimentation; the negative type-check strategy for proving malformed handlers rejected was undefined) and one MINOR finding (stale Scope Selection wording describing rejected components as selected) — all corrected in the design-correction commit. Independent review of the implementation found zero CRITICAL, zero MAJOR, and zero blocking MINOR findings; no correction commit was required.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `416 passed, 110 skipped`, coverage `82.73%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 288 targets |
| Ruff format/check | PASS |
| mypy | PASS - 81 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| External review package | PASS - `complete.diff` byte-identical to Git, 31/31 manifest hashes verified, ZIP SHA-256 `0b87d30525690ef22dba1d9eaef9d956ddeb8cf305c5dee27519a984c4bb64b0` |

M027 does not authorize any concrete `Command`/`CommandHandler` implementation, a handler-level error hierarchy, a `Command` marker, a dispatcher/registry, application service orchestration, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign execution behavior, or any MILESTONE-028 implementation start on its own authority.

## 8. MILESTONE-028 Closure Evidence

Authority chain: design `db99194277aecef7b5a5c74f576a940d6e24e399` → design correction `bff0865f7f2495b1854a86d04c0db66ecb0512b1` → design freeze `e062d14ef80feb3df4f4862c3e117fb930b41c01` → implementation `a71de466c707f5665f6826f0fcb35f1aee90181c` → narrow checkpoint correction `8d3069a464ba58d53b51e687d142a7e42474e7af` (removed one duplicated `M029_STATUS=NOT_STARTED` line from this document's own prior Section 2, discovered during repository-truth verification; no source, test, or fixture file touched) → implementation freeze recorded via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md` (this checkpoint update is bundled into that same freeze commit; see that document for the exact freeze commit's own hash, which this content cannot self-cite without a recursive cycle — see Section 1's self-reference note). Repository evidence after M027 identified the scope as **Application Query/QueryHandler Contracts** — the CQRS read-side counterpart to M027's `CommandHandler`.

Independent review found one MAJOR finding at the design stage (structural interchangeability with `CommandHandler` was overstated as "no type relationship" when Python's structural typing allows one concrete class to satisfy both Protocols simultaneously when types align) and one MINOR finding (read-only semantics described without stating clearly that it is not mechanically enforced) — both corrected in the design-correction commit. Independent review of the implementation found zero CRITICAL, zero MAJOR, and zero blocking MINOR findings; no implementation correction commit was required. The narrow checkpoint correction (`8d3069a`) is a documentation-only truth fix discovered during freeze-mission repository-truth verification, not an implementation defect.

Fresh freeze validation:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `scripts/verify.ps1` | PASS - `438 passed, 110 skipped`, coverage `82.77%` |
| `scripts/security.ps1` | PASS - pip-audit clean, secret scan 302 targets |
| Ruff format/check | PASS - 176 files formatted |
| mypy | PASS - 82 source files |
| Architecture checker | PASS |
| Build | PASS - sdist and wheel built |
| External review package | PASS - `complete.diff` byte-identical to Git, 40/40 manifest hashes verified, ZIP SHA-256 `7a619efc5b447051012587a2683be5bae620b714ce9632e43f6870480e487f73` |

M028 does not authorize any concrete `Query`/`QueryHandler` implementation, a declared relationship/shared base/unification with `CommandHandler`, a query-level error hierarchy, a `Query` marker, a dispatcher/registry, caching, pagination, read-only transaction enforcement, application service orchestration, retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign execution behavior, or any MILESTONE-029 work.

## 9. Deferred Capabilities

- MILESTONE-030 scope selection (M029 is now APPROVED_AND_FROZEN at scope, design, and implementation — see Section 12);
- retry-on-`OptimisticConcurrencyConflict` policy after concrete business handlers exist;
- APIs, workers, Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or empirical campaign execution behavior.

## 10. Next Authorized Work

MILESTONE-027 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 7). MILESTONE-028 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 8): the corrected design (Version 1.1) was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN_FREEZE.md`; the implementation, reviewed with zero CRITICAL, zero MAJOR, and zero blocking MINOR findings, was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md`. MILESTONE-029 is `APPROVED_AND_FROZEN` at the scope stage (Section 11; scope-freeze commit `22cec98d4bd724e00754551034b896236989acec`), at the design stage (design commit `f047d3a33fcd8ba4849a5be1f75abc74c64a362f`, frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md`), and now at the implementation stage (implementation commit `5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986`, owner-frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_FREEZE.md` after a final independent implementation re-review found all previously blocking evidence/governance findings resolved; see Section 12). MILESTONE-029 is now fully `APPROVED_AND_FROZEN` at every stage. The next authorized action is MILESTONE-030 SCOPE SELECTION.

## 11. MILESTONE-029 Scope and Design

**Scope:** Application Service Orchestration — the application invocation boundary that routes commands to `CommandHandler` implementations and queries to `QueryHandler` implementations via two composition-bound entry points, with handler-owned transaction execution and transparent error propagation.

**Why now:** M027-M028 provide the CQRS vocabulary (`CommandHandler` and `QueryHandler` Protocols); M029 provides the orchestration that calls them. Without M029, those Protocols are unreachable abstractions. With M029, every business logic layer above it (APIs, workers, Audit, Decision, market-data execution) becomes possible.

**Dependency chain:**
- M020-M026 (persistence foundation) → provides infrastructure.
- M027-M028 (CQRS contracts) → defines what orchestration calls.
- M029 (orchestration) → routes commands and queries to handlers.
- Later concrete business-handler milestones → define actual commands and handlers.

**Scope selection document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_SELECTION.md` (commit `449d7ef`).

**Scope freeze document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_FREEZE.md` (commit `22cec98`).

**Design document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md` (commit `f047d3a`) — underwent three independent correction passes before final approval: Pass I corrected an options-catalogue structure into concrete architectural decisions; Pass II restated the exact frozen M024/M025 `run_composed()` contract and resolved transaction/error/handler-resolution decisions; Pass III resolved five remaining blocking findings (architectural emptiness, an unjustified `ApplicationBoundaryError`, unspecified runtime Protocol validation, non-implementable milestone-number architecture rules, and inaccurate async-deferral wording).

**Design freeze document:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md`.

**Status:** Scope APPROVED_AND_FROZEN. Design APPROVED_AND_FROZEN. Implementation APPROVED_AND_FROZEN. MILESTONE-029 is fully complete.

## 12. MILESTONE-029 Implementation Evidence and Owner Freeze

**Implementation commit:** `5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986` (`feat: implement M029 application service orchestration`).

**New package:** `src/empirical_platform/application/` — `CommandEntryPoint[CommandT, ResultT]` and `QueryEntryPoint[QueryT, QueryResultT]`, each a composition-bound callable wrapping exactly one frozen M027/M028 handler, invoked exactly once per call, propagating results and exceptions unchanged. No handler discovery, no transaction ownership, no custom exception hierarchy, no runtime Protocol introspection, synchronous only — matching the frozen design at every decision point in Sections 5-9 of `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md`.

**Architecture enforcement:** `tools/check_architecture.py` extended with an `"application": {"shared"}` allowed-import rule, a `FORBIDDEN_IMPORT_PREFIXES["application"]` entry blocking `empirical_platform.shared.persistence`/`sqlalchemy`/`psycopg`/`boto3`, and `"entrypoints": {"shared", "application"}` permitting transport to depend on the application boundary. Domain feature packages and persistence retain no path to `application` (enforced by omission from their existing allow-lists, unchanged).

**Tests added:** `tests/unit/test_command_entry_point.py`, `tests/unit/test_query_entry_point.py` (behavioral: exactly-once invocation, unchanged input/result/exception identity, natural-failure-on-malformed-handler), `tests/unit/test_application_boundary_invariants.py` (structural: import surface, no exception hierarchy, no runtime introspection, no registry/discovery identifiers, synchronous-only, distinct command/query types), `tests/unit/test_application_boundary_composition.py` (composition/transport-binding pattern), plus three architecture fixtures under `tests/fixtures/illegal_imports/` and two new assertions in `tests/architecture/test_module_boundaries.py`.

**Validation gates (fresh run against implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite | PASS — `464 passed, 110 skipped`, coverage `82.85%` (threshold 80%) |
| Focused MILESTONE-029 tests | PASS — `28 passed` |
| Ruff format/check (`src tests tools`) | PASS — 184 files formatted, 0 lint issues |
| mypy strict | PASS — 85 source files (was 82; +3 for the new package) |
| Architecture checker | PASS — 0 violations |
| Build | PASS — sdist and wheel built, `application` package present in wheel contents |

**No M020-M028 frozen contracts changed.** No M029 scope/design/freeze documents changed. No persistence, runtime, or transport implementation added. No MILESTONE-030 work started.

**Independent review history:** The first implementation review found the implementation code conformant but rejected the review package on two evidence/governance defects — a missing external-review ZIP archive and stale contradictory M029 narrative in this document. Both were corrected in commit `a2a64d6bbf166b1d0ef63cbdbb4a6842d50f7ba5` (`docs: correct M029 review governance state`) without touching any source, test, or architecture-rule file. A final independent implementation re-review then evaluated commit `a2a64d6` and found all previously blocking findings resolved, concluding: **M029 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Owner freeze:** The owner formally froze the implementation via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_FREEZE.md`. MILESTONE-029 is now `APPROVED_AND_FROZEN` at every stage: scope, design, and implementation.

**Review status:** COMPLETE. Owner-frozen. No further M029 implementation change is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

**Next permitted action:** MILESTONE-030 SCOPE SELECTION.
