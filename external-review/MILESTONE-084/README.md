# MILESTONE-084 — Decision-to-Approval Product Core

**Candidate for Owner review. Not merged, not frozen, not approved.**

## What this milestone is

The step where the platform stops describing research and starts producing
something a person acts on: a configured policy, an evaluation bound to the
evidence it consumed, a derived trade proposal or a reasoned refusal, one
explicit human decision, and — only downstream of that decision — one
broker-neutral order intent that **cannot be sent anywhere**.

## What it is technically incapable of

MILESTONE-084 has no order-submission capability. That is not a policy this
code follows; it is a property of what exists:

- `SubmissionState` declares exactly one member, `NOT_SUBMITTED`. There is no
  submitted state to transition to.
- `submission_state` is constrained to `NOT_SUBMITTED` in the database, and
  intents are append-only, so a stored row cannot acquire one either.
- The intent repository's public surface is exactly `{issue, get,
  for_proposal}`. No `submit`, no `send`, no `mark_submitted`.
- No module of the package may import a client capable of placing, modifying
  or cancelling an order. The rule is enforced statically across **every**
  module, and four negative fixtures prove it fires.

No credential was obtained, no account was opened, no API key was created, and
no endpoint was contacted anywhere in this milestone.

## Where to start reading

| File | What it is |
|---|---|
| `current-authority.md` | **The single active statement of what M084 establishes.** Generated; do not edit. |
| `current-authority.json` | The canonical contract. The only source of authority. |
| `current-authority.schema.json` | The closed schema. A claim it does not name cannot be added; a claim removed fails the exact item counts. |
| `scope-and-design.md` | What was built and why each refusal is where it is. |
| `validation-results.md` | What was executed and what it measured, and every finding this campaign produced. |
| `exhaustion-table.md` | One row per required campaign item. Generated: each status is DERIVED from the evidence, so a row cannot be typed into passing. |
| `broker-and-market-data-research.md` | Phase C. Research only, with every fact carrying its verification tier and the conclusion marked CONDITIONAL. |
| `operator-verification-checklist.md` | The exact URLs and questions for what this environment could not verify. No row is complete. |
| `changed-files.txt` | The exact diff surface. |

### The campaign artifacts

All generated from their own runs and guarded by a `--check` gate, so none of
them can drift from what it reports.

| File | What it is |
|---|---|
| `mutation-matrix.md` | All 27 mutation families: the rule weakened, the test that caught it, the failure, the byte-identical restore. Plus the three defects the campaign found. |
| `hostile-review.md` | Five formally separate adversarial passes, 183 executed attacks. An attack here is code that runs, and a refusal counts only if it names the rule the attack was aimed at. |
| `performance-results.md` | Latency at 0 → 25,000 rows with median, p95, max and sample counts; a query plan per scale; row-lock waits under real contention. |
| `concurrency-results.md` | 36 races, three repetitions, each on a database rebuilt from nothing — proven by a distinct `pg_database.oid`. |
| `file-audit-matrix.md` | Every changed path, its owner and its purpose. A file added without being audited fails the render. |
| `frozen-path-digests.json` | The git blob id of every frozen M083 path as of the base commit. The frozen-path guard compares against this. |

Verify the generated artifacts:

```
PYTHONPATH=. python tools/render_m084_authority.py --check
python tools/render_m084_file_audit.py --check
python tools/render_m084_exhaustion_table.py --check
python tools/check_frozen_paths.py
python tools/check_architecture.py
```

Re-run the campaigns themselves (each needs a live PostgreSQL):

```
python tools/m084_mutation_campaign.py
python tools/m084_hostile_review.py --all
python tools/m084_frozen_m083_acceptance.py
bash tools/m084_operator_walkthrough.sh
```

## A limitation this package states rather than works around

M084's `evaluation_context` carries a foreign key to M083's frozen
`evaluation_evidence_watermark`. PostgreSQL refuses to `TRUNCATE` a table a
foreign key references — whether or not the referencing table holds a single
row — so M083's frozen reset statement is **inexecutable at the M084 head**, and
M083's PostgreSQL suites cannot run there unmodified.

The frozen files were left exactly as they are. Two results are produced
separately and neither stands in for the other: `m084_frozen_m083_acceptance.py`
runs M083's unmodified suites at M083's own revision, and
`test_m084_m083_compatibility.py` covers what M084 does to that schema at the
M084 head. `validation-results.md` §9 has the detail, including the repairs that
were considered and rejected.

## The one thing a reviewer should check first

Whether the document's claims are still true of the code. That is what
`tests/integration/test_m084_authority_contract.py` exists for: it checks the
schema is closed, that the prose is the deterministic rendering of the
contract, and — the part that actually matters — that each mechanical claim
holds against the code and migration that implement it. A contract can be
perfectly rendered, perfectly validated, and false; the third check is what
prevents that.
