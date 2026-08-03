# MILESTONE-036 - Concrete Application Command Vertical Slice (EvidencePackage Creation) Design

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW**

Produced within the same consolidated Macro Milestone Mission as the scope document. Not approved, not frozen, does not authorize implementation on its own.

---

## 2. Architectural Context

The frozen-in-this-mission scope authorizes exactly one capability: create a new `EvidencePackage` for an existing `Run`, via `EvidencePackageRepository.add()`. This is structurally isomorphic to M033's Run-creation slice one level down the now-fully-proven dependency chain, and the design deliberately reuses M033's already-hostile-reviewed reasoning wherever the two capabilities are genuinely identical in shape — while independently verifying every claim against `EvidencePackage`'s own actual source, not assuming symmetry.

---

## 3. Repository-Verified Facts

- `EvidencePackage(identity: DomainIdentity[EvidencePackageId], run_id: RunId)` — minimal constructor, verified directly in `evidence/package.py`.
- `EvidencePackageRepository.add(aggregate: EvidencePackage) -> SaveResult` — frozen M020 signature; raises `AggregateAlreadyExists` on duplicate `DomainIdentity`/`governance_id`/`runtime_id`, `InvalidAggregateForPersistence` when invalid.
- `PostgresEvidencePackageRepository.add()` — verified directly: on `FoundationError`, checks `unique_violation_constraint_name(exc)` against `_ROOT_UNIQUE_CONSTRAINTS = {"pk_evidence_package", "uq_evidence_package_governance_id"}`; if the violated constraint is a root unique constraint, raises `AggregateAlreadyExists`; otherwise **bare re-raises the original `FoundationError` unchanged** — identical mechanism to `PostgresRunRepository.add()`.
- `evidence_package.run_id → run.governance_id` is a real foreign key (verified directly in the M022 migration) — a missing Run produces a foreign-key violation (SQLSTATE `23503`), which `unique_violation_constraint_name` does not classify as a unique violation (SQLSTATE `23505`), so the FK violation reaches the bare re-raise path — a raw `FoundationError(category=PERSISTENCE)`, never translated.
- `EvidencePackage`'s initial lifecycle state is `INITIALIZED` (verified directly, `EvidencePackageLifecycleState.INITIALIZED`).
- `ALLOWED["usecases"]` does not currently include `"evidence"` — verified directly against live `tools/check_architecture.py`.

---

## 4. Identity Model Analysis

