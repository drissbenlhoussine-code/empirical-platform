# MILESTONE-083 external review package

Kept intentionally small from the start, per the mission's explicit
instruction not to repeat M082's natural-language-claim-sweep growth. Two
classes only:

**`CURRENT_AUTHORITY`** — the single, closed, machine-readable source of what
M083 claims:

- `current-authority.json` — the contract.
- `current-authority.schema.json` — closed JSON Schema (`additionalProperties:
  false`, exact `minItems`/`maxItems`, `authority_version` frozen at
  `const: 1`) validated against by `tools/render_m083_authority.py`.
- `current-authority.md` — deterministic rendering of the contract. Generated;
  do not hand-edit. `python tools/render_m083_authority.py --check` fails if
  it has drifted from the JSON.

**`CURRENT_VALIDATION_EVIDENCE`** — supporting evidence, not authority:

- `scope-and-design.md` — candidate ranking and the selected schema/trigger
  design.
- `hostile-review.md` — design and implementation findings, corrections, and
  the two anti-vacuity checks (weaken the rule, show the attack pass; restore
  it, show the attack rejected).
- `validation-results.md` — focused and full-regression numbers, exact
  failing-ID diff against baseline, static/build gate results, and measured
  suppression counts.
- `changed-files.txt` — exact `git diff --name-only` against base
  `45016d7cb79381d9ff8f90a410f57d5a22473269`.

No natural-language claim sweep, banned-word list, banner grammar, or
annotation token exists anywhere in this package or in `tools/
render_m083_authority.py` — the closed schema is the only enforcement
mechanism, adopted directly from what M082's owner findings 20-28 converged
on rather than re-derived.
