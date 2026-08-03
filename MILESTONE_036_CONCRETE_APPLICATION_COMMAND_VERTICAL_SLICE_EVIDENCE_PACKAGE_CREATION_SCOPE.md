# MILESTONE-036 - Concrete Application Command Vertical Slice (EvidencePackage Creation) Scope

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

This document is a scope candidate, produced as part of a consolidated Macro Milestone Mission (Section 49 of the M035 implementation freeze). It has not been reviewed, approved, or frozen.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at scope selection | `5f3b8f69afdcd7b319fd0842efb80effde8f7991` |

---

## 3. Frozen Predecessor Chain

M020-M035 all `APPROVED_AND_FROZEN` at every stage. M035 implementation freeze: `6853d988634ae264d6e625a90b9ba6815d908df5`.

---

## 4. Fresh Architecture Inventory

Rebuilt directly from live source, not reused from prior tables:

| Aggregate | `add()` | `get()` | `save()` | Application usecases |
| --- | --- | --- | --- | --- |
| `Campaign` | Proven (M030) | Proven (M031) | Proven (M032) | 3 modules |
| `Run` | Proven (M033) | Proven (M034) | Proven (M035) | 3 modules |
| `EvidencePackage` | **Unproven** | Unproven | Unproven | 0 modules |
| `Review` | Unproven | Unproven | Unproven | 0 modules |

`src/empirical_platform/usecases/` contains exactly 6 modules (`create_campaign`, `get_campaign`, `prepare_campaign_for_authorization`, `create_run`, `get_run`, `authorize_run`) — verified by direct directory listing. `evidence/` and `review/` each have a full domain aggregate, lifecycle enum, repository Protocol (M020), and concrete PostgreSQL adapter (M023) — verified directly — but zero application-layer reference exists anywhere in `usecases/`.

---

## 5. Verified Architectural Gap

All three CQRS verbs (`add()`, `get()`, `save()`) have now been independently proven to generalize across **two** aggregates each: `add()` (Campaign M030, Run M033), `get()` (Campaign M031, Run M034), `save()`/`OptimisticConcurrencyConflict` (Campaign M032, Run M035). The pattern-generalization question this project has closed one verb at a time since M033 is now fully answered for all three verbs at the two-aggregate depth. The only remaining architectural question is **aggregate breadth**: `EvidencePackage` and `Review` have zero application-layer proof of any kind — independently verified by a repository-wide search finding no reference to either aggregate anywhere in `src/empirical_platform/usecases/`.

---

## 6. Aggregate Dependency Graph

Reconstructed from constructor signatures and live migration foreign keys:

```
Campaign  (proven: add/get/save)
  ← Run            (proven: add/get/save)
      ← EvidencePackage  [EvidencePackage(identity, run_id: RunId); evidence_package.run_id → run.governance_id FK, verified directly in migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py]
          ← Review        [Review(identity, target: ReviewTargetReference[EvidencePackageId], reviewer); review.target_evidence_package_id → evidence_package.governance_id FK]
```

`EvidencePackage`'s constructor dependency is `RunId` only — the identical minimal shape `Run(identity, campaign_id)` had before M033. Parent existence is persistence-enforced via the real FK, not application-enforced — the exact mechanism M033 already proved for `Run`/`Campaign`. `Review` remains two FK hops from ready, gated behind `EvidencePackage`.

---

## 7. Candidates Considered

| Candidate | Assessment |
| --- | --- |
| **EvidencePackage creation** | Closes the largest remaining gap (zero proof for 2 of 4 aggregates); constructor is minimal (`identity`, `run_id`); real FK exists; concrete PostgreSQL adapter already fully implemented; unlocks `Review`. Repeats the already-twice-proven `add()` verb, but that is now expected and correct — with all three verbs proven twice, the next milestone's value is necessarily in aggregate-breadth extension, not verb-generalization. |
| A second Run lifecycle transition | Would repeat the already-twice-proven `save()`/`OptimisticConcurrencyConflict` pattern a third time, closing no open question. Lower leverage than extending to a third aggregate. |
| Retry-on-`OptimisticConcurrencyConflict` policy | Now has two independently-proven data points (Campaign M032, Run M035) — closer to justifiable than at any prior milestone, but remains a cross-cutting policy, not a vertical slice; this project's own established discipline has deferred it at every prior opportunity pending a concrete, evidenced need beyond "two data points now exist." No such need is evidenced. |
| `EvidencePackage` retrieval (`get()`) | Would repeat the already-twice-proven `get()` pattern and, more importantly, cannot precede creation — nothing to retrieve without it. Rejected on ordering alone, independent of pattern-repetition concerns. |
| `Review` creation | Gated two FK hops behind `EvidencePackage`; not reachable. |
| Composition root / registry / dispatcher | No repeated-handler-need evidence exists (six handlers, all trivially direct-constructed, unchanged pattern since M030). |
| Audit/governance/registry foundation | Each remains an empty stub requiring an entirely new foundational milestone chain — disproportionate to a single vertical slice. |

