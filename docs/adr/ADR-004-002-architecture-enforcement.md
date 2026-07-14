# ADR-004-002 Architecture Enforcement

Decision: Module boundaries are enforced by a repository-local AST checker.

Rationale: A local checker avoids adding an architectural dependency solely for boundary enforcement and can encode the exact MILESTONE-003 dependency graph.

Reversal condition: If import graph complexity grows, replace with a dedicated architecture-testing tool after evaluation.

