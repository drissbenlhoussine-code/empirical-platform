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

M030_SCOPE=Concrete Application Command Vertical Slice (Campaign Creation)
M030_SCOPE_STATUS=APPROVED_AND_FROZEN
M030_SCOPE_COMMIT=2b4ac748304d3859b78b6a1900849fab7b6fec35
M030_SCOPE_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_SCOPE_FREEZE_COMMIT=52f07c03195926e4f3a67dc1524aba7c206a09cb
M030_DESIGN_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_COMMIT=6c12c77fdded4d42caaba1f37287dabf2c5c577a
M030_DESIGN_CORRECTION_COMMIT=b0dba94927c8067f0d55aa6790bcf71bb82cb0a6
M030_DESIGN_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_FREEZE_COMMIT=990ce7c82a531015b883f7a2d3f8889107e6eee9
M030_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M030_IMPLEMENTATION_COMMIT=bb66826225f621368ea317b5757631bf94731a56
M030_IMPLEMENTATION_REVIEW_STATUS=APPROVED_FOR_OWNER_FREEZE
M030_IMPLEMENTATION_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_IMPLEMENTATION_FREEZE_COMMIT=64682d1790ed3efacbdbdb6d99b3f3b4e7bbee90
M030_STATUS=APPROVED_AND_FROZEN

M031_SCOPE=Concrete Application Query Vertical Slice (Campaign Retrieval)
M031_SCOPE_STATUS=APPROVED_AND_FROZEN
M031_SCOPE_COMMIT=68bd50d1d2e2d38abb3e3e389e4a8dde6d996848
M031_SCOPE_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M031_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_SCOPE_FREEZE_COMMIT=b31b664e9395aa0a988ccd1aecc21d6b06436d39
M031_DESIGN_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_COMMIT=f73b924d3c36e4796087aa4bb889a8dcde7b548e
M031_DESIGN_REVIEW_STATUS=APPROVED_WITH_NON_BLOCKING_OBSERVATIONS
M031_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_FREEZE_COMMIT=196150dcde88610c9bc78e6bd0ff40d4d5da9d9b
M031_IMPLEMENTATION_STATUS=CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW
M031_IMPLEMENTATION_COMMIT=PENDING
M031_IMPLEMENTATION_OWNER_FREEZE_STATUS=NOT_STARTED
M031_STATUS=IMPLEMENTED_PENDING_INDEPENDENT_REVIEW
NEXT_PERMITTED_ACTION=MILESTONE-031 INDEPENDENT IMPLEMENTATION REVIEW
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

- MILESTONE-031 independent implementation review and owner implementation freeze (an implementation candidate now exists — see Section 18 — not yet reviewed or frozen);
- the symmetric query-side vertical slice (deferred by the frozen M030 scope itself, a separate future milestone);
- retry-on-`OptimisticConcurrencyConflict` policy after a concrete handler exists that saves an existing aggregate;
- APIs, workers, Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or empirical campaign execution behavior.

## 10. Next Authorized Work

