# MILESTONE-027 - Application Command/Handler Contracts Implementation Scope

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-IMPLEMENTATION-SCOPE |
| Title | Application Command/Handler Contracts Implementation Scope |
| Status | Implementation in progress against frozen design |
| Frozen design | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN_FREEZE.md` |

## 2. Purpose

Confirm the frozen M027 design (Version 1.1, Sections 1-24) can be
implemented exactly as specified, with no contradiction discovered against
live repository evidence, before writing source code.

## 3. Confirmed Implementable Without Design Contradiction

Read in full immediately before implementation: the frozen corrected
Design, `shared/contracts/repository.py`, `shared/contracts/mapping.py`,
`shared/contracts/__init__.py`, and `pyproject.toml`'s `[tool.mypy]` and
`[tool.pytest.ini_options]` sections. No contradiction was found between
the frozen design and the live state of any of these files:

- The exact frozen contravariant/covariant contract type-checks cleanly
  against the project's live `mypy --strict` configuration, exactly as the
  design's own correction-round experimentation predicted.
- `shared/contracts/__init__.py`'s existing `__all__` pattern accommodated
  one new alphabetically-placed export (`CommandHandler`) with no structural
  change.
- All five frozen negative/positive typing fixtures, when checked against
  the real (not stubbed) `CommandHandler` implementation via the exact
  frozen `python -m mypy --config-file <pyproject.toml> <fixture>` command,
  produced exactly the diagnostics the frozen design specified.
- None of the five fixture filenames match pytest's default `test_*.py`/
  `*_test.py` collection glob, confirmed directly against the live
  `pyproject.toml`.

## 4. Scope Confirmed

Implementation is scoped to exactly:

- one new file, `src/empirical_platform/shared/contracts/command.py`;
- one new export in `src/empirical_platform/shared/contracts/__init__.py`;
- five typing fixtures under `tests/typing_fixtures/command_handler/`;
- two new unit test files
  (`tests/unit/test_command_handler_typing.py`,
  `tests/unit/test_command_handler_contract.py`);
- implementation documentation and a checkpoint update.

## 5. Non-Goals (unchanged from Design)

Any concrete `Command`/`CommandHandler` implementation, application service
orchestration, transaction ownership decisions, a handler-level error
hierarchy, a `Command` marker type, a dispatcher or runtime registry, retry
policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze,
market-data/vendor/trading/campaign execution behavior, and any
MILESTONE-028 work.

## 6. Final Status

```text
M027 IMPLEMENTATION SCOPE CONFIRMED - NO DESIGN CONTRADICTION FOUND
```
