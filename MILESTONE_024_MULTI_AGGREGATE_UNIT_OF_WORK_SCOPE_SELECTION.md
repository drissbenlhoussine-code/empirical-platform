# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024 |
| Title | Multi-Aggregate Persistence Unit of Work Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `4ce800d3609ba7c621eadffc338bc5bc2503228d` |
| Baseline status | MILESTONE-023 APPROVED AND FROZEN |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Repository contracts, mapper contracts, schema, or concrete adapters modified | No |

## 2. Frozen Baseline

MILESTONE-023 freezes four concrete mappers and four concrete PostgreSQL repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`), each satisfying the frozen M020 Repository Protocols and M021 Mapper Protocols against the frozen M022 schema. The repository now contains, verified live:

- frozen aggregate/reconstruction behavior (M013-M019);
- frozen `CampaignRepository`/`RunRepository`/`EvidencePackageRepository`/`ReviewRepository` Protocols — exactly `get`/`add`/`save` — and their `LoadedAggregate`/`SaveOperation`/`SaveResult`/`RepositoryContractError` support types (M020);
- frozen `CampaignMapper`/`RunMapper`/`EvidencePackageMapper`/`ReviewMapper` Protocols and durable-record types (M021);
- the frozen twelve-table PostgreSQL schema (M022);
- four **concrete, working, real-PostgreSQL-proven repository adapters** (M023), each of whose `get`/`add`/`save` opens exactly one `PostgresUnitOfWork` internally per call — verified live in `src/empirical_platform/shared/persistence/postgres_repositories/{campaign,run,evidence_package,review}_repository.py`;
- `empirical_platform.shared.persistence.postgres.PostgresUnitOfWork` — verified live in `src/empirical_platform/shared/persistence/postgres.py` — provides exactly `execute(statement, parameters) -> Sequence[Mapping[str, object]]`, `commit()`, `rollback()`, single-connection, single-transaction-per-`with`-block, and a `_active_unit_of_work` `ContextVar` guard that **raises `FoundationError` if a unit of work is opened while another is already active on the same context** (confirmed live and exercised by M023's own tests; M023 Design Section 11 point 5 states this explicitly: "a repository operation must not be invoked reentrantly from within another already-open unit of work");
- no application services, runtime composition, dependency-injection wiring, APIs, or workers exist anywhere in the repository.

MILESTONE-020 (Design Sections 18/26), MILESTONE-021 (Design Section 15), and MILESTONE-023 (Design Section 11, Scope Selection Candidate D) each independently evaluated and deferred a "multi-statement/multi-aggregate Unit of Work" as premature, for the same stated reason every time: no concrete repository existed yet to make the design concrete against. M023's own Scope Selection Section 7 recorded this precisely: *"Candidate D was already evaluated and re-rejected twice (M020, M021); nothing new justifies revisiting it, and Candidate B's design will explicitly confirm the existing single-statement primitive suffices for one repository operation rather than silently assuming so."* M023's Design Section 11 then did exactly that, and closed by naming the next step directly: *"Candidate D (multi-statement/multi-aggregate Unit of Work) remains correctly deferred; nothing above requires it"* — phrased as a forward pointer to precisely this milestone, not a closed door.

That blocker — the absence of a concrete repository to design against — is now resolved. Four concrete, frozen, empirically-proven repository adapters exist.

## 3. Current Persistence-Readiness Inventory

| Area | Repository evidence | Readiness |
| --- | --- | --- |
| Concrete repository adapters | 4 exist, frozen, real-PostgreSQL-proven (M023) | Ready to be composed |
| Transaction primitive | `PostgresUnitOfWork`, single-transaction-per-`with`-block, reentrancy explicitly forbidden (raises `FoundationError`) | Sufficient for one repository operation; **does not currently support composing two or more repository operations into one atomic transaction** — this is the exact, empirically-confirmed gap this milestone addresses |
| Repository Protocol shape (M020, frozen) | `get(identity)` / `add(aggregate)` / `save(aggregate, *, expected_persisted_version)` — no session, transaction, or Unit-of-Work parameter anywhere in any of the four Protocols (verified live in `src/empirical_platform/shared/contracts/repository.py`) | Any multi-aggregate composition design must not add one — M020 Design Section 26 is explicit: *"repository contracts do not accept database sessions... do not expose transaction objects... do not expose Unit of Work objects"* |
| Application/runtime-composition layer | None exists | Composing repositories requires *some* caller; no application service, worker, or DI container exists to be that caller, and building one is explicitly out of scope for this milestone (see Section 10) |
| Architecture permissions | `shared.persistence.*` already permits `sqlalchemy`/persistence imports (M023 already widened `ALLOWED["shared"]`); `campaign`/`run`/`evidence`/`review` remain forbidden from importing persistence machinery, unchanged | A composition primitive living in `shared.persistence` needs no further architecture-checker change; this milestone must confirm, not assume, that |

## 4. Remaining Uncertainty

Unresolved questions a design must answer before any multi-aggregate transaction composition can be built honestly:

- **how** a caller composes two or more repository operations (potentially across different aggregate repositories, e.g. persisting a `Run` and its parent `Campaign`'s updated state together) into one atomic transaction, **without** adding a session/transaction/Unit-of-Work parameter to any M020 `get`/`add`/`save` signature (frozen, non-negotiable);
- whether this requires the concrete repository adapters (M023, frozen) to change their internal transaction-acquisition behavior at all, and if so, whether that change is additive (an opt-in ambient scope existing repositories join when present, with zero behavior change when absent) or requires reopening M023's Section 11 point 5 reentrancy prohibition — this is the single most consequential design question and must be resolved with a concrete, narrow answer, not left ambiguous;
- what happens to `SaveResult`/`LoadedAggregate`/`OptimisticConcurrencyConflict` semantics when a save inside a composed transaction fails partway through a multi-operation sequence — whether commit-before-return (M023's frozen guarantee for a single operation) has a coherent multi-operation analogue, or whether multi-operation composition necessarily defers all `SaveResult` construction until the *entire* composed transaction commits;
- whether nested/composed calls to the *same* aggregate's repository within one composed transaction (e.g., two saves to the same `Run` in one transaction) are permitted, forbidden, or simply unaddressed, and why;
- how error translation (SQLSTATE/constraint-name based, per M023 Section 9) behaves when a failure occurs on the second or later operation in a composed transaction, given the whole transaction rolls back together;
- what this milestone's design must explicitly decline to answer: it must not design *who calls* the composed-transaction primitive (an application service, a worker, a script) — only the primitive itself and how the four existing concrete repositories interact with it.

## 5. Candidate Milestones

| Candidate | Purpose | Disposition |
| --- | --- | --- |
| D. Multi-Aggregate/Multi-Statement Persistence Unit of Work | Define a composition primitive allowing a caller to atomically group two or more repository operations (potentially across aggregates) into one transaction, without changing any M020 Protocol signature. | Selected. |
| E. Repository Runtime Composition | Wire the four concrete repositories into a runtime/DI-style construction point. | Rejected as *this* milestone: legitimate and now unblocked (four concrete repositories exist to compose), but it answers "how does calling code obtain repository instances," a materially different and independent question from "how do two repository calls share one transaction." Bundling both risks an uncontrolled milestone. Remains available as an independent future milestone; does not block or get blocked by Candidate D. |
| F. Application Services | Use-case-facing orchestration calling repositories. | Rejected: requires *both* a settled multi-aggregate transaction story (Candidate D) and a settled repository-composition story (Candidate E) to be well-posed; building it now would either freeze premature transaction semantics or skip them silently. Two milestones premature. |
| I. Persistence Factory/Provider Convenience | A minimal, mechanical helper constructing all four repositories from one `PostgresPersistenceService`. | Rejected as *this* milestone: real but trivial — a handful of one-line constructor calls — and does not raise a substantive design question warranting independent architectural review on its own; more naturally belongs inside Candidate E's scope than as a standalone milestone. |
| J. Service-Level Optimistic-Concurrency Retry | Define retry-on-`OptimisticConcurrencyConflict` policy. | Rejected: M020 and M023 both explicitly defer retry as "application-owned"; no application layer exists yet to own it. Depends on Candidate F. |
| K. No Implementation-Ready Next Scope | Stop because no prerequisite is ready. | Rejected: the multi-aggregate Unit of Work design is ready and bounded now that M023 is frozen, and both M023's own design text and the M020/M021 deferral history point at it directly. |

## 6. Candidate Comparison

| Candidate | Architectural risk | Implementation risk | Unsupported-assumption risk | Reversibility risk | Scope-creep risk | Independent reviewability | Future milestones unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D | MEDIUM-HIGH | LOW (design-only) | MEDIUM | LOW (design-only; no code changes to frozen contracts) | MEDIUM | HIGH | Application services, repository composition, both now well-posed against a settled transaction story |
| E | LOW | LOW | MEDIUM | LOW | MEDIUM | HIGH | Application services (partially) |
| F | HIGH | HIGH | HIGH | MEDIUM | HIGH | LOW | Nothing further; terminal without D and E first |
| I | LOW | LOW | LOW | LOW | LOW | HIGH (but trivial) | None material on its own |
| J | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable without F |
| K | LOW | LOW | LOW | LOW | LOW | HIGH | None |

Candidate D carries genuine architectural risk — unlike M023's schema-translation questions, this design must resolve whether and how a frozen concrete adapter's internal transaction-acquisition behavior can be safely extended without reopening M023 — but, like every prior design-only milestone in this lineage, essentially no reversibility risk: nothing is implemented, and the design can be corrected freely before any code changes. This is exactly the profile (real design risk, no implementation risk, high reviewability) that has selected every prior milestone (B for M022, B for M023) over its lower-risk-but-premature alternatives.

## 7. Rejected Candidates

Candidate E (repository runtime composition) is legitimate and now unblocked, but answers an independent question from Candidate D and does not need to be resolved to design D; combining them risks exactly the uncontrolled-milestone pattern M022 and M023's own scope selections both explicitly warned against and avoided. It remains available as an independent future milestone.

Candidate F (application services) requires both D and E settled first; selecting it now would force either premature transaction-semantics decisions or silent gaps.

Candidate I (persistence factory/provider convenience) is real but mechanical enough that it does not warrant an independent scope-selection-through-freeze cycle on its own; it more naturally belongs as part of Candidate E's future scope.

Candidate J (service-level optimistic-concurrency retry) depends on Candidate F (an application layer to own the retry policy), which itself depends on D and E; three milestones premature.

Candidate K is rejected because Candidate D is ready and directly evidenced as the next step by this project's own accumulated design history (Section 2).

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Design
```

