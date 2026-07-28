# MILESTONE-028 - Application Query/QueryHandler Contracts Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-SCOPE-SELECTION |
| Title | Application Query/QueryHandler Contracts Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository baseline | `64abc16156b949491ded4ff239d2c249aac569a8` |
| Mission type | Scope selection and design authorization only |

## 2. Objective

Select the single best bounded milestone after frozen M027 design using live repository evidence.

## 3. Authority

This mission is authorized by the Project Owner's direct instruction, given immediately after accepting the M027 design freeze, to perform live repository analysis, select the single most appropriate M028 candidate, and produce its Scope Selection and Design documents without implementing any source code and without starting M028 implementation.

## 4. Frozen Baseline

All of M020 through M026 are `APPROVED_AND_FROZEN`; M027's design is `APPROVED_AND_FROZEN` (implementation not started) — see `PROJECT_CHECKPOINT.md` Section 2. In particular:

- M020 froze the persistence-neutral repository Protocols and `RepositoryContractError` taxonomy.
- M026 froze `FoundationRuntime.repository_runtime`, so a fully booted process obtains a working `PostgresRepositoryRuntime` with zero manual wiring.
- M027 froze exactly one Protocol, `CommandHandler[_CommandT_contra, _ResultT_co]` (`shared/contracts/command.py`), the write-side (command) half of an application-layer command/query vocabulary, with variance-correct generics and a mechanically verified negative type-check strategy — design-frozen, not yet implemented.

## 5. Live Repository Evidence

Live evidence gathered directly from the repository (not from memory of prior milestones):

- `grep -rln "class.*Query\|QueryHandler" src/empirical_platform` returns **no results**. No query or query-handler type exists anywhere in the codebase today — confirmed by direct search during this scope-selection pass.
- `src/empirical_platform/shared/contracts/` contains `repository.py`, `mapping.py`, and (as of the M027 design, not yet implemented) the planned `command.py` — establishing `CommandHandler` as the write-side half of an application-layer vocabulary, with no read-side counterpart designed or implemented.
- Direct listing of `src/empirical_platform/datasets/`, `src/empirical_platform/acquisition/`, `src/empirical_platform/normalization/`, `src/empirical_platform/validation/`, and `src/empirical_platform/registry/` shows each contains at most one non-`__init__.py` file (`datasets/` has exactly one; the rest have zero) — all are earlier-stage placeholders than even `audit`/`decision_candidate`/`governance`, and none is a narrower or more ready candidate than completing the command/query vocabulary.
- `PROJECT_CHECKPOINT.md`'s own Deferred Capabilities list explicitly orders "application service orchestration" as depending on "repository runtime composition and the command/query vocabulary" existing — at the time of this scope selection, only the command half of that vocabulary is even design-frozen; the query half does not exist in any form.
- M027's own Scope Selection and Design documents established a proven, narrow, contracts-only pattern (a single generic, variance-correct Protocol; a positive `if TYPE_CHECKING:` conformance proof inside the module; an isolated, `mypy`-verified negative type-check fixture mechanism kept outside the canonical gate) — a pattern this milestone can reuse directly, since the read-side contract has an identical structural shape (one method, one input, one output) to the write-side contract, differing only in vocabulary and, in a future milestone, retry/idempotency semantics that this milestone does not need to decide.

Classic command/query separation (CQRS) treats commands (state-changing) and queries (state-reading) as a paired, but semantically distinct, vocabulary — deliberately kept as two named concepts rather than one, because future milestones (e.g. retry policy) will need to treat them differently: queries are ordinarily safe to retry without an idempotency concern, while commands are not. Freezing only `CommandHandler` and leaving no read-side counterpart at all leaves that vocabulary half-finished, and is the single most direct, narrow, evidence-grounded gap this repository reveals today.

**Explicit acknowledgment of M027's implementation status:** M027's `CommandHandler` Protocol is design-frozen but not yet implemented as source code. This milestone's own `QueryHandler` Protocol is fully independent of `CommandHandler` at the type level (no shared base, no import between them), so this Scope Selection and its Design can proceed without requiring M027 to be implemented first. However, MILESTONE-028 *implementation* additionally requires M027 to be implemented first, purely as a matter of project sequencing discipline (both contracts belong in the same `shared/contracts/` module-family and should land together or in a clearly ordered sequence, not interleaved) — this is recorded as an explicit Stop Condition (Section 14) and is not a technical dependency of the Protocol shape itself.

## 6. Candidate Inventory

