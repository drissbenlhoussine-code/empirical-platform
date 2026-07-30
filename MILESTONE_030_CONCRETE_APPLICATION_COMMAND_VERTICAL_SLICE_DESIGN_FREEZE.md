# MILESTONE-030 - Concrete Application Command Vertical Slice Design Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-030 design following a hostile independent design review, a required correction pass, and a final hostile independent design delta re-review. It authorizes MILESTONE-030 implementation to begin, strictly within the boundaries this record freezes. It does not itself implement anything.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `c741162d23f6431c2306f7e60e28e61a541b361a` |
| Milestone | MILESTONE-030 |

---

## 3. Frozen Predecessor Chain

M020-M029 are `APPROVED_AND_FROZEN` at every stage (scope, design, implementation where applicable). This freeze changes nothing about their frozen status. None of their source files, contracts, or governance documents were touched at any point during M030 scope selection, design, design correction, or this freeze.

---

## 4. M030 Frozen Scope Authority

**Scope:** Concrete Application Command Vertical Slice (Campaign Creation).

**Scope document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE.md` (commit `2b4ac748304d3859b78b6a1900849fab7b6fec35`).

**Scope freeze document:** `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE_FREEZE.md` (commit `52f07c03195926e4f3a67dc1524aba7c206a09cb`).

**Scope status:** `APPROVED_AND_FROZEN`, unchanged and untouched throughout the entire design phase.

---

## 5. Original Design Candidate Commit

**Commit:** `6c12c77fdded4d42caaba1f37287dabf2c5c577a` (`docs: define M030 design candidate`)

Answered all ten required architectural questions with justification and documented alternatives.

---

## 6. Hostile Design-Review Decision (First Pass)

**Decision: M030 DESIGN REQUIRES REVISION**

Two MAJOR findings and one MINOR finding:

- **M030-DESIGN-REVIEW-0001 (MAJOR):** the original design's Design Question 10 claimed `usecases` "needs to import `shared.persistence`," directly contradicting the handler's own Design Question 3 Protocol-only dependency decision.
- **M030-DESIGN-REVIEW-0002 (MAJOR):** the design's proposed architecture-checker change (`ALLOWED["usecases"]` alone, with no `FORBIDDEN_IMPORT_PREFIXES` entry) could not enforce the very prohibitions its own fixture matrix claimed to prove.
- **M030-DESIGN-REVIEW-0003 (MINOR):** `PROJECT_CHECKPOINT.md` contained stale narrative describing scope review as the next action after a design candidate already existed.

---

## 7. Design Correction Commit

**Commit:** `b0dba94927c8067f0d55aa6790bcf71bb82cb0a6` (`docs: correct M030 usecase dependency design`)

**Hash-recording commit:** `c741162d23f6431c2306f7e60e28e61a541b361a` (`docs: record M030 design correction commit`)

**Correction scope:** exactly two files (`MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN.md`, `PROJECT_CHECKPOINT.md`), verified via `git diff --stat` across the full commit range — no source, test, or `tools/check_architecture.py` file was touched at any point during the correction.

**Resolution:**

1. Withdrew the false claim that `usecases` needs `shared.persistence` access; stated the precise dependency model:
   ```
   CreateCampaignHandler
       -> CampaignRepository Protocol          (empirical_platform.campaign.repository)
       -> RuntimeIdentifierGenerator Protocol  (empirical_platform.shared.identifiers)
       -> Campaign aggregate and domain value types
   ```
2. Specified the required paired architecture-checker change: `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` together with `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")`, and realigned the proposed fixture matrix to match.
3. Realigned `PROJECT_CHECKPOINT.md`'s narrative (Sections 9, 10, 14) to the current state, preserving every historically accurate statement about M020-M029 and the M030 scope stage unchanged.

No other design decision was reopened.

---

## 8. Final Delta Re-Review Decision

**Decision: M030 DESIGN APPROVED FOR OWNER FREEZE**

The final hostile independent design delta re-review did not take the correction's own claims on faith. It independently re-derived the underlying technical problem by hand-tracing `tools/check_architecture.py`'s `imported_top_level()` / `check_path()` logic for both `import sqlalchemy` and `from empirical_platform.shared.persistence import X` inside a hypothetical `usecases` module, confirming the original gap was real (not hypothetical) and that the corrected paired rule closes it. It independently verified the cited precedents (`ALLOWED["datasets"]`, and the identical `FORBIDDEN_IMPORT_PREFIXES` tuples already carried by `campaign`, `run`, `evidence`, `review`, `application`) exist byte-for-byte as claimed. It confirmed via diff-hunk analysis that zero changes touched Sections 2-13 of the design document (Design Questions 1-9), meaning no previously-accepted decision was disturbed. It confirmed `PROJECT_CHECKPOINT.md`'s historical statements about M020-M029 and the M030 scope stage remained byte-identical. It found no residual contradiction anywhere in the corrected document.