The milestone is a design milestone. It must define exactly how a caller composes two or more repository operations (potentially spanning different aggregate repositories) into one atomic transaction — without changing any frozen M020 Repository Protocol signature, and with an explicit, justified answer to whether and how the frozen M023 concrete adapters' internal transaction-acquisition behavior extends to support this — without writing implementation code, without wiring a runtime composition root, and without designing an application service.

## 9. Milestone Type

MILESTONE-024 is:

```text
MULTI-AGGREGATE UNIT OF WORK DESIGN ONLY
```

It is not implementation, repository runtime composition, dependency injection, or application-service design.

## 10. Exact Scope Boundary

In scope:

- the exact shape of a new, additive composition primitive (name, module placement, lifecycle: open/commit/rollback/close) that a caller can use to group multiple repository operations into one transaction;
- an explicit, justified decision on whether the four frozen M023 concrete repository adapters require any internal behavior change to participate in a composed transaction, and if so, the exact, narrow nature of that change (e.g., ambient-scope detection via `ContextVar`, ordinary use unaffected when no composed scope is active) — framed and justified as an additive extension of M023's transaction-acquisition behavior, not a reopening of its frozen `get`/`add`/`save` semantics;
- explicit confirmation that no M020 Repository Protocol signature (`get`/`add`/`save`) changes — the composition mechanism must live entirely outside the Protocol surface;
- commit/rollback/error-propagation semantics for the composed transaction as a whole, including what happens to each individual repository call's return value (`LoadedAggregate`/`SaveResult`) when it occurs partway through a still-open composed transaction;
- exact behavior when a composed transaction is entered while one is already active (nesting), and when a repository operation is invoked with no composed scope active (must remain byte-for-byte identical to today's M023 behavior);
- test strategy for a future implementation milestone, covering at minimum: two-aggregate atomic commit, two-aggregate atomic rollback-on-failure, ordinary single-operation calls unaffected when no composed scope is open, and nested composed-scope-open-while-already-open behavior;
- architecture and security constraints;
- explicit non-goals preventing implementation, runtime composition, or application-service lock-in.

Out of scope:

- writing implementation code for the composition primitive;
- wiring concrete repositories into any runtime/DI/composition root (Candidate E, independent, deferred);
- application services or use-case orchestration (Candidate F, deferred, depends on this milestone and Candidate E);
- retry-on-`OptimisticConcurrencyConflict` policy (Candidate J, deferred, depends on Candidate F);
- any change to the M020 Repository Protocols, M021 Mapper Protocols, or M022 schema;
- any change to the four concrete repository adapters' `get`/`add`/`save` *external* behavior when no composed transaction is active;
- APIs, workers, Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 11. Aggregate Coverage

All four aggregates are in scope for the composition primitive's design (it must be demonstrably usable to compose, e.g., a `Campaign` save with a `Run` add, or any other pairing) — the primitive itself is aggregate-agnostic by construction, since it lives outside the repository Protocol surface, but the design must show at least one concrete cross-aggregate example to prove the shape actually composes in practice, not just in the abstract.

## 12. Required Deliverables (of the Design, not of this scope selection)

- exact composition-primitive shape: name, module, public surface, lifecycle;
- exact, narrow, justified decision on whether/how the M023 concrete adapters extend to participate, with the "additive, not reopening" claim explicitly defended;
- exact commit/rollback/error-propagation semantics for composed transactions;
- exact nesting and no-composed-scope-active behavior, with an explicit backward-compatibility argument for the latter;
- exact module placement relative to `tools/check_architecture.py`'s existing rules;
- test strategy for a future implementation milestone;
- explicit non-goals preventing implementation/runtime-composition/application-service lock-in;
- hostile self-review before independent review.

## 13. Test Obligations (to be defined by the Design, executed only in a future Implementation milestone)

The Design must specify future test categories only: two-repository-operation atomic commit against real PostgreSQL, two-repository-operation atomic rollback when the second operation fails, single-operation calls with no composed scope active behaving identically to today's frozen M023 behavior (regression proof), nested composed-scope-open-while-already-open behavior, and composed-transaction behavior when the *first* operation's own guarded optimistic-concurrency check fails.

## 14. Architecture Constraints

The Design must treat `tools/check_architecture.py`'s existing `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` tables as authoritative and must explicitly confirm — not silently assume — that a composition primitive living in `shared.persistence` requires no further change, since M023 already widened `ALLOWED["shared"]` to include the four aggregate packages and `identifiers`. Any proposed adjustment must be narrow, explicit, and justified; the Design must not propose broadening permissions beyond what the composition primitive strictly requires, and must not grant `campaign`/`run`/`evidence`/`review` any new persistence-import permission.

## 15. Security Constraints

The Design must not introduce new credential handling or connection-string construction; those remain the existing `PersistenceService`/`resolve_foundation_config()` infrastructure's concern, unchanged since M008. The Design must consider whether a composed multi-operation transaction held open longer than a single operation introduces any new connection-exhaustion or long-transaction-lock concern, and if so, state the constraint (e.g., an explicit maximum composed-operation count or duration) rather than leaving it unaddressed.

## 16. Stop Conditions

Stop MILESTONE-024 design if:

- the design would require changing a frozen M020 Repository Protocol signature, M021 mapper/durable-record shape, or M022 schema/constraint;
- the design cannot avoid reopening M023's Section 11 transaction-ownership rules in a way that changes any *existing* single-operation behavior (any change must be strictly additive);
- answering a design question requires writing and running implementation code first;
- the design cannot be demonstrated, at least on paper, to compose a genuine two-aggregate example without contradiction.

## 17. Acceptance Gate

MILESTONE-024 scope is acceptable only if:

- the composition primitive's design does not add a session/transaction/Unit-of-Work parameter to any M020 Protocol signature;
- the design's effect on the four frozen M023 concrete repository adapters is explicitly additive and justified as such, with single-operation behavior proven unchanged when no composed scope is active;
- commit/rollback/error-propagation, nesting, and no-composed-scope-active questions in Section 4 are all enumerated for resolution by the Design;
- runtime composition, dependency injection, application services, and retry policy remain deferred;
- validation passes;
- only this scope-selection document (and, in the same mission, the Design document) is changed.

## 18. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M024-SCOPE-ISSUE-0001 | MAJOR | 2, 4, 10 | Initial framing risked treating "extend the M023 adapters to join an ambient transaction" as a purely additive, risk-free change without confronting that M023 Design Section 11 point 5 *explicitly, deliberately* raises an error on reentrant Unit-of-Work use — a frozen behavioral guarantee, not an oversight. | Read live: `PostgresUnitOfWork`'s `_active_unit_of_work` `ContextVar` guard and M023 Design Section 11 point 5's exact wording were both re-verified before writing Section 4. | Understating this risk could produce a Design that quietly reopens M023 rather than one that explicitly, narrowly extends it with independent review positioned to catch the difference. | Named this as "the single most consequential design question" in Section 4, and made Section 17's acceptance gate explicitly require the Design prove single-operation behavior is unchanged when no composed scope is active — shifting the burden of proof onto the Design rather than assuming safety. | Resolved |
| M024-SCOPE-ISSUE-0002 | MAJOR | 5, 6 | Considered selecting Candidate E (repository runtime composition) instead of or alongside Candidate D, since both are now equally "unblocked" by M023's freeze. | E and D answer genuinely independent questions (how repositories are obtained vs. how multiple repository calls share one transaction); M023's own design text (Section 11) and the M020/M021/M023 deferral history point specifically and repeatedly at the transaction-composition question (Candidate D), not at composition-root wiring. | Bundling both would repeat the exact uncontrolled-milestone risk M022-SCOPE-ISSUE-0003 and M023-SCOPE-ISSUE-0003 both already resolved by keeping ready-but-independent concerns separate. | Kept Candidate E explicitly rejected-for-this-milestone, available independently, and did not let its now-also-ready status pull it into Candidate D's scope. | Resolved |
| M024-SCOPE-ISSUE-0003 | MINOR | 3 | `PostgresUnitOfWork`'s reentrancy-guard mechanism needed direct verification rather than assumed carry-forward from memory of M023's design/implementation work. | Read live: confirmed the `_active_unit_of_work` `ContextVar` guard and its `FoundationError`-raising behavior in `src/empirical_platform/shared/persistence/postgres.py`, and cross-checked against M023 Design Section 11 point 5's textual description. | Low; would have been a citation-accuracy gap only. | Verified directly and cited with file evidence in Sections 2 and 3. | Resolved |
| M024-SCOPE-ISSUE-0004 | MINOR | 5 | Considered whether Candidate I (a trivial repository-factory convenience) deserved its own candidate slot at all, given how mechanical it is. | Comparing it directly against Candidate E's stated purpose showed it is better understood as a subset of Candidate E's eventual scope than an independent concern, consistent with how M023 itself declined to introduce a generic repository base class absent an explicit need. | Low; affects candidate-table tidiness only, not the selected scope. | Kept Candidate I listed and explicitly rejected with its relationship to Candidate E stated, rather than omitting it silently. | Resolved |

No unresolved scope-selection finding remains.

## 19. Final Decision

Selected next milestone:

```text
MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Design
```

Final status:

```text
SCOPE SELECTED - PENDING INDEPENDENT REVIEW
```
