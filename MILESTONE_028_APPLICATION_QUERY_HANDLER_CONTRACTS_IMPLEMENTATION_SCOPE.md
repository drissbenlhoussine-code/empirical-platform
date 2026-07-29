# MILESTONE-028 - Application Query/QueryHandler Contracts Implementation Scope

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-IMPLEMENTATION-SCOPE |
| Title | Application Query/QueryHandler Contracts Implementation Scope |
| Status | Implementation in progress against frozen design |
| Frozen design | `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN_FREEZE.md` |

## 2. Purpose

Confirm the frozen M028 design (Version 1.1, Sections 1-27) can be
implemented exactly as specified, with no contradiction discovered against
live repository evidence, before writing source code.

## 3. Confirmed Implementable Without Design Contradiction

Read in full immediately before implementation: the frozen corrected
Design, the frozen corrected M027 Design/Implementation (for the exact
precedent pattern), `shared/contracts/command.py`,
`shared/contracts/__init__.py`, and `pyproject.toml`'s `[tool.mypy]` and
`[tool.pytest.ini_options]` sections. No contradiction was found:

- The exact frozen contravariant/covariant `QueryHandler` contract
  type-checks cleanly against the project's live `mypy --strict`
  configuration, identically to `CommandHandler`'s verified case.
- `shared/contracts/__init__.py`'s existing `__all__` pattern accommodated
  one new alphabetically-placed export (`QueryHandler`) with no structural
  change and no disturbance to the existing `CommandHandler` export.
- All five frozen `query_handler` typing fixtures, when checked against the
  real implementation, produced exactly the diagnostics the frozen design
  predicted (identical to `CommandHandler`'s equivalent fixtures).
- The frozen design's Section 19 Items 5-6 (declared-relationship and
  structural-compatibility test obligations) required two additional
  fixtures not explicitly named by file in the Design — implemented as
  `tests/typing_fixtures/command_query_relationship/dual_satisfaction.py`
  (positive) and `mismatched_dual_satisfaction.py` (negative), verified
  directly against the real `CommandHandler`/`QueryHandler` implementations,
  producing exactly the behavior the Design's own correction-round
  experimentation predicted.
- None of the seven fixture filenames match pytest's default collection
  glob, confirmed directly against the live `pyproject.toml`.

## 4. Scope Confirmed

Implementation is scoped to exactly:

- one new file, `src/empirical_platform/shared/contracts/query.py`;
- one new export in `src/empirical_platform/shared/contracts/__init__.py`
  (preserving the existing `CommandHandler` export unchanged);
- five typing fixtures under `tests/typing_fixtures/query_handler/`;
- two relationship fixtures under
  `tests/typing_fixtures/command_query_relationship/`;
- three new unit test files
  (`tests/unit/test_query_handler_typing.py`,
  `tests/unit/test_query_handler_contract.py`,
  `tests/unit/test_command_query_relationship.py`);
- implementation documentation and a checkpoint update.

## 5. Non-Goals (unchanged from Design)

Any concrete `Query`/`QueryHandler` implementation, any declared
relationship/shared base/unification with `CommandHandler`, application
service orchestration, transaction ownership decisions, a query-level error
hierarchy, a `Query` marker type, a dispatcher or runtime registry, read-only
transaction enforcement, caching, pagination wrappers, result envelopes,
retry policy, APIs, workers, Audit runtime, Decision Candidate, Decision
Freeze, market-data/vendor/trading/campaign execution behavior, and any
MILESTONE-029 work.

## 6. Final Status

```text
M028 IMPLEMENTATION SCOPE CONFIRMED - NO DESIGN CONTRADICTION FOUND
```