---

## 9. Owner Approval

I, the owner, declare the MILESTONE-030 design, as corrected at commit `b0dba94927c8067f0d55aa6790bcf71bb82cb0a6` and recorded at HEAD `c741162d23f6431c2306f7e60e28e61a541b361a`, **APPROVED AND FROZEN** effective immediately upon this record.

**M030 DESIGN APPROVED_AND_FROZEN**

No further change to the frozen design is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 10. Final Frozen Architectural Decisions

### A. Vertical Slice

- Exactly one concrete command: `CreateCampaignCommand`.
- Exactly one concrete handler: `CreateCampaignHandler`.
- Both belong to: `empirical_platform.usecases.create_campaign`.
- No additional use case is authorized by this freeze.

### B. Handler Dependencies

`CreateCampaignHandler` depends only on:

- `CampaignRepository` Protocol (`empirical_platform.campaign.repository`).
- `RuntimeIdentifierGenerator` Protocol (`empirical_platform.shared.identifiers`).
- The `Campaign` aggregate and frozen domain/value types (`CampaignScopeStatement`, `CampaignId`, `DomainIdentity`).

Constructor injection is the frozen dependency-acquisition mechanism.

### C. Infrastructure Prohibition

The `usecases` package and `CreateCampaignHandler` must not directly import or depend on:

- `empirical_platform.shared.persistence` (any submodule).
- `PostgresRepositoryRuntime`.
- `FoundationRuntime`.
- `PostgresCampaignRepository`.
- `sqlalchemy`.
- `psycopg`.
- `boto3`.
- Database sessions, engines, or connections.
- Transaction factories.
- Unit-of-work objects.
- Any infrastructure adapter.

Concrete collaborators (a `CampaignRepository`-conforming object, a `RuntimeIdentifierGenerator`-conforming object) are supplied to the handler's constructor from outside the `usecases` package — by tests in this milestone. **No production composition root is authorized by M030.**

### D. Identity Ownership

- `CampaignId` remains caller-supplied on the command.
- `runtime_id` remains produced by the injected `RuntimeIdentifierGenerator`.
- No handler-generated `CampaignId`.
- No new identity-allocation policy of any kind.

### E. Domain Ownership

- All business-rule validation remains inside the already-frozen `Campaign` aggregate and its value objects (`CampaignScopeStatement`, `CampaignId`, `Identifier`).
- The handler performs orchestration and translation only — constructing value objects from raw command fields, constructing the aggregate, calling the repository, returning the result.
- No duplicated aggregate validation inside the handler or the command.
- No new business rules of any kind.

### F. Persistence Flow

The frozen sequence:

```
1. handler.handle(command) receives CreateCampaignCommand
2. campaign_id = CampaignId(command.campaign_governance_id)
3. runtime_id = self._runtime_identifier_generator.generate()
4. identity = DomainIdentity(governance_id=campaign_id, runtime_id=runtime_id)
5. scope_statement = CampaignScopeStatement(command.scope_statement)
6. campaign = Campaign(identity=identity, scope_statement=scope_statement)
7. self._campaign_repository.add(campaign)   # exactly one repository call
8. return campaign.identity                  # DomainIdentity[CampaignId]
```

Explicitly excluded: `update`, `get`-as-a-command, `delete`, any query, any retry policy, any transaction orchestration by the handler, any `run_composed()` usage, any multi-repository workflow.

### G. Error Propagation

- Fully transparent propagation is frozen: the handler contains zero `try`/`except` blocks.
- No wrapping, translation, or error-envelope framework of any kind.
- Every exception (`ValueError`/`TypeError` from value-object construction, `AggregateAlreadyExists`/`InvalidAggregateForPersistence` from the repository) propagates unchanged through the handler and the frozen `CommandEntryPoint`.

### H. Entry-Point Binding

- The frozen M029 `CommandEntryPoint[CommandT, ResultT]` is used exactly as it exists today — unmodified.
- Direct construction/binding (`CommandEntryPoint(CreateCampaignHandler(...))`) is permitted, and only demonstrated, in tests.
- No production registry, command bus, mediator, dispatcher, service locator, or dependency-injection framework is authorized.