---

## 8. Selected M036 Scope

**One concrete application command vertical slice creating a new `EvidencePackage` for an existing `Run`, via the frozen `EvidencePackageRepository.add()` method.**

---

## 9. Why This Scope Is Next

`EvidencePackage` is the only aggregate with zero application-layer proof whose parent (`Run`) is already fully proven at the application layer. It is architecturally ready (minimal constructor, real FK, concrete adapter already implemented) and is a genuine prerequisite for `Review`. This mirrors M033's own selection of `Run` creation over `EvidencePackage`/`Review` at that time — the identical "narrowest available next aggregate" reasoning, now one link further down the now-fully-proven chain.

---

## 10. In-Scope Capability

One command, one handler, exactly one `EvidencePackageRepository.add()` call, `CommandHandler`/`CommandEntryPoint` compatibility, focused unit/contract/PostgreSQL evidence, and the one narrow architecture-checker addition (`"evidence"` to `ALLOWED["usecases"]`) this capability genuinely requires.

---

## 11. Out-of-Scope Capabilities

Any `EvidencePackage` retrieval, mutation (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`), listing, filtering, or pagination; any `Review` command or query; any Campaign/Run command or query beyond what already exists; any retry/idempotency policy; any composition-root/registry/dispatcher/DI framework; any transport layer; any schema/migration change; any MILESTONE-037 work.

---

## 12. Frozen Dependencies

M020 `EvidencePackageRepository` Protocol and `EvidencePackage` aggregate; M023 concrete PostgreSQL adapter; M027 `CommandHandler`; M029 `CommandEntryPoint`; M030/M033's caller-supplied-governance/handler-generated-runtime identity model precedent; M033's persistence-enforced-parent-existence precedent (directly reused, not merely referenced).

---

## 13. Identity and Referential-Integrity Considerations

Repository fact only: `EvidencePackage(identity: DomainIdentity[EvidencePackageId], run_id: RunId)`. Run existence is enforced by the real `evidence_package.run_id → run.governance_id` foreign key, not by any application-level `RunRepository` lookup — identical mechanism to M033's Campaign-existence enforcement. Exact command/handler identity construction is an open Design Mission question, not decided here (though the frozen `CreateRunCommand` precedent strongly constrains the reasonable option space, per Section 7).

---

## 14. Open Design Questions

Exact command/handler type names and module path; whether `RuntimeIdentifierGenerator` is required (expected: yes, mirroring M030/M033, since this is a creation capability minting a new identity); exact result contract (`DomainIdentity[EvidencePackageId]` expected, mirroring `CreateRunHandler`'s return, but not decided here); exact error-propagation treatment for the missing-Run FK-violation scenario (expected: transparent raw `FoundationError`, mirroring M033's own hostile-review-verified decision, but not decided here); the exact architecture-checker addition's evidence requirements.

---

## 15. Architecture-Boundary Considerations

`ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` does **not** currently grant `"evidence"` — verified directly. Exactly one narrow addition (`"evidence"`) will be required, mirroring M033's own precedent of adding `"run"` for the identical reason (a new aggregate package the `usecases` layer needs to import for the first time).

---

## 16. Stop Conditions / Prohibited Expansion

No `EvidencePackage` retrieval or mutation beyond creation; no `Review` work; no retry policy; no composition root; no transport; no schema/migration change; no MILESTONE-037 work.

---

## 17. Governance Status

**Status:** `CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW`. Not approved. Not frozen.

**Next permitted action:** consolidated with M036 Design and Implementation per the active Macro Milestone Protocol; final disposition awaits MILESTONE-036 INDEPENDENT IMPLEMENTATION REVIEW.
