# Architecture Boundaries

The repository starts as a modular monolith. Module dependency rules are enforced by `tools/check_architecture.py`.

Business logic, empirical validation, B3 criteria, vendor adapters, campaign execution, Decision Candidate behavior, and Decision Freeze behavior are intentionally absent.