### I. Architecture Checker

Implementation may add only:

- `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` — the narrow first-party allowlist justified by the actual imports this milestone needs.
- `FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` — required together with the above, matching the identical paired-rule shape `campaign`, `run`, `evidence`, `review`, and `application` already carry.
- Corresponding focused checker fixtures (accepted: `CampaignRepository`/identifier-type imports and other explicitly justified first-party imports actually used; rejected: `shared.persistence`, concrete Postgres modules, `sqlalchemy`, `psycopg`, `boto3`, unrelated domain aggregates/infrastructure packages; reconfirmed: `campaign` still cannot import `usecases`, full existing source tree still passes unmodified).

No broader package grant is authorized. Implementation must use the repository's actual `tools/check_architecture.py` syntax and conventions (`ALLOWED`, `FORBIDDEN_IMPORT_PREFIXES`, `ALLOWED_EXACT_IMPORTS` as applicable) exactly as they exist at implementation time — this freeze does not prescribe checker implementation code.

---

## 11. Implementation Authorization Boundary

The future MILESTONE-030 implementation mission may implement **only** what Section 10 above explicitly freezes. This freeze record does not itself authorize any file modification — the implementation mission must independently verify exact paths and predecessor contracts before editing, exactly as every prior implementation mission in this project has done.

**Files an implementation mission may justifiably touch, narrowly:**

- The new `usecases` package/module (`src/empirical_platform/usecases/__init__.py`, `src/empirical_platform/usecases/create_campaign.py`).
- Focused unit tests (handler behavior against a fake `CampaignRepository`).
- Focused contract tests (`CommandHandler` Protocol conformance).
- Focused integration tests (golden path and `AggregateAlreadyExists` against real PostgreSQL, via a directly-constructed `CommandEntryPoint`).
- The minimum architecture-checker rule addition (Section 10.I) and its accompanying fixtures.
- `PROJECT_CHECKPOINT.md` and an implementation-evidence governance document.

**Explicitly prohibited, regardless of implementation-phase convenience:**

- Speculative abstractions of any kind.
- Generic base handler classes.
- Command registries.
- Command buses.
- Mediator frameworks.
- Production composition roots.
- New persistence contracts or modifications to existing ones.
- Modifications to any frozen Protocol signature (`CommandHandler`, `QueryHandler`, `CampaignRepository`, etc.).
- Transport or API layers of any kind.
- Any query-side behavior.
- Any MILESTONE-031 work.

---

## 12. Deferred Capabilities

Unchanged from the frozen scope document:

- The symmetric query-side vertical slice — a separate future milestone.
- Any composition-root abstraction beyond direct binding, if repeated concrete handlers later reveal a genuine need for one.
- Retry-on-`OptimisticConcurrencyConflict` policy (requires a `save()`-based handler, which this milestone does not include).
- Any transport/entrypoint adapter.
- All `Run`, `EvidencePackage`, and `Review` commands and queries.
- All market-data, vendor, trading, and campaign-execution business behavior.
- MILESTONE-031 and beyond.

---

## 13. Governance Status

```
M030_SCOPE_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_STATUS=APPROVED_AND_FROZEN
M030_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M030_IMPLEMENTATION_STATUS=NOT_STARTED
M030_STATUS=DESIGN_APPROVED_AND_FROZEN
```

---

## 14. Next Permitted Action

**MILESTONE-030 IMPLEMENTATION MISSION.**

This freeze record does NOT authorize:

- Any file modification by itself.
- Any MILESTONE-031 work.
- Any expansion of the frozen boundaries in Section 10 without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 15. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-030 DESIGN FREEZE COMPLETE

═══════════════════════════════════════════════════════════════════════════════

M030 CONCRETE APPLICATION COMMAND VERTICAL SLICE (CAMPAIGN CREATION)

Scope:                           APPROVED_AND_FROZEN
Design:                          APPROVED_AND_FROZEN
Design Freeze:                   APPROVED_AND_FROZEN
Implementation:                  NOT_STARTED

Original Design Candidate:       6c12c77fdded4d42caaba1f37287dabf2c5c577a
Design Correction:                b0dba94927c8067f0d55aa6790bcf71bb82cb0a6
Correction Hash-Recording:        c741162d23f6431c2306f7e60e28e61a541b361a
Design Freeze Commit:             (recorded in a following governance commit)

M020-M029:                        UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M031:                             NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-030 IMPLEMENTATION MISSION

═══════════════════════════════════════════════════════════════════════════════
```