Two established precedents exist in this codebase for identity: (A) full `DomainIdentity` supplied by the caller (used by every *retrieval*/*transition* command — `GetRunQuery`, `AuthorizeRunCommand`), and (B) raw governance-ID string supplied by the caller, with the handler minting a new runtime ID via `RuntimeIdentifierGenerator` (used by every *creation* command — `CreateCampaignCommand`, `CreateRunCommand`). This capability is a creation command — it mints a brand-new `EvidencePackage` identity, not operating on an existing one — so precedent (B) applies, independently re-confirmed for `EvidencePackage`: there is no existing `EvidencePackage` row to reference before this command runs, so a full-`DomainIdentity` model would have nothing valid to construct from. **Selected: raw governance-ID string + handler-generated runtime ID**, exactly mirroring `CreateRunCommand`.

---

## 5. Run-Existence Validation Analysis

Two options: (A) persistence-enforced via the real FK, no application-level `RunRepository` lookup (M033's own precedent for Campaign-existence); (B) an explicit `RunRepository.get()` pre-check in the handler. Option B was already rejected once, with full reasoning, at M033 design time for the analogous Campaign-existence question — race-exposed (a Run deleted between the check and the `add()` call would still need FK-level protection anyway, making the check redundant even when it passes) and adds a repository dependency + call the FK already makes unnecessary. Independently re-confirmed sound for `EvidencePackage`/`Run`: the identical FK mechanism exists (Section 3), so the identical reasoning applies without modification. **Selected: Option A, no `RunRepository` dependency.**

---

## 6. Result Contract Analysis

Precedent: `CreateCampaignHandler`/`CreateRunHandler` both return `DomainIdentity[<Id>]` (the newly created identity), not `SaveResult`. This differs from M032/M035's *transition* commands, which return `SaveResult` because a write-side caller needs the resulting persisted version after a **mutation of an existing row**. A **creation** command has no "before" state to compare against — the caller's primary need is the identity it can now use for further operations, exactly what `DomainIdentity[EvidencePackageId]` provides. **Selected: `DomainIdentity[EvidencePackageId]`**, mirroring `CreateRunHandler` exactly, independently re-justified (not merely copied) on this creation-vs-transition distinction.

---

## 7. Exact Command Contract

Module: `empirical_platform/usecases/create_evidence_package.py`

```python
@dataclass(frozen=True, slots=True)
class CreateEvidencePackageCommand:
    """Request to create a new EvidencePackage for an existing Run.

    Carries raw, unvalidated data; `CreateEvidencePackageHandler` translates
    it into the already-frozen `EvidencePackageId` and `RunId` value
    objects, which perform all format validation. Run existence is not
    validated here or in the handler -- it is enforced by the database
    foreign-key constraint on the `evidence_package.run_id` column.
    """

    evidence_package_governance_id: str
    run_governance_id: str
```

---

## 8. Exact Handler Contract

```python
class CreateEvidencePackageHandler:
    """Creates and persists a new EvidencePackage for one command."""

    __slots__ = ("_evidence_package_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        evidence_package_repository: EvidencePackageRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._evidence_package_repository = evidence_package_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateEvidencePackageCommand) -> DomainIdentity[EvidencePackageId]:
        """Create and persist a new EvidencePackage; return its identity."""
        identity = DomainIdentity(
            governance_id=EvidencePackageId(command.evidence_package_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        package = EvidencePackage(
            identity=identity,
            run_id=RunId(command.run_governance_id),
        )
        self._evidence_package_repository.add(package)
        return package.identity
```

Sole dependencies: `EvidencePackageRepository`, `RuntimeIdentifierGenerator`. No `RunRepository`, no `CampaignRepository`, no `Clock`.

---

## 9. Exact Sequence

1. Receive command.
2. Construct `EvidencePackageId(command.evidence_package_governance_id)` — format-validates.
3. Call `runtime_identifier_generator.generate()` exactly once.
4. Construct `DomainIdentity`.
5. Construct `RunId(command.run_governance_id)` — format-validates.
6. Construct exactly one `EvidencePackage` aggregate.
7. Call `evidence_package_repository.add(package)` exactly once.
8. Return `package.identity` unchanged.

No `get()`/`save()` call of any kind. No retry. No Run lookup.

---

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateAlreadyExists` (duplicate identity) and `InvalidAggregateForPersistence` (invalid aggregate). The missing-Run scenario reaches a **raw, untranslated `FoundationError`** — verified directly against the concrete adapter's exception-handling code path (Section 3) — identical to M033's own hostile-review-verified decision for the missing-Campaign case. No handler-level `try`/`except`, no wrapping, no translation.

---

## 11. Validation Ownership

`EvidencePackageId`/`RunId` own format validation at construction. `DomainIdentity` validates only base identity-pair structure. `EvidencePackage.__init__` owns its own type checks. The repository/adapter own persistence and uniqueness/FK enforcement. The handler performs no duplicate validation.

---

## 12. Transaction Ownership

No application-level transaction orchestration — one repository-owned `add()` call, already atomic via its own `unit_of_work()`.

---

## 13. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone.

---

## 14. Architecture-Checker Impact

**Exactly one narrow addition:** `ALLOWED["usecases"]` gains `"evidence"`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` is unchanged (already blocks persistence/sqlalchemy/psycopg/boto3). No other permission change.

---

## 15. PostgreSQL Success Strategy

Seed Campaign (M030) → Run (M033) → invoke `CreateEvidencePackageCommand` through `CommandEntryPoint`; assert the returned identity; independently reload via the repository and assert `state is EvidencePackageLifecycleState.INITIALIZED`, `run_id` matches, `criterion_results`/`artifact_references` are empty.

---

## 16. PostgreSQL Missing-Run Strategy

Seed Campaign+Run are **not** seeded (or a non-existent `run_governance_id` is used); invoke the command; assert a raw `FoundationError` propagates, **not** `AggregateAlreadyExists`/`AggregateNotFound`; assert no row was persisted (reload attempt via `get()` raises `AggregateNotFound`).

---

## 17. PostgreSQL Duplicate-Identity Strategy

Create one EvidencePackage; attempt a second creation with the same `evidence_package_governance_id` (duplicate governance) and separately with the same runtime ID via a `DeterministicRuntimeIdentifierGenerator` (duplicate runtime); assert `AggregateAlreadyExists` in both cases.

---

## 18. Test Strategy

Unit: command field/immutability/slots; handler dependency shape (no `RunRepository`); exactly-one-`add()`-call with exact constructed aggregate; exact identity returned; `AggregateAlreadyExists`/arbitrary-`add()`-failure propagation; `CommandEntryPoint` binding and reuse. Contract: `CommandHandler[CreateEvidencePackageCommand, DomainIdentity[EvidencePackageId]]` typed-conformance proof, `handle` signature shape, no-inheritance. Architecture: real checker run, zero unauthorized permission. PostgreSQL: Sections 15-17 plus M030/M033 regression.

---

## 19. Alternatives and Rejections

| Decision | Alternatives | Selected | Reason |
| --- | --- | --- | --- |
| Identity model | Full `DomainIdentity` caller-supplied | Raw governance string + generated runtime ID | Creation command mints a new identity; nothing exists yet to reference |
| Run-existence validation | Application-level `RunRepository.get()` pre-check | Persistence-enforced FK only | Race-exposed, redundant with the FK, unjustified extra dependency — identical M033 reasoning independently re-confirmed for this FK |
| Result contract | `SaveResult` | `DomainIdentity[EvidencePackageId]` | Creation (no "before" state) vs. transition (caller needs new persisted version) — independently re-derived distinction |
| Missing-Run error treatment | Translate to a domain-specific error | Transparent raw `FoundationError` | Verified directly against adapter code; no translation occurs in the real exception path |

---

## 20. Risks

Constructor-shape assumption not holding (mitigated: verified directly against live source, Section 3); FK-violation mechanism differing from Run's (mitigated: verified directly, identical `_ROOT_UNIQUE_CONSTRAINTS`/bare-reraise pattern); scope creep into EvidencePackage mutation (explicitly excluded).

---

## 21. Hostile Self-Review

Second `add()`/`get()`/`save()` call: absent (Section 9). `RunRepository` dependency: absent (Section 8). Retry: absent. Composition root: absent (Section 13). `Review`/M037 leakage: absent anywhere in this document. Architecture permission scope: exactly one line, verified against live source (Section 14).

---

## 22. Final Status

**CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW.** Not approved. Not frozen.