MILESTONE-027 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 7). MILESTONE-028 is `APPROVED_AND_FROZEN` at both the design and implementation stages (Section 8): the corrected design (Version 1.1) was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN_FREEZE.md`; the implementation, reviewed with zero CRITICAL, zero MAJOR, and zero blocking MINOR findings, was frozen via `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_FREEZE.md`. MILESTONE-029 is `APPROVED_AND_FROZEN` at the scope stage (Section 11; scope-freeze commit `22cec98d4bd724e00754551034b896236989acec`), at the design stage (design commit `f047d3a33fcd8ba4849a5be1f75abc74c64a362f`, frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md`), and at the implementation stage (implementation commit `5b8a7d8a7e6bcd3852161c8fe0fafff5c7f5f986`, owner-frozen via `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_FREEZE.md` after a final independent implementation re-review found all previously blocking evidence/governance findings resolved). MILESTONE-029 is fully `APPROVED_AND_FROZEN` at every stage (Section 12). MILESTONE-030 scope — Concrete Application Command Vertical Slice (Campaign Creation) — is `APPROVED_AND_FROZEN` (Section 13; scope commit `2b4ac748304d3859b78b6a1900849fab7b6fec35`) after a hostile independent scope review found exactly one architectural capability with no hidden design, implementation, sequencing, or governance defect. MILESTONE-030 has a design candidate — answering all ten required architectural questions (command/handler package placement, dependency injection, entry-point binding, identity supply, validation ownership, repository interaction sequence, error propagation, and the one justified architecture-checker change) — recorded in `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN.md` (Section 14). A hostile independent design review found two MAJOR defects in the architecture-checker decision (a claim that `usecases` needed `shared.persistence` access, contradicting the handler's own Protocol-only dependency design, and a missing `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry required to actually enforce that Protocol-only boundary) and one MINOR governance defect in this document. All three were corrected: the design states the precise dependency model (`CampaignRepository` + `RuntimeIdentifierGenerator` Protocols only, no persistence import anywhere in `usecases`), specifies the required paired `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` checker change, and this document's narrative was realigned. A final independent design delta re-review then independently re-derived and verified the underlying technical claims against the actual `tools/check_architecture.py` source (not merely the design's own assertions) and confirmed no other decision was reopened, concluding: **M030 DESIGN APPROVED FOR OWNER FREEZE.** The owner formally froze the design via `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`. MILESTONE-030 implemented exactly `CreateCampaignCommand`/`CreateCampaignHandler` in `empirical_platform.usecases.create_campaign`, the paired `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` architecture-checker addition, and focused unit/contract/integration/architecture-fixture tests (implementation commit `bb66826225f621368ea317b5757631bf94731a56`). A hostile independent implementation review verified the change scope, prohibited-pattern absence, and test rigor directly against the real commit (not the implementation's own claims), independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container twice, and concluded: **M030 IMPLEMENTATION APPROVED FOR OWNER FREEZE.** The owner formally froze the implementation via `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md`. MILESTONE-030 is now `APPROVED_AND_FROZEN` at every stage — scope, design, and implementation (Section 15). MILESTONE-031 scope — Concrete Application Query Vertical Slice (Campaign Retrieval) — is `APPROVED_AND_FROZEN` (Section 16; scope commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`) after a hostile independent scope review found exactly one coherent read-side capability with no hidden design, implementation, sequencing, or governance defect (two non-blocking governance observations were raised and resolved in this same freeze). MILESTONE-031 design — resolving all ten open design questions the scope freeze deferred (query shape, handler placement, repository dependency, return shape, repository interaction, not-found behavior, validation ownership, `QueryEntryPoint` binding, architecture-checker impact, PostgreSQL evidence strategy), recorded in `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` (design candidate commit `f73b924d3c36e4796087aa4bb889a8dcde7b548e`) — is `APPROVED_AND_FROZEN` (Section 17) after a hostile independent design review found zero CRITICAL and zero MAJOR findings (three non-blocking MINOR findings were raised and resolved in the freeze record). MILESTONE-031 implemented exactly `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` in `empirical_platform.usecases.get_campaign`, with zero `tools/check_architecture.py` change and 23 new focused unit/contract/integration tests (implementation document `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION.md`, Section 18 below). MILESTONE-031 implementation is `CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`, not yet reviewed or frozen. The next authorized action is MILESTONE-031 INDEPENDENT IMPLEMENTATION REVIEW.

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

**Next permitted action:** MILESTONE-030 INDEPENDENT SCOPE REVIEW (see Section 13).

## 13. MILESTONE-030 Scope (APPROVED_AND_FROZEN)

**Scope:** Concrete Application Command Vertical Slice (Campaign Creation) — one concrete command type and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting a new `Campaign` via the frozen M023 `PostgresCampaignRepository.add()`.

**Why this scope:** Every layer of the CQRS/persistence stack (M020-M029) is frozen, but no two adjacent layers have ever been exercised together with a real, concrete operation — every prior milestone validated its Protocol or boundary exclusively against mock/fake handlers. This is the smallest coherent next capability: one narrow, concrete vertical slice proving the entire frozen stack composes correctly for one real write operation, using `Campaign` because it is the only domain aggregate with zero dependency on any other domain aggregate.

**Explicitly out of scope:** the query-side vertical slice, any other Campaign operation, any other aggregate, any composition-root/registry/DI framework, any transport layer, any retry/optimistic-concurrency handling, and any market-data/vendor/trading/execution behavior.

**Scope document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE.md` (commit `2b4ac748304d3859b78b6a1900849fab7b6fec35`).

**Independent review:** A hostile independent scope review, including direct source inspection rather than reliance on the scope document's own claims, found exactly one architectural capability, no hidden design or implementation, no sequencing defect, no bundled capabilities, and no frozen-contract violation. Two non-blocking findings were carried forward for design-phase awareness: `CampaignId`'s governance-value has no frozen generation mechanism (already flagged as an open design question in the scope document), and no currently-allowed package can host a concrete handler needing both the `Campaign` aggregate and `PostgresRepositoryRuntime` without an architecture-checker addition (already narrowly pre-authorized by the scope document's own Scope-Compliance Rules). Decision: **M030 SCOPE APPROVED FOR OWNER FREEZE.**

**Scope freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-030 design is authorized and a candidate now exists (below). MILESTONE-030 implementation is NOT authorized until design is independently reviewed and owner-frozen.

## 14. MILESTONE-030 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN.md` (design candidate commit `6c12c77fdded4d42caaba1f37287dabf2c5c577a`; correction commit `b0dba94927c8067f0d55aa6790bcf71bb82cb0a6`).

**Selected architecture:** a new top-level package `empirical_platform.usecases` (justified against the already-frozen `datasets: {shared, identifiers, campaign}` precedent in `tools/check_architecture.py`), containing one module `usecases/create_campaign.py` with `CreateCampaignCommand` and `CreateCampaignHandler`. The handler receives `CampaignRepository` and `RuntimeIdentifierGenerator` (both already-frozen Protocols) via constructor injection — and imports nothing from `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3` anywhere in the package; `CampaignId` is caller-supplied on the command while `runtime_id` is handler-generated; `CommandEntryPoint` binding happens by direct construction in tests only (no new production composition code); all validation is delegated to the already-frozen `Campaign` aggregate and its value objects; all errors propagate transparently, matching M029's frozen invariant exactly. Exactly one *paired* architecture-checker addition is proposed: `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` together with `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` — both required together, matching the identical paired-rule shape already used by `campaign`, `run`, `evidence`, `review`, and `application`.

**Independent review and correction:** a hostile independent design review found two MAJOR findings (M030-DESIGN-REVIEW-0001, M030-DESIGN-REVIEW-0002) — the design's Design Question 10 originally and incorrectly claimed `usecases` needed direct `shared.persistence` access, contradicting its own Design Question 3 Protocol-only dependency decision, and consequently omitted the `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry needed to actually enforce that boundary — and one MINOR finding (M030-DESIGN-REVIEW-0003) in this document's stale narrative. All three were corrected; no other design decision was reopened.

**Final delta re-review:** a final independent hostile design delta re-review independently re-derived the underlying technical problem by hand-tracing `tools/check_architecture.py`'s actual `imported_top_level()`/`check_path()` logic (not merely trusting the correction's own claims), confirmed both cited precedents (`ALLOWED["datasets"]`, and the identical `FORBIDDEN_IMPORT_PREFIXES` tuples `campaign`/`run`/`evidence`/`review`/`application` already carry) exist exactly as claimed, and confirmed via diff-hunk analysis that no other design decision was disturbed. Decision: **M030 DESIGN APPROVED FOR OWNER FREEZE.**

**Design constraints preserved:** domain purity, all existing Protocols/Repository/EntryPoint/Runtime contracts, all existing PostgreSQL adapters, and existing dependency direction — verified against actual frozen source, not assumed. Concrete persistence and runtime objects are supplied to the handler from outside the `usecases` package (by tests, or by a future, separately scoped composition boundary); `usecases` itself never imports or references `PostgresRepositoryRuntime`, `FoundationRuntime`, or `PostgresCampaignRepository`.

**Prohibited items confirmed absent:** no DI framework, registry, service locator, mediator, transport, HTTP, API, queue, scheduler, market-data/trading logic, event bus, command bus, or generic framework.

**Design freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-030 implementation is now authorized, strictly within the boundaries the freeze record establishes.

**Next permitted action:** MILESTONE-030 INDEPENDENT IMPLEMENTATION REVIEW (see Section 15).

## 15. MILESTONE-030 Implementation (Candidate, Not Yet Approved)

**Implementation document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION.md` (implementation commit `bb66826225f621368ea317b5757631bf94731a56`).

**Implemented:** `CreateCampaignCommand` and `CreateCampaignHandler` in the new `empirical_platform.usecases.create_campaign` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on the `CampaignRepository` and `RuntimeIdentifierGenerator` Protocols via constructor injection; performs the frozen sequential flow (translate command data into frozen value types, obtain `runtime_id` from the injected generator, construct the `Campaign` aggregate, call `CampaignRepository.add()` exactly once, return `DomainIdentity[CampaignId]`); propagates every collaborator failure transparently; and is invocable through the unmodified, frozen `CommandEntryPoint`.

**Architecture-checker change:** exactly the paired addition the design freeze specifies — `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` and `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` — verified both positively (the real implementation passes the full checker) and negatively (7 new fixtures, each triggering exactly one expected violation).

**Tests added:** 14 unit tests (deterministic recording fakes, no mocks), 3 contract tests (Protocol conformance), 3 integration tests against **real PostgreSQL** (a disposable `postgres:17` container via the repository's own `infra/local/compose.yaml`, migrated with the frozen Alembic chain, following the identical opt-in convention `test_m023_postgres_repositories.py` established) proving the golden path and the `AggregateAlreadyExists` failure path end-to-end, plus 7 architecture-checker fixture files and 7 new assertions in `tests/architecture/test_module_boundaries.py`.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 481 passed, 113 skipped, coverage 82.96% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **588 passed**, 6 skipped, coverage **91.87%** |
| Focused M030 tests | PASS — 19 passed |
| Full integration-suite regression check, real PostgreSQL | PASS — 107 passed, 6 skipped |
| Ruff format/check | PASS — 196 files formatted, 0 lint issues |
| mypy strict | PASS — 87 source files (was 85; +2 for `usecases`) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — all 7 new + all pre-existing violations trigger exactly as expected |
| Build | PASS — sdist and wheel built, `usecases` package present in wheel contents |

**Hostile self-audit (executed, not merely asserted):** zero matches anywhere in `src/empirical_platform/usecases/` for `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, handler-level `try`/`except`, `uuid`/`datetime` identity generation, `run_composed`, or any registry/dispatcher/mediator/service-locator/DI-framework pattern. Exactly 7 imports in `create_campaign.py`, exactly one `.add()` call, exactly 2 modules in the `usecases` package.

**No M020-M029 material changed.** No M030 scope/design/freeze document changed. No transport, query-side, composition-root, or MILESTONE-031 work introduced. No database schema or migration change.

**Independent review:** A hostile independent implementation review verified the 16-file change scope directly against the real commit, re-ran a fresh prohibited-pattern grep sweep (zero matches), independently re-derived the checker's necessity for the paired `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` rule, read every test for genuine (non-tautological) rigor, and **independently reproduced the real-PostgreSQL evidence from a completely fresh Docker container and volume, twice** — once for the 3 M030-specific integration tests, once for the full 588-test suite — with results identical both times. One non-blocking observation: the typed-conformance tests' "mypy-checked proof" docstring wording is technically imprecise (test files are outside mypy's configured `packages` scope) but is inherited verbatim from M029's own frozen, already-approved tests, not a new defect. Decision: **M030 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

**Implementation freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_IMPLEMENTATION_FREEZE.md`.

**Review status:** `APPROVED_AND_FROZEN`. MILESTONE-030 is now fully frozen at every stage.

**Next permitted action:** MILESTONE-031 DESIGN MISSION (see Section 16).

## 16. MILESTONE-031 Scope (APPROVED_AND_FROZEN)

**Scope:** Concrete Application Query Vertical Slice (Campaign Retrieval) — one concrete query and one concrete handler conforming to the frozen M028 `QueryHandler` Protocol, invoked through the frozen M029 `QueryEntryPoint`, reading a Campaign via the existing, already-frozen `CampaignRepository.get()` method (M020).

**Why this scope:** M030 proved the write side of the application invocation boundary; the read-side counterpart (`QueryHandler`/`QueryEntryPoint`) has been frozen since M028/M029 but exercised only by mock/fake handlers — a repository-wide search confirms zero concrete query handlers exist anywhere. A Campaign created via M030's slice can currently be read back only by reaching around the application boundary directly. Both M030's own frozen scope document and this checkpoint's prior deferred-capabilities entries explicitly named the query-side vertical slice as the next item.

**Explicitly out of scope:** any `Run`/`EvidencePackage`/`Review` command or query; any Campaign query beyond retrieval-by-identity (no listing/filtering/searching/pagination); any additional Campaign command; any composition-root/registry/dispatcher/caching/read-model/DI framework; any transport layer; any cross-aggregate access; any retry/optimistic-concurrency handling; any market-data/vendor/trading/execution behavior; any MILESTONE-032 work.

**Scope document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE.md` (commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`).

**Independent review:** A hostile independent scope review found exactly one coherent read-side capability, correctly following the frozen M030 write-side slice, with every frozen predecessor contract preserved. Two non-blocking governance observations were raised (a `PENDING` scope-commit placeholder; a stale "not yet started" narrative sentence) — both resolved in this same freeze. Decision: **M031 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Scope freeze document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE_FREEZE.md`.

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-031 design was authorized and a candidate now exists (see Section 17). MILESTONE-031 implementation is NOT authorized until design is independently reviewed and owner-frozen.

**Next permitted action:** see Section 17.

## 17. MILESTONE-031 Design (APPROVED_AND_FROZEN)

**Design document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` (design candidate commit `f73b924d3c36e4796087aa4bb889a8dcde7b548e`).

**Selected architecture:** one concrete query, `GetCampaignQuery` (single field: `identity: DomainIdentity[CampaignId]`), and one concrete handler, `GetCampaignHandler`, both in a new module `usecases/get_campaign.py` alongside M030's `create_campaign.py`. The handler depends on `CampaignRepository` only via constructor injection (no `RuntimeIdentifierGenerator` — nothing is generated on a read); calls `CampaignRepository.get()` exactly once; and returns a new narrow immutable read value, `CampaignSnapshot` (`identity`, `scope_statement`, `state` — deliberately excluding `persisted_version`), rather than the raw mutable `Campaign` aggregate or the write-metadata-bearing `LoadedAggregate[Campaign]`, to avoid aggregate-mutation leakage and write-side metadata leakage through the read boundary. `AggregateNotFound` and any other repository exception propagate transparently, matching M029's frozen invariant and M030's own precedent. `QueryEntryPoint(GetCampaignHandler(...))` binding is demonstrated by direct construction in tests only, exactly matching M030. No architecture-checker change is required: every needed import (`campaign`, `identifiers`, `shared`) is already covered by M030's existing `ALLOWED["usecases"]` grant.

**Return-shape decision (the design's hardest question):** four options were formally evaluated — (A) return `Campaign` directly, rejected for aggregate-mutability leakage; (B) return `LoadedAggregate[Campaign]` directly, rejected for the same leakage plus exposing write-side `persisted_version` through a read-only boundary; (C) a new narrow immutable read value, selected; (D) another existing frozen type, rejected as no candidate carries exactly `identity + scope_statement + state`. The selection is justified by direct precedent: M030's own `CreateCampaignHandler.handle()` already declined to return the raw `SaveResult`, returning only `campaign.identity` — establishing this project's discipline of extracting the minimal useful slice rather than passing through the underlying repository/contract type verbatim.

**Prohibited items confirmed absent:** no listing/filtering/pagination/sorting, no caching, no generic read-model framework, no hidden DTO/serialization layer, no query registry/dispatcher/mediator/service locator, no DI framework, no composition-root code, no infrastructure import in `usecases`, no not-found translation, no runtime-ID regeneration, no MILESTONE-032 work.

**Hostile self-audit:** performed against the mission's full attack list (unresolved return type, aggregate leakage, accidental read-model framework, hidden DTO layer, governance-ID-only lookup, runtime-ID regeneration, extra repository calls, loss of revision metadata, unauthorized not-found translation, registry/dispatcher leakage, infrastructure dependency, production composition leakage, architecture-checker mismatch, M032 leakage) — no issue survived requiring correction; the one deliberate omission (`persisted_version`) is explicitly justified, not silently dropped.

**Independent review:** A hostile independent design review verified every load-bearing decision directly against actual frozen source (not the design's own claims) — identity semantics, the four-option return-shape evaluation, repository interaction, not-found/error behavior, revision-metadata treatment, and architecture-checker impact — and found zero CRITICAL and zero MAJOR findings. Three non-blocking MINOR findings were raised (an imprecise field-justification sentence in Section 9; an unresolved "or" in the Section 17.F integration-test seed mechanism; incomplete numeric labeling of the ten design questions) and resolved in the design-freeze record without modifying the frozen design document. Decision: **M031 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.**

**Design freeze document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN_FREEZE.md` (freeze commit `196150dcde88610c9bc78e6bd0ff40d4d5da9d9b`).

**Status:** `APPROVED_AND_FROZEN`. MILESTONE-031 implementation was authorized and a candidate now exists (see Section 18).

**Next permitted action:** see Section 18.

## 18. MILESTONE-031 Implementation (Candidate, Not Yet Approved)

**Implementation document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_IMPLEMENTATION.md` (implementation commit `PENDING` — recorded via a narrow follow-up commit once the candidate commit exists; see Section 1's self-reference note).

**Implemented:** `GetCampaignQuery`, `CampaignSnapshot`, and `GetCampaignHandler` in the new `empirical_platform.usecases.get_campaign` module — exactly the vertical slice the frozen design specifies, with no deviation. The handler depends only on the `CampaignRepository` Protocol via constructor injection; performs the frozen sequential flow (read `query.identity` unchanged, call `CampaignRepository.get()` exactly once, build `CampaignSnapshot` from the loaded aggregate's `identity`/`scope_statement`/`state`, intentionally discarding `persisted_version`); propagates every collaborator failure transparently (no `try`/`except` anywhere in the module); and is invocable through the unmodified, frozen `QueryEntryPoint`.

**Architecture-checker change:** none, exactly as the design freeze predicted. Verified both positively (the real source tree, now including `get_campaign.py`, passes the unmodified checker with 0 violations) and negatively (all 7 pre-existing `usecases`-scoped illegal-import fixtures from M030 still trigger without modification — no new fixture was added, since none was needed).

**Tests added:** 17 unit tests (deterministic recording/failing fakes, no mocks), 3 contract tests (Protocol conformance), 3 integration tests against **real PostgreSQL** (a disposable `postgres:17` container, following the identical opt-in convention `test_m030_create_campaign_usecase.py` established) proving the golden path (retrieval of a Campaign created via the frozen M030 slice) and the `AggregateNotFound` failure path end-to-end.

**Validation gates (fresh run against the implementation):**

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — 500 passed, 116 skipped, coverage 83.07% |
| Full `pytest` suite, **real PostgreSQL** | PASS — **610 passed**, 6 skipped, coverage **91.92%** |
| Focused M031 tests (unit + contract) | PASS — 19 passed |
| Focused M031 PostgreSQL integration | PASS — 3 passed |
| Full integration-suite regression check, real PostgreSQL | PASS — 110 passed, 6 skipped |
| Ruff format/check | PASS — 200 files formatted, 0 lint issues |
| mypy strict | PASS — 88 source files (was 87; +1 for `get_campaign.py`) |
| Architecture checker (full repo) | PASS — 0 violations |
| Architecture checker (fixtures) | PASS — all pre-existing `usecases` violations trigger exactly as before, unmodified |
| Build | PASS — sdist and wheel built, `get_campaign.py` present in wheel contents |
| Security — pip-audit | PASS — no known vulnerabilities |
| Security — secret scan targets | PASS — 344 targets discovered |

**Hostile self-audit (executed, not merely asserted):** zero matches anywhere in `src/empirical_platform/usecases/get_campaign.py` for `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `run_composed`, registry/dispatcher/mediator/service-locator patterns, `async`, `uuid`/`datetime` identity generation, or any listing/filtering/pagination/caching/transport keyword. Exactly 5 imports, exactly one `.get(` call, exactly 45 lines.

**No M020-M030 material changed.** No M031 scope/design/freeze document changed. No transport, composition-root, or MILESTONE-032 work introduced. No database schema or migration change.

**Review status:** `CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`. Not approved. Not frozen.

**Next permitted action:** MILESTONE-031 INDEPENDENT IMPLEMENTATION REVIEW.
