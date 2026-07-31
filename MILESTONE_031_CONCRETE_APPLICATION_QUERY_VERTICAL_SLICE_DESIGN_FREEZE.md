# MILESTONE-031 - Concrete Application Query Vertical Slice Design Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-031 design following independent hostile design review. It authorizes MILESTONE-031 implementation to begin. It does not itself constitute implementation authorization for anything beyond what Section 8 below specifies.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `26b1bf3ef3733c75d230009f0614d5dcf98f7779` |
| Milestone | MILESTONE-031 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `64682d1790ed3efacbdbdb6d99b3f3b4e7bbee90`) |
| M031 scope | APPROVED_AND_FROZEN (scope commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`, freeze commit `b31b664e9395aa0a988ccd1aecc21d6b06436d39`) |

Verified directly: zero changes to `src/`, `tests/`, or `tools/check_architecture.py` between M030's implementation-freeze commit (`64682d1`) and this freeze's authoritative HEAD (`26b1bf3`). M020-M030 remain exactly as frozen.

---

## 4. M031 Design-Candidate Commit

**Commit:** `f73b924d3c36e4796087aa4bb889a8dcde7b548e` (`docs: define M031 campaign retrieval design candidate`)

**Hash-recording commit:** `26b1bf3ef3733c75d230009f0614d5dcf98f7779` (`docs: record M031 design candidate commit hash`)

**Design document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md`

**Verified unchanged since review:** `git diff f73b924 HEAD -- MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` is empty. The design document's last modifying commit is `f73b924`, its own creation commit — the exact commit the independent review evaluated. No edit occurred between independent review and this freeze. No implementation file (`src/empirical_platform/usecases/get_campaign.py` or equivalent) exists anywhere in the repository.

---

## 5. Independent Design-Review Decision

**Decision: M031 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS**

The independent hostile design review verified every load-bearing decision (identity semantics, return contract, repository interaction, not-found/error behavior, revision-metadata treatment, architecture-checker impact) directly against actual frozen source — not the design's own claims — and found zero CRITICAL and zero MAJOR findings. Three MINOR, non-blocking findings were raised and are resolved by this freeze (Section 6).

---

## 6. Non-Blocking Observations (Resolved by This Freeze)

**M031-DESIGN-REVIEW-0001:** Design Section 9's field-justification prose stated that `identity` and `scope_statement` are "exactly the two fields `CreateCampaignCommand` accepts as input," which imprecisely equates `CreateCampaignCommand`'s raw-string fields (`campaign_governance_id: str`, `scope_statement: str`) with `CampaignSnapshot`'s value-object fields. Resolved: the actual round-trip symmetry is between `CreateCampaignHandler`'s *return value* (`campaign.identity`, a `DomainIdentity[CampaignId]`) and `GetCampaignQuery`/`CampaignSnapshot.identity` — correctly reflected everywhere else in the design (Sections 3, 6, 7, 9's own type declarations). This freeze record states the corrected framing; the design document's exact frozen text is not modified (Section 7 of this document; the design document remains byte-identical to the reviewed candidate).

**M031-DESIGN-REVIEW-0002:** Design Section 17.F phrased the PostgreSQL integration test's seed mechanism as an unresolved choice ("using the existing M030 `CreateCampaignHandler` (or the equivalent direct `CampaignRepository.add()` call...)"). Resolved: both alternatives are already-frozen, already-exercised mechanisms (verified in `tests/integration/test_m030_create_campaign_usecase.py` and `tests/integration/test_m023_postgres_repositories.py`) that produce identical persisted state; implementation may use either without any architectural consequence. This freeze does not mandate one over the other, since neither choice reopens any frozen decision.

**M031-DESIGN-REVIEW-0003:** Only 4 of the 10 design questions the M031 scope freeze (Section 12) anticipated were labeled by number in the design document ("Design Question 1", "4", "6", "9"); the remaining six (handler location, repository dependency, repository interaction, validation ownership, `QueryEntryPoint` binding, PostgreSQL evidence strategy) were substantively resolved without an explicit numeric label. Resolved: this freeze record confirms, by direct cross-reference against the M031 Scope Freeze's exact Section 12 list, that all ten items are answered in substance (Section 8 below maps each to its design-document section). No content gap exists — only a labeling/navigation gap, which does not require correcting the frozen design document.

---

## 7. Owner Approval

I, the owner, declare the MILESTONE-031 design, as recorded in `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN.md` at commit `f73b924d3c36e4796087aa4bb889a8dcde7b548e`, **APPROVED AND FROZEN** effective immediately upon this record.

**M031 DESIGN APPROVED_AND_FROZEN**

No further change to the frozen design is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit. The design document itself is not modified by this freeze — the three non-blocking observations are resolved by this record's clarifying text, not by editing the frozen candidate.

---

## 8. Frozen Design Decisions

The following are now frozen and binding on MILESTONE-031 implementation, with no remaining architectural invention permitted:

| # | Design Question | Frozen Decision | Design Document Section |
| --- | --- | --- | --- |
| 1 | Query shape | `GetCampaignQuery` — one field, `identity: DomainIdentity[CampaignId]` | Section 6 |
| 2 | Handler location | `GetCampaignHandler`, same module as the query: `src/empirical_platform/usecases/get_campaign.py` | Section 7 |
| 3 | Repository dependency | Constructor injection of `CampaignRepository` only — no `RuntimeIdentifierGenerator` | Section 7 |
| 4 | Return shape | New narrow immutable value `CampaignSnapshot` (`identity`, `scope_statement`, `state`) — not `Campaign`, not `LoadedAggregate[Campaign]` | Section 9 |
| 5 | Repository interaction | Exactly one `CampaignRepository.get()` call; no pre-read, no secondary lookup, no `add()`/`save()` | Section 10 |
| 6 | Not-found behavior | Fully transparent propagation of `AggregateNotFound` and any other repository exception — no translation, no wrapping | Section 11 |
| 7 | Validation ownership | No validation in the query or handler; entirely delegated to already-frozen `DomainIdentity`/`Identifier`/repository validation | Section 12 |
| 8 | `QueryEntryPoint` binding | Direct construction, `QueryEntryPoint(GetCampaignHandler(...))`, in tests only — no production composition code | Section 13 |
| 9 | Architecture-checker impact | None — every required import (`campaign`, `identifiers`, `shared`) already resolves under the existing `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` pair | Section 15 |
| 10 | PostgreSQL evidence strategy | Reuse the exact opt-in fixture pattern `tests/integration/test_m030_create_campaign_usecase.py` already established; no new schema, container, or composition wiring | Section 18 |

**Exact frozen module/type names:** `GetCampaignQuery`, `GetCampaignHandler`, `CampaignSnapshot`, module `src/empirical_platform/usecases/get_campaign.py`.

---

## 9. Implementation Authorization Boundaries

**Authorized:**

- Creating `src/empirical_platform/usecases/get_campaign.py` with exactly `GetCampaignQuery`, `GetCampaignHandler`, and `CampaignSnapshot` as frozen in Section 8.
- Unit tests (query construction, handler behavior with deterministic recording/failing fakes), contract tests (`QueryHandler` conformance), architecture tests (existing `test_current_source_tree_respects_boundaries`, no new fixture required per Section 8 row 9), and PostgreSQL integration tests, per Design Section 17.
- An External Review Package for MILESTONE-031 implementation, mirroring M030's established structure.

**Not authorized by this freeze:**

- Any deviation from the frozen names, module placement, field shapes, dependency style, return type, repository-call sequence, or error-propagation behavior in Section 8.
- Any architecture-checker change (none is required; see Section 8 row 9).
- Any production composition-root code binding `GetCampaignHandler` to a runtime `QueryEntryPoint` outside of tests.
- Any modification to M020-M030 frozen contracts, source files, or governance documents.
- Any `Run`/`EvidencePackage`/`Review` command or query, any Campaign query beyond retrieval-by-identity, any additional Campaign command, any transport layer, any retry/optimistic-concurrency handling.
- Any MILESTONE-032 work of any kind.

---

## 10. Frozen Predecessor Authority (Unmodified, Reverified)

The following remain exactly as frozen, unmodified, verified directly against source at this freeze:

- `Campaign` aggregate and `CampaignScopeStatement` (M020) — `src/empirical_platform/campaign/aggregate.py`.
- `CampaignRepository` Protocol, including its existing `get()` signature (M020) — `src/empirical_platform/campaign/repository.py`.
- The concrete PostgreSQL Campaign repository adapter (M023) — `src/empirical_platform/shared/persistence/postgres_repositories/campaign_repository.py`.
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol (M028) — `src/empirical_platform/shared/contracts/query.py`.
- `QueryEntryPoint[QueryT, QueryResultT]` (M029) — `src/empirical_platform/application/query.py`.
- Everything M030 delivered: `CreateCampaignCommand`/`CreateCampaignHandler` (`src/empirical_platform/usecases/create_campaign.py`) and the `usecases` package's architecture-checker rules (`tools/check_architecture.py`).

Verified via `git diff --name-status 64682d1 HEAD -- src/ tests/ tools/check_architecture.py`: empty — zero changes to any of the above since M030's own implementation freeze.

---

## 11. Final Frozen State

```
M031_SCOPE_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_IMPLEMENTATION_STATUS=NOT_STARTED
M031_STATUS=DESIGN_APPROVED_AND_FROZEN
```

M020-M030 remain unchanged and untouched throughout M031's design lifecycle.

---

## 12. Next Permitted Action

**MILESTONE-031 IMPLEMENTATION MISSION.**

This freeze record does NOT authorize:

- Any further M031 design change without the re-authorization process in Section 7.
- Any MILESTONE-032 work.
- Any implementation deviating from the frozen decisions in Section 8.

---

## 13. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-031 DESIGN FREEZE COMPLETE

═══════════════════════════════════════════════════════════════════════════════

M031 CONCRETE APPLICATION QUERY VERTICAL SLICE (CAMPAIGN RETRIEVAL)

Independent Review Decision:    M031 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS
Owner Decision:                 APPROVED_AND_FROZEN
Design Candidate Commit:        f73b924d3c36e4796087aa4bb889a8dcde7b548e
Design Freeze Commit:           (recorded in a following governance commit)

M020-M030:                      UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M031 Scope:                     APPROVED_AND_FROZEN
M031 Design:                    APPROVED_AND_FROZEN
M031 Implementation:            NOT_STARTED
M032:                           NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-031 IMPLEMENTATION MISSION

═══════════════════════════════════════════════════════════════════════════════
```
