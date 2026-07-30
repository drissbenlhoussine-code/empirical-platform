# MILESTONE-030 - Concrete Application Command Vertical Slice Design

## 1. Document Status

**Status: CANDIDATE_FOR_FINAL_INDEPENDENT_DESIGN_RE_REVIEW**

This document is a design candidate. It has not been reviewed, approved, or frozen. No implementation of MILESTONE-030 is authorized by this document.

A hostile independent design review of the prior version of this document found two MAJOR defects (M030-DESIGN-REVIEW-0001, M030-DESIGN-REVIEW-0002, both in Design Question 10's architecture-checker decision) and one MINOR governance defect (M030-DESIGN-REVIEW-0003, in `PROJECT_CHECKPOINT.md`, corrected separately). Both MAJOR defects are corrected in this revision — see Section 14 and Section 15's "Corrected Dependency Model" subsection, and the Final Status block (Section 21) for a summary. No other design decision was reopened.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at design | `3c35f9bcef4b57aee965b857564162b4045502da` |
| Frozen scope commit | `2b4ac748304d3859b78b6a1900849fab7b6fec35` |
| Scope freeze commit | `52f07c03195926e4f3a67dc1524aba7c206a09cb` |
| Milestone | MILESTONE-030 |

---

## 3. Frozen Predecessor Chain

M020-M029 are `APPROVED_AND_FROZEN`. M030 scope (`MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE.md`) is `APPROVED_AND_FROZEN`. This design operates strictly within that frozen scope's boundaries (Sections 8-9 of the scope document) and answers only the open design questions the scope identified (Section 13 of the scope document), without reopening any M020-M029 decision.

---

## 4. Architectural Context (Recap)

**Scope:** One concrete command type + one concrete handler, conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting a new `Campaign` via the frozen M023 `PostgresCampaignRepository.add()`.

**What this design must resolve:** the ten design questions the owner mission specified, each answered here with justification, alternatives, and a selected option. Nothing here reopens a frozen M020-M029 decision; nothing here proceeds to implementation.

---

## 5. Design Question 1: Where should the concrete command live?

### Decision

The concrete command type lives in a **new top-level package**, `empirical_platform.usecases`.

### Justification

A repository-wide inspection of `tools/check_architecture.py` shows that **no existing package can legally host it**:

- `campaign` (the domain package) is forbidden from importing `empirical_platform.shared.persistence` (`FORBIDDEN_IMPORT_PREFIXES["campaign"]`). Placing a persistence-touching command/handler pair inside `campaign` would require weakening that forbidden-import rule, which exists specifically to keep the domain package persistence-ignorant. That would violate the mission's explicit "Domain purity" preservation constraint.
- `application` (M029's boundary) is *also* forbidden from importing `shared.persistence` (`FORBIDDEN_IMPORT_PREFIXES["application"]`). Placing the command/handler there would weaken M029's own frozen, already-implemented, already-tested purity guarantee — reopening a frozen decision, which this design must not do.
- `shared` (outside `shared/domain/*`) is technically unrestricted and could host it without any checker change, but this is architecturally poor: `shared` is a foundational, cross-cutting utility layer that every domain package depends on; placing Campaign-specific business orchestration there inverts the intended dependency direction and does not scale to future use cases without repeatedly overloading `shared`.

A new top-level package is therefore necessary, not merely convenient. This exactly matches what the frozen scope document's Scope-Compliance Rules (Section 15) already narrowly pre-authorized: "one narrowly-scoped architecture-checker addition for wherever the concrete command/handler package lives."

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Inside `campaign/` | No new package; co-located with the aggregate it serves | Requires weakening `campaign`'s frozen persistence-forbidding rule | Violates domain purity constraint |
| Inside `application/` | Co-located with `CommandEntryPoint` | Requires weakening M029's frozen persistence-forbidding rule | Reopens a frozen M029 decision |
| Inside `shared/` (non-domain) | Zero checker change needed today | Inverts dependency direction; foundational layer accumulating business logic; does not scale | Architecturally unsound long-term, even though technically legal today |
| New per-aggregate package (e.g. `campaign_usecases`) | Maximal isolation per aggregate | Repeats the same checker addition per aggregate as each future aggregate gets its own command; fragments a single cross-cutting concern (application orchestration) across many packages | Unnecessary fragmentation for a concern (use-case orchestration) that is inherently cross-aggregate, not aggregate-specific |
| **New generic package `usecases`** | One checker addition serves all future concrete commands across all aggregates; keeps domain and application boundaries pure; precedent already exists for a non-domain package importing a domain package | Introduces one new top-level package | **Selected** |

### Precedent Cited

`tools/check_architecture.py`'s existing, already-frozen `ALLOWED["datasets"] = {"shared", "identifiers", "campaign"}` is the *exact same pattern* being proposed here: a non-domain, non-`shared` package importing both `shared` and a domain package (`campaign`). This is not a novel pattern; it is the established, already-approved shape of dependency this repository already uses.

---

## 6. Design Question 2: Where should the concrete handler live?

### Decision

In the same `usecases` package as its command, in the same module file — one file per use case: `src/empirical_platform/usecases/create_campaign.py`, containing both `CreateCampaignCommand` and `CreateCampaignHandler`.

### Justification

M027 and M028 each froze their Protocol in a single small file (`command.py`, `query.py`) — a "one cohesive unit per file" precedent already established in this repository. A command and its one-and-only handler (M027's Protocol is a strict 1:1 pairing: one command type, one handler, one result type) are exactly such a cohesive unit; splitting them into separate files or separate packages would add indirection without benefit, since neither is ever used without the other.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Command and handler in separate files (`commands/create_campaign.py`, `handlers/create_campaign_handler.py`) | Mirrors some external CQRS frameworks' folder conventions | Splits one cohesive unit across two files/subpackages for no benefit this repository's own precedent doesn't already reject | Adds indirection with no evidenced advantage |
| Command and handler in separate top-level packages | Maximal separation | Two checker-package additions instead of one; commands and handlers are never independently reusable in this Protocol's design | Unjustified duplication of the Design Question 1 decision |
| **Co-located in one file per use case, within `usecases`** | Matches M027/M028's file-per-cohesive-unit precedent; minimal indirection; trivially discoverable | None material | **Selected** |

---

## 7. Design Question 3: How should the handler obtain repository dependencies?

### Decision

**Constructor injection**, at the narrowest necessary Protocol level: the handler's `__init__` accepts a `campaign_repository: CampaignRepository` (the M020 frozen, persistence-neutral Protocol — not the concrete `PostgresCampaignRepository`, not the broader `PostgresRepositoryRuntime`) and a `runtime_identifier_generator: RuntimeIdentifierGenerator` (the M026-available frozen Protocol for generating the aggregate's `runtime_id`).

### Justification

- **Method-parameter injection is architecturally impossible without violating a frozen contract.** M027's `CommandHandler` Protocol freezes `handle(self, command) -> result` as a single-parameter method. A handler cannot receive its runtime dependency as a second `handle()` parameter without breaking Protocol conformance, which this design must not do.
- **Global/module-level singleton state** is not used anywhere else in this codebase (every existing repository/service class receives its dependencies via `__init__`) and is explicitly disfavored for testability reasons; introducing it here would be inconsistent with the entire codebase's established style.
- **Service locator / registry lookup** is explicitly prohibited by the design mission's constraints.
- Constructor injection is the pattern used by every other concrete class in this codebase that needs a collaborator: `PostgresCampaignRepository.__init__(self, service, mapper=None)`, `PostgresRepositoryRuntime.__init__(self, service)`. This design follows that exact precedent.

**Why the narrow Protocol (`CampaignRepository`), not the broad concrete runtime (`PostgresRepositoryRuntime`):** injecting the full `PostgresRepositoryRuntime` would couple the handler to a concrete PostgreSQL-specific class and to three repository properties (`runs`, `evidence_packages`, `reviews`) the handler never uses. Injecting only the `CampaignRepository` Protocol keeps the handler persistence-neutral (any conforming fake/mock satisfies it for unit tests, matching M020's Protocol's entire purpose) and testable without a real database. The caller (test, or future composition code) supplies `foundation_runtime.repository_runtime.campaigns` — which already conforms to `CampaignRepository` — at construction time.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| `handle(self, command, runtime)` (method-parameter injection) | Simple to write | Breaks the frozen `CommandHandler` Protocol's single-parameter signature | Architecturally impossible without violating a frozen contract |
| Global singleton runtime | No constructor parameters needed | Hidden state; inconsistent with the rest of the codebase; hostile to test isolation | Contradicts established codebase style |
| Service locator inside `handle()` | Decouples construction from use | Explicitly prohibited by the design mission | Hard constraint violation |
| Constructor injection of the full `PostgresRepositoryRuntime` | One dependency object instead of two | Couples handler to concrete Postgres class and three unused repository properties; weakens persistence-neutrality | Broader coupling than necessary |
| **Constructor injection of `CampaignRepository` Protocol + `RuntimeIdentifierGenerator` Protocol** | Matches codebase-wide constructor-injection convention; narrowest necessary coupling; fully testable with fakes; both dependencies are already-frozen Protocols | Two constructor parameters instead of one | **Selected** |

---

## 8. Design Question 4: How should `CommandEntryPoint` be bound?

### Decision

**Direct construction, at the call site — in tests only, not in any new production composition module.** `CommandEntryPoint(CreateCampaignHandler(campaign_repository=..., runtime_identifier_generator=...))`, exactly matching the binding pattern M029's own frozen design already illustrates (a handler instance passed directly to the entry point's constructor).

### Justification

The frozen M030 scope explicitly excludes "any composition-root abstraction... beyond direct binding" (Scope Section 9) and defers "any composition-root abstraction beyond direct binding" to a future milestone (Scope Section 17, Deferred Capabilities) — only "if repeated concrete handlers later reveal a genuine need for one." With exactly one concrete handler existing after this milestone, no such need is yet evidenced. Introducing a production composition module now would be exactly the kind of premature abstraction the design mission's constraints prohibit ("Do NOT introduce... generic framework").

The scope document's own acceptance boundary requires only that "the handler is invoked through a `CommandEntryPoint` bound to it (not called directly)" be *proven* — which contract and integration tests do directly, the same way M029's own frozen test suite proves `CommandEntryPoint`'s behavior without any production composition code existing anywhere in `src/`.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| New production composition/factory function (e.g., a `bind_create_campaign()` helper in `usecases`) | Gives production code a named, reusable binding point | Introduces a composition abstraction the scope explicitly defers; couples `usecases` to `application` for no proven need yet | Premature; contradicts frozen scope's explicit deferral |
| A `FoundationRuntime` field exposing a pre-bound `CommandEntryPoint` | Convenient for a hypothetical future caller | No caller exists yet (no transport, no MILESTONE-031); would require modifying the frozen `FoundationRuntime` dataclass | Modifies a frozen M026 contract for a need this scope doesn't establish |
| **Direct `CommandEntryPoint(handler)` construction in tests only** | Zero new production code; matches M029's own established test pattern; proves the acceptance boundary exactly as required | None material within this scope | **Selected** |

---

## 9. Design Question 5: How is `CampaignId` supplied?

### Decision

**Caller-supplied, as a raw string field on the command.** The command carries `campaign_governance_id: str` (e.g., `"CAMP-0042"`); the handler wraps it as `CampaignId(command.campaign_governance_id)` before constructing the aggregate's identity. The aggregate's `runtime_id` half of `DomainIdentity` is generated by the handler via the injected `RuntimeIdentifierGenerator.generate()` — a different mechanism for a different identifier, by design.

### Justification

A direct search of every existing test and fixture in this repository (`tests/contract/`, `tests/integration/`) shows `CampaignId` values are **always** hardcoded, caller-supplied literals (e.g., `CampaignId("CAMP-0001")`) — there is no frozen generation mechanism for the governance identifier anywhere in the codebase, and inventing one now would be inventing a new business rule (a numbering/allocation policy), which the frozen scope's Non-Goals explicitly forbid ("this milestone adds no new business rule").

The `runtime_id` is architecturally different: `RuntimeIdentifier` is explicitly documented as "carrying no domain meaning" and already has a frozen generation Protocol (`RuntimeIdentifierGenerator`, used throughout `FoundationRuntime`). Reusing it for `runtime_id` — and only `runtime_id` — is consistent with its frozen purpose; attempting to reuse it for the governance `CampaignId` is not possible, since `RuntimeIdentifier` and `CampaignId` are distinct, incompatible value-object types (the former is a UUIDv4; the latter matches `^CAMP-\d{4}$`).

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Handler invents a new sequential/allocation scheme for `CampaignId` | No caller burden | Invents new, unfrozen business logic (numbering policy, uniqueness pre-check strategy); duplicates what the database's `uq_campaign_governance_id` constraint already enforces at persistence time | Violates the scope's "no new business rule" non-goal; scope creep into business-domain territory |
| Repurpose `RuntimeIdentifierGenerator` for `CampaignId` | One generation mechanism for both identifiers | Type-incompatible: `RuntimeIdentifierGenerator.generate()` returns `RuntimeIdentifier` (UUIDv4), not `CampaignId` (`CAMP-\d{4}`); would require modifying a frozen type | Architecturally impossible without violating a frozen contract |
| **Caller-supplied `CampaignId` string on the command; handler-generated `runtime_id` via the frozen `RuntimeIdentifierGenerator`** | Matches 100% of existing repository precedent for `CampaignId`; correctly uses the frozen generator for the identifier it was actually designed to generate; introduces no new business rule | Caller (test, or future business layer) must supply a well-formed governance ID string | **Selected** |

---

## 10. Design Question 6: What belongs inside the handler versus the aggregate?

### Decision

**The aggregate and its value objects own all business-rule validation, exactly as already frozen and unmodified. The handler owns only translation and orchestration** — converting raw command fields into the value objects `Campaign.__init__` requires, constructing the aggregate, calling the repository, and returning the result. The handler contains zero new validation logic.

### Justification

`Campaign.__init__` already validates `identity` type-correctness and `scope_statement` type-correctness (`isinstance` checks). `CampaignScopeStatement.__post_init__` already validates non-emptiness. `Identifier.__post_init__` (the `CampaignId` base class) already validates format via regex. Every business rule this vertical slice needs already exists, frozen, in M020. Reimplementing or duplicating any of this validation inside the handler would create two sources of truth that could drift out of sync — a correctness risk this design must avoid, and duplicative work the scope's Non-Goals already forbid.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Handler re-validates scope statement non-emptiness before constructing the value object | "Fails fast" with a handler-specific error message | Duplicates `CampaignScopeStatement.__post_init__`'s existing check; two sources of truth | Unnecessary duplication; the aggregate's own `__post_init__` already fails exactly as fast |
| Handler validates `CampaignId` format before wrapping | Avoids a `ValueError` from inside `Identifier.__post_init__` | Duplicates already-frozen regex validation | Same as above |
| **Handler performs zero validation; delegates entirely to the aggregate and its value objects** | No duplication; single source of truth for every business rule; matches the scope's own Non-Goals | None material | **Selected** |

---

## 11. Design Question 7: What validation belongs outside the aggregate?

### Decision

**None.** This question is answered by Design Question 6: no validation belongs outside the aggregate and its already-frozen value objects. The command type itself is an unvalidated data carrier (a `@dataclass(frozen=True, slots=True)` with two `str` fields), and the handler performs no validation of its own — it only translates and orchestrates.

### Justification

Introducing any command-level or handler-level validation beyond what `Campaign.__init__`, `CampaignScopeStatement`, and `CampaignId` already enforce would be new business logic this milestone's scope explicitly forbids. The command type's own construction is intentionally permissive (any two strings), deferring all rejection to the already-frozen, already-tested value objects the handler constructs from them.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Command performs its own `__post_init__` validation (e.g., non-empty checks) | Slightly earlier failure, before the handler runs | Duplicates checks the value objects already perform; the command's own validation would need to be kept in sync with the aggregate's forever | Unnecessary duplication, same reasoning as Design Question 6 |
| **Command is an unvalidated data carrier; all validation happens in already-frozen value objects the handler constructs** | Single source of truth; zero new business rules; simplest possible command shape | None material | **Selected** |

---

## 12. Design Question 8: What repository interaction sequence is required?

### Decision

A single, sequential, non-transactional-at-the-handler-level flow:

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

### Justification

`PostgresCampaignRepository.add()` already opens and commits its own `unit_of_work()` internally (verified directly in `src/empirical_platform/shared/persistence/postgres_repositories/campaign_repository.py`). The handler does not need to open any transaction itself, and does not need `run_composed()` — that primitive exists for *multi*-repository atomic operations, and this handler touches exactly one repository, exactly once. This matches and confirms the frozen scope's own exclusion of `run_composed()` for this milestone.

Returning `campaign.identity` (the full `DomainIdentity[CampaignId]`, not just the bare `CampaignId`) is deliberate: `CampaignRepository.get()` requires the *full* `DomainIdentity[CampaignId]` to retrieve a Campaign later, so returning only the governance half would strand the caller without enough information to look the Campaign back up — undermining the very "prove the stack works end-to-end" purpose of this vertical slice.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Handler wraps the repository call in its own transaction | Explicit, visible transaction boundary in application code | Redundant: `add()` already manages its own transaction; would risk a nested-unit-of-work conflict (M024 forbids nesting) | Unnecessary and risks violating the frozen no-nested-transactions invariant |
| Handler returns only `CampaignId` (not full `DomainIdentity`) | Slightly smaller return type | Caller cannot later call `CampaignRepository.get()` without the `runtime_id`, defeating the slice's end-to-end proof purpose | Insufficient for the stated architectural goal |
| **Single sequential flow, one repository call, return full `DomainIdentity[CampaignId]`** | Matches `add()`'s existing transaction ownership; gives the caller everything needed for a subsequent lookup; simplest possible correct sequence | None material | **Selected** |

---

## 13. Design Question 9: How are errors propagated?

### Decision

**Transparently, exactly as M029 already guarantees.** The handler catches nothing. Every exception any step above can raise — `ValueError`/`TypeError` from `CampaignId`, `CampaignScopeStatement`, or `Campaign.__init__`; `AggregateAlreadyExists` or `InvalidAggregateForPersistence` from `CampaignRepository.add()` — propagates unchanged through the handler, through the already-frozen, already-tested `CommandEntryPoint`, to the caller.

### Justification

M029's frozen design and implementation already guarantee transparent, unwrapped exception propagation as an invariant (`CommandEntryPoint.__call__` simply calls `self._handler.handle(command)` with no `try`/`except`). This handler must not reintroduce error handling M029 already decided against. Introducing a `try`/`except` inside the handler to translate or wrap any of these exceptions would both duplicate work M029 already does for free and violate the frozen scope's explicit prohibition on any "new error handling logic" beyond what M029 provides (no new exception hierarchy is introduced anywhere in this design).

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| Handler catches `AggregateAlreadyExists` and translates it to a handler-specific error | Gives callers a use-case-specific exception type | Introduces a new exception type this scope does not authorize; duplicates information already present in the frozen `AggregateAlreadyExists` | Violates "no new business rule" / no new exception hierarchy |
| Handler wraps all exceptions in a generic result/outcome object instead of raising | Avoids exceptions crossing the handler boundary | Directly contradicts M029's frozen, tested transparent-propagation contract (`CommandEntryPoint` expects exceptions, not wrapped results) | Reopens a decision M029 already froze |
| **No handler-level exception handling; everything propagates unchanged** | Matches M029's frozen invariant exactly; zero new code paths to test for correctness beyond what M029 already tests | None material | **Selected** |

---

## 14. Design Question 10: What architecture-checker change, if any, is actually justified?

### Decision

**Two changes, both required together, and nothing else:**

```
ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}

FORBIDDEN_IMPORT_PREFIXES["usecases"] = (
    "empirical_platform.shared.persistence",
    "sqlalchemy",
    "psycopg",
    "boto3",
)
```

**Correction (M030-DESIGN-REVIEW-0001 / -0002):** an earlier version of this design claimed `usecases` "needs to import `shared.persistence`" and therefore proposed no `FORBIDDEN_IMPORT_PREFIXES` entry for it. That claim was wrong and is withdrawn. Design Question 3 already establishes that `CreateCampaignHandler` depends only on the `CampaignRepository` Protocol (`empirical_platform.campaign.repository`) and the `RuntimeIdentifierGenerator` Protocol (`empirical_platform.shared.identifiers` — a *different* submodule from `empirical_platform.shared.persistence`). Neither dependency requires importing `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3` anywhere inside the `usecases` package. `ALLOWED["usecases"]` including `"shared"` is still correct and necessary (it is what makes `shared.identifiers.RuntimeIdentifierGenerator` reachable), but that same broad `"shared"` grant is precisely why the narrower `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry is *also* required: `ALLOWED` governs which first-party top-level packages may be imported at all, while `FORBIDDEN_IMPORT_PREFIXES` is the mechanism this checker already uses (identically, for `campaign`, `run`, `evidence`, `review`, `application`) to carve a specific, sensitive submodule (`shared.persistence`) and third-party infrastructure libraries back out of an otherwise-broad `"shared"` grant. Both rules are required together; `ALLOWED` alone cannot express "may use `shared.identifiers` but not `shared.persistence`."

**Concrete persistence and runtime objects are supplied to `CreateCampaignHandler` from outside the `usecases` package** — by a test, or by a future composition boundary this milestone does not build (Design Question 4) — never acquired or imported from within `usecases` itself.

### Justification

**Why `FORBIDDEN_IMPORT_PREFIXES` is necessary, not optional, given `ALLOWED["usecases"]` includes `"shared"`:** this checker's `imported_top_level()` function only recognizes imports beginning with `empirical_platform.`; a bare `import sqlalchemy`, `import psycopg`, or `import boto3` is invisible to the `ALLOWED`-based check entirely (verified directly against `tools/check_architecture.py`'s `imported_module()`/`imported_top_level()` logic). Without a `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry, nothing in the checker would catch `usecases` importing any of these third-party infrastructure libraries directly, nor `empirical_platform.shared.persistence` specifically (which *is* reachable once `"shared"` is in `usecases`'s `ALLOWED` set, since `shared.persistence` is a submodule of the already-allowed `shared` top-level package). This is not a hypothetical gap: it is the same reasoning that already justifies the identical `FORBIDDEN_IMPORT_PREFIXES` entries `campaign`, `run`, `evidence`, `review`, and `application` already carry. `usecases` must carry the same protection for the same reason: it is allowed to import `shared` (for `shared.identifiers`), and that grant would otherwise silently also permit `shared.persistence` and unrestricted third-party persistence libraries.

**Why `ALLOWED["usecases"]` itself is unchanged and still correct:** this matches an already-frozen precedent (`ALLOWED["datasets"] = {"shared", "identifiers", "campaign"}`) rather than inventing a new shape of rule, exactly as the prior version of this design already established. That reasoning survives this correction unchanged.

This is exactly the "one narrowly-scoped architecture-checker addition" the frozen scope document's Section 15 conditionally pre-authorized — it is one *coherent* addition (an allow-rule and its accompanying forbid-rule, the same paired shape every other persistence-adjacent package already uses), not an expansion of scope.

### Alternatives Considered

| Option | Advantages | Disadvantages | Rejection Reason |
| --- | --- | --- | --- |
| No checker change (use the `shared`-package escape hatch) | Zero checker diff | Architecturally poor placement (Design Question 1); technically legal but not sound | Rejected already in Design Question 1 |
| Broader `usecases` allowance (e.g., also `run`, `evidence`, `review`, `governance`, `registry`) | Anticipates future milestones' needs in one change | Grants import rights this milestone's scope does not use or justify; premature, unreviewed expansion | Violates "avoid speculative abstractions"; each future aggregate's use case should justify its own import need when it arrives |
| `ALLOWED["usecases"]` addition only, no `FORBIDDEN_IMPORT_PREFIXES` entry (the original, incorrect version of this design) | One rule instead of two | Leaves `usecases` free to import `shared.persistence`, `sqlalchemy`, `psycopg`, and `boto3` completely undetected by the checker, contradicting Design Question 3's own Protocol-only dependency decision | **Rejected on review** — internally inconsistent; creates exactly the infrastructure escape path Design Question 3 was written to prevent |
| **`ALLOWED["usecases"]` addition paired with a `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry blocking `shared.persistence`/`sqlalchemy`/`psycopg`/`boto3`** | Grants exactly what this milestone needs (`shared.identifiers`, `identifiers`, `campaign`) while closing the exact gap `ALLOWED` alone cannot close; matches the identical paired-rule shape every other persistence-adjacent package in this checker already uses | Two rule entries instead of one | **Selected** — the only internally consistent option |

### Future Fixture Coverage (Implementation-Phase Work, Specified Here Only in Shape)

Mirroring the pattern M029's own implementation already established (`tests/fixtures/illegal_imports/src/empirical_platform/application/...`), implementation must add fixtures under `tests/fixtures/illegal_imports/src/empirical_platform/usecases/` proving the **paired** `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` rule above is actually enforced, not merely declared. The design specifies the required matrix; it does not write the fixtures.

**Must be accepted** (proves the positive `ALLOWED["usecases"]` grant is usable for what this milestone actually needs):

- `usecases` importing the `CampaignRepository` abstraction (`empirical_platform.campaign.repository`).
- `usecases` importing the `RuntimeIdentifierGenerator` abstraction and identifier/domain value types (`empirical_platform.shared.identifiers`, `empirical_platform.identifiers`).
- `usecases` importing any other explicitly justified first-party dependency this milestone's implementation actually uses (e.g. `empirical_platform.shared.contracts.command` for `CommandHandler` typing, `empirical_platform.campaign.aggregate` for `Campaign`/`CampaignScopeStatement`) — no dependency beyond what implementation actually needs should be added to a fixture "accepted" case.

**Must be rejected** (proves the `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry actually blocks the exact escape path Finding 0001/0002 identified):

- `usecases` importing `empirical_platform.shared.persistence` (any submodule).
- `usecases` importing a concrete PostgreSQL runtime or adapter module (e.g. `empirical_platform.shared.persistence.postgres_repositories.runtime`, `...campaign_repository`).
- `usecases` importing `sqlalchemy` directly.
- `usecases` importing `psycopg` directly.
- `usecases` importing `boto3` directly.
- `usecases` importing an unrelated domain aggregate (`run`, `evidence`, `review`) or an unrelated infrastructure package (`entrypoints`, `audit`, `archive`, `acquisition`, `normalization`, `validation`, `decision_candidate`) — none of which this milestone's `ALLOWED["usecases"]` grant includes.

**Must also be reconfirmed** (proves no *other* existing package's rules were weakened by this addition): `campaign` still cannot import `usecases` (no entry for `usecases` exists in `ALLOWED["campaign"]`), and the full existing source tree still passes `test_current_source_tree_respects_boundaries` unmodified.

This milestone's fixtures must cover exactly this matrix — no unrelated fixture requirement is introduced.

---

## 15. Design Constraints Preserved

Verified against the actual frozen source, not assumed:

- **Domain purity:** `Campaign`, `CampaignScopeStatement`, `CampaignRepository` are used exactly as frozen, unmodified. `campaign`'s architecture-checker entry is untouched.
- **Existing Protocols:** `CommandHandler[_CommandT_contra, _ResultT_co]` (M027) is satisfied structurally; not modified, not subclassed, not reinterpreted.
- **Existing Repository contracts:** `CampaignRepository.add()` (M020) is called exactly as its frozen signature requires; not modified.
- **Existing EntryPoint contracts:** `CommandEntryPoint[CommandT, ResultT]` (M029) is used exactly as its frozen constructor/`__call__` shape requires; not modified.
- **Existing Runtime contracts:** `PostgresRepositoryRuntime` and `FoundationRuntime` (M025-M026) are **never imported or referenced inside the `usecases` package.** A test, or a future composition boundary this milestone does not build, is responsible for sourcing a `CampaignRepository`-conforming object (e.g. `runtime.repository_runtime.campaigns`) and passing it into `CreateCampaignHandler`'s constructor from *outside* `usecases`. Neither `PostgresRepositoryRuntime` nor `FoundationRuntime` is modified, and neither is a dependency of the `usecases` package itself.
- **Existing PostgreSQL adapters:** `PostgresCampaignRepository` (M023) is used exactly as frozen, and only by whatever external caller supplies the concrete `CampaignRepository`-conforming instance; `usecases` never imports it. Not modified.
- **Existing dependency direction:** the new `usecases → campaign` edge matches the already-frozen `datasets → campaign` edge; no existing edge is reversed, removed, or weakened.

### Corrected Dependency Model (Precise)

```
CreateCampaignHandler
    -> CampaignRepository Protocol            (empirical_platform.campaign.repository)
    -> RuntimeIdentifierGenerator Protocol    (empirical_platform.shared.identifiers)
    -> Campaign aggregate and domain value types
       (Campaign, CampaignScopeStatement, CampaignId, DomainIdentity)
```

`CreateCampaignHandler` and the `usecases` package as a whole **must not** import or depend directly on:

- `empirical_platform.shared.persistence` (any submodule)
- `PostgresRepositoryRuntime`
- `FoundationRuntime`
- `PostgresCampaignRepository`
- `sqlalchemy`
- `psycopg`
- `boto3`
- database connections, sessions, or engines
- transaction factories or unit-of-work objects
- any other infrastructure adapter

Concrete repository and runtime objects are constructed and supplied entirely outside `usecases` — by tests in this milestone, and potentially by a composition boundary in a later, separately scoped milestone (Design Question 4). This design does not design that future composition code.

---

## 16. Prohibited Items — Confirmed Absent From This Design

- No DI framework: dependencies are passed via plain constructor parameters, nothing more.
- No registry: `usecases` contains exactly one command/handler pair; no lookup mechanism of any kind.
- No service locator: rejected explicitly in Design Question 3.
- No mediator: `CommandEntryPoint` is used directly; no intermediary dispatch object is introduced.
- No transport: no HTTP, no CLI, no worker — the binding call site lives in tests only (Design Question 4).
- No HTTP / API / queue / scheduler: none referenced anywhere in this design.
- No market data / trading logic: this design touches only `Campaign` creation, a governance/administrative aggregate, not any trading or market-data concept.
- No event bus / command bus: `CommandEntryPoint` is the only dispatch mechanism used, exactly as M029 already froze it.
- No generic framework: this design produces exactly one command, one handler, one new package with a three-entry `ALLOWED` set — nothing generic or reusable beyond what one future milestone might independently choose to imitate (and independently justify).

---

## 17. Boundaries

### In Scope

- `src/empirical_platform/usecases/__init__.py` (new package).
- `src/empirical_platform/usecases/create_campaign.py` (new module: `CreateCampaignCommand`, `CreateCampaignHandler`).
- One paired `ALLOWED["usecases"]` / `FORBIDDEN_IMPORT_PREFIXES["usecases"]` addition to `tools/check_architecture.py`.
- Contract tests proving `CreateCampaignHandler` conforms to `CommandHandler[CreateCampaignCommand, DomainIdentity[CampaignId]]`.
- Unit tests for the handler's translation/orchestration logic against a fake `CampaignRepository`.
- Integration tests proving the golden path and the `AggregateAlreadyExists` failure path against real PostgreSQL, invoked through a directly-constructed `CommandEntryPoint`.
- Architecture-checker test fixtures proving the new `usecases` boundary is enforced (mirroring M029's own precedent).

### Out of Scope

- Everything the frozen scope document's Section 9 already excludes: any `Run`/`EvidencePackage`/`Review` command or query; any other `Campaign` operation; the query-side vertical slice; any composition-root abstraction beyond direct binding; any transport layer; any retry/optimistic-concurrency handling; any `run_composed()` usage; any market-data/vendor/trading/execution behavior; any change to M020-M029 frozen material; any MILESTONE-031 work.

### Non-Goals

- This design does not attempt to anticipate the shape of any future concrete command. The `usecases` package's `ALLOWED` entry is deliberately minimal (Design Question 10), not pre-expanded for imagined future needs.
- This design does not introduce a testing framework, fixture library, or test-utility abstraction beyond what M020-M029's own test suites already establish as precedent.

### Deferred Work

- The symmetric query-side vertical slice (a separate future milestone, per the frozen scope).
- Any production composition/binding code (deferred per Design Question 4, pending evidence of genuine repeated need).
- Any expansion of `usecases`'s `ALLOWED` set beyond `{"shared", "identifiers", "campaign"}` (each future aggregate's use case justifies its own need independently).
- Retry-on-`OptimisticConcurrencyConflict` policy (requires a `save()`-based handler, which this milestone does not include).

---

## 18. Risks

**Architectural risks:**

- `usecases` could become an undisciplined "dumping ground" if future milestones stop giving each use case its own single-responsibility file. Mitigation: this design establishes (but does not enforce as a rule) one-file-per-use-case; each future milestone's own design phase should re-justify this convention rather than assume it silently.

**Dependency risks:**

- The handler's constructor dependency on `RuntimeIdentifierGenerator` in addition to `CampaignRepository` is a second collaborator; if a future use case needs three or more collaborators, constructor injection could become unwieldy. Not a risk for this milestone (exactly two collaborators), but worth future design phases re-evaluating if it recurs.

**Testing risks:**

- Integration tests against real PostgreSQL depend on the existing `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS` opt-in convention; if not run, the golden-path proof against real infrastructure is skipped by default in ordinary CI runs. This is an accepted, pre-existing repository-wide convention (used by every M022-M026 integration test), not a new risk this milestone introduces.

**Governance risks:**

- As the *first* concrete command/handler, every choice in this design (package name, injection style, error propagation, return-type shape) risks being copied by future milestones as an unreviewed convention rather than independently re-justified. Mitigation: the frozen scope document already states this explicitly ("whatever pattern this milestone establishes is a precedent to evaluate, not a framework to enforce"); this design does not claim otherwise.

**Implementation risks:**

- `tools/check_architecture.py` is a shared, sensitive file last modified during M029's implementation. Implementation must add exactly the paired `ALLOWED["usecases"]` and `FORBIDDEN_IMPORT_PREFIXES["usecases"]` entries this design specifies (Section 14), verify the full existing test suite (`test_current_source_tree_respects_boundaries`) still passes unmodified, and add new positive and negative fixtures proving the full matrix (Section 14) is actually enforced — not merely declared.

---

## 19. Acceptance Criteria for This Design

This design is complete and ready for independent review when:

- [x] All ten design questions are answered with justification, not left open.
- [x] Every alternative considered states advantages, disadvantages, and a rejection reason.
- [x] No design decision reopens any M020-M029 frozen contract.
- [x] No prohibited item (DI framework, registry, service locator, mediator, transport, HTTP, API, queue, scheduler, market data, trading logic, event bus, command bus, generic framework) appears anywhere in this design.
- [x] In-scope, out-of-scope, non-goals, and deferred work are explicit and match the frozen scope document.
- [x] Architectural, dependency, testing, governance, and implementation risks are identified.
- [x] The one architecture-checker change is justified against an already-frozen precedent, not invented from nothing.

---

## 20. Next Permitted Action

**MILESTONE-030 FINAL INDEPENDENT DESIGN RE-REVIEW.**

If and only if this design is approved and owner-frozen: **MILESTONE-030 IMPLEMENTATION.**

This document does not authorize implementation.

---

## 21. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

         MILESTONE-030 DESIGN CANDIDATE (CORRECTED)

═══════════════════════════════════════════════════════════════════════════════

Status:                          CANDIDATE_FOR_FINAL_INDEPENDENT_DESIGN_RE_REVIEW
Design Questions Answered:       10 / 10
Alternatives Documented:         10 / 10
Prohibited Items Introduced:     0
Frozen Contracts Reopened:       0
Architecture-Checker Changes:    1 coherent addition, 2 rule entries
                                  (ALLOWED["usecases"] = {"shared", "identifiers", "campaign"};
                                   FORBIDDEN_IMPORT_PREFIXES["usecases"] = ("empirical_platform.shared.persistence",
                                     "sqlalchemy", "psycopg", "boto3"))

Selected Package:                empirical_platform.usecases (new)
Selected Module:                 usecases/create_campaign.py
Selected Dependency Style:       Constructor injection (CampaignRepository, RuntimeIdentifierGenerator)
Selected Binding:                Direct CommandEntryPoint(handler) construction, test-only
Selected Identity Strategy:      Caller-supplied CampaignId; handler-generated runtime_id
Selected Error Strategy:         Fully transparent propagation (no handler-level try/except)

Corrections Applied (this revision):
  M030-DESIGN-REVIEW-0001 (MAJOR) -- removed the false claim that usecases
    needs shared.persistence access; stated the precise dependency model
    (CampaignRepository + RuntimeIdentifierGenerator Protocols only).
  M030-DESIGN-REVIEW-0002 (MAJOR) -- added the required
    FORBIDDEN_IMPORT_PREFIXES["usecases"] entry; aligned the fixture matrix
    with the corrected, paired ALLOWED/FORBIDDEN_IMPORT_PREFIXES design.

NEXT PERMITTED ACTION: MILESTONE-030 FINAL INDEPENDENT DESIGN RE-REVIEW

═══════════════════════════════════════════════════════════════════════════════
```