| Candidate | Layer | Dependencies | Scope size | Risk | Decision |
| --- | --- | --- | --- | --- | --- |
| Application Query/QueryHandler Contracts | Application (contracts only) | None beyond `typing`; independent of M027 implementation status at the type level | Small | Low | Selected |
| Application Service Orchestration (full) | Application (implementation) | Requires M027 (and this milestone) to be implemented first | Large | High | Rejected as premature |
| Retry Policy (as a Protocol) | Application policy | Would need to decide command-vs-query retry semantics differently, which is premature before both handler shapes are even implemented | Medium | Medium | Rejected as premature |
| Optimistic-Concurrency Handling at Service Layer | Application policy | Explicitly requires application services to exist first | Medium | Medium | Rejected as premature |
| Runtime/Bootstrap Access Above FoundationRuntime | Infrastructure/entrypoint | Would require inventing an API/worker/CLI entrypoint ahead of any application layer to consume it | Medium | High | Rejected as premature |
| Audit Runtime Composition | Governance/runtime | `audit`/`decision_candidate`/`governance` packages remain empty placeholders | Large | High | Rejected as premature |

## 7. Candidate Comparison

| Criterion | Query/QueryHandler Contracts | Application Service Orchestration | Retry Policy Protocol | Optimistic-Concurrency Policy | Audit Runtime |
| --- | --- | --- | --- | --- | --- |
| Architectural ordering | Completes the M027 vocabulary pair | Depends on M027 + this milestone | Depends on both handler shapes existing | Depends on application services | Depends on APIs/workers |
| Dependency readiness | Ready (independent of M027 implementation status) | Not ready | Not ready | Not ready | Not ready |
| Isolation | High (new contracts-only file, mirrors M027 exactly) | Low | Medium | Low | Low |
| Independent testability | High (identical proven pattern to M027) | Medium | Medium | Medium | Low |
| Reversibility | High | Medium | Medium | Medium | Low |
| Scope-creep risk | Low | High | Medium | High | High |
| Implementation confidence | High (M027's exact pattern, already corrected once) | Medium | Low | Low | Low |

## 8. Selected Scope

MILESTONE-028 selects **Application Query/QueryHandler Contracts**.

Purpose: freeze the read-side counterpart to M027's `CommandHandler` — a single generic, variance-correct `QueryHandler` Protocol — completing the command/query vocabulary, with **zero implementation of any concrete query, handler, or orchestration logic**, exactly mirroring M027's own (corrected) precedent.

**Components evaluated:**

1. a `QueryHandler[QueryT, QueryResultT]` Protocol;
2. a `Query` marker Protocol;
3. a query-level error/result contract distinct from M020's `RepositoryContractError` and any future M027-adjacent handler error type.

**Components selected:**

- exactly one generic, variance-correct, synchronous `QueryHandler` Protocol (component 1 above), with contravariant query input and covariant result output, following M027's exact corrected pattern;
- its canonical export from `shared/contracts/`;
- a positive static (`mypy`) conformance proof, checked automatically on every `mypy` run;
- an isolated negative type-check verification mechanism, mechanically proving malformed handler shapes are rejected, kept entirely outside the canonical `mypy` gate — reusing the exact algorithm M027's own correction round verified against live `mypy` behavior.

**Components evaluated and explicitly rejected:**

- a `Query` marker type (component 2 above) — rejected for the identical reason M027 rejected a `Command` marker: an empty `Protocol` is structurally satisfied by every object;
- a query-level error/result contract (component 3 above) — rejected because no concrete query handler yet exists to reveal what failure modes it would need to express;
- any relationship, shared base type, or conversion between `CommandHandler` and `QueryHandler` — rejected as premature; the two remain fully independent Protocols until a concrete application-service milestone reveals whether unifying them has real value.

## 9. Non-Goals

- any concrete `Query` or `QueryHandler` implementation for any aggregate;
- any relationship, shared base, or unification with `CommandHandler`;
- application service orchestration, transaction ownership decisions, or any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- retry-on-`OptimisticConcurrencyConflict` policy, or any retry semantics specific to queries vs. commands;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any change to M020-M027 frozen contracts, adapters, mappers, schema, `run_composed`, `PostgresRepositoryRuntime`, `FoundationRuntime`, or `CommandHandler`.

## 10. Dependencies

| Dependency | Role | Status |
| --- | --- | --- |
| M020 | Repository Protocol contracts and `RepositoryContractError` taxonomy | APPROVED AND FROZEN |
| M026 | Foundation Runtime Repository Composition | APPROVED AND FROZEN |
| M027 | `CommandHandler` Protocol (design only; not a technical dependency of `QueryHandler`'s type shape, but a sequencing dependency for implementation — see Section 14) | DESIGN APPROVED AND FROZEN; IMPLEMENTATION NOT STARTED |

## 11. Architecture Constraints

- New contract lives in `src/empirical_platform/shared/contracts/query.py`, alongside `repository.py`/`mapping.py`/(planned) `command.py`, following the identical placement precedent M020 and M027 set.
- No new top-level package is introduced; `tools/check_architecture.py`'s `ALLOWED` table requires no change.
- No domain package (`campaign`/`run`/`evidence`/`review`) is required to import the new contract as part of this milestone.
- No import from `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3`.
- No import from, or of, `shared.contracts.command` — `QueryHandler` and `CommandHandler` remain fully independent at the type level (Section 8).

## 12. Transaction Constraints

No transaction coordinator, no `run_composed` reimplementation, no wiring to any repository or persistence service. The contract describes only the *shape* of a query handler — never how a handler obtains or uses a repository.

## 13. Concurrency Constraints

None. No concurrency primitive is introduced; the contract is a pure Protocol/type definition with no runtime state.

## 14. Security Constraints

No credential, connection, or persistence-adjacent concern is introduced.

## 15. Test Obligations

A future implementation must prove:

- the `QueryHandler[_QueryT_contra, _ResultT_co]` Protocol is structurally satisfiable by a minimal in-memory example handler with no persistence dependency, via a static (`mypy`) conformance proof checked on every run;
- the contravariant query / covariant result variance is real, proven the same way M027's correction round verified `CommandHandler`'s variance;
- malformed handler shapes are mechanically proven rejected by an isolated negative type-check mechanism, reusing M027's exact verified algorithm, that never pollutes the canonical `mypy` gate and is never collected by pytest as a test module;
- only `QueryHandler` is exported from `shared/contracts/`; the underlying `TypeVar`s are not;
- `QueryHandler` and `CommandHandler` share no base type, import relationship, or conversion function;
- no existing M020-M027 test is affected;
- `tools/check_architecture.py` reports zero violations with the new file present.

## 16. Stop Conditions

STOP design work and return to scope selection if:

- freezing a useful query/handler contract turns out to require deciding transaction ownership, caching semantics, or repository access patterns (that would mean this milestone has silently become "Application Service Orchestration" and must be re-scoped);
- a genuine, concrete need emerges to unify `QueryHandler` with `CommandHandler` under a shared base — in which case this milestone must stop and be re-scoped as a joint command/query vocabulary revision rather than proceeding with two silently-diverging, independently-evolving Protocols.

**Sequencing stop condition (implementation phase only, not design phase):** MILESTONE-028 implementation must not begin until MILESTONE-027 is implemented, reviewed, approved, and frozen. This is a project-sequencing decision, not a type-system dependency — recorded here explicitly so it is never silently skipped.

## 17. Acceptance Gate

The design is acceptance-ready only if it freezes, with no remaining ambiguity: the exact, variance-correct `QueryHandler` shape; the exact package/file placement; the exact export surface; the exact, justified decisions not to freeze a `Query` marker, a query-level error type, or any relationship to `CommandHandler`; the exact, `mypy`-verified negative type-check mechanism; and exact test obligations.

## 18. Hostile Self-Review

1. **Does this quietly become "application services"?** No — no concrete handler, no repository access, no transaction ownership decision is made.
2. **Does this presume a specific application framework or dispatch mechanism?** No — a `QueryHandler` Protocol describes a callable shape, not a registry, bus, or dispatcher.
3. **Does this leak into APIs/workers?** No — `entrypoints/` is untouched.
4. **Does this leak into retry policy?** No — retry semantics (which would legitimately differ between commands and queries) remain explicitly deferred.
5. **Does this silently couple to, or depend on, `CommandHandler`'s implementation status?** No — Section 5 explicitly documents that `QueryHandler`'s type shape requires nothing from `CommandHandler`; only the *implementation sequencing* (Section 16) references M027, and that is recorded as a project-discipline decision, not a technical necessity.
6. **Is this milestone narrow enough to actually finish in one pass?** Yes — it is contracts-only, structurally near-identical to M027's own now-corrected, proven pattern.
7. **Does this leak into M029?** No — nothing here presumes or requires any named future milestone; it only completes the command/query vocabulary that a future "Application Service Orchestration" milestone would consume.

## 19. Final Decision

```text
M028 APPLICATION QUERY/QUERYHANDLER CONTRACTS SCOPE SELECTED
M028 DESIGN READY FOR INDEPENDENT REVIEW
M028 NOT APPROVED
M028 NOT FROZEN
M028 IMPLEMENTATION NOT STARTED
```
