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
| `validation-results.md` | What was executed and what it measured. |
| `broker-and-market-data-research.md` | Phase C. Research only, with its limitations stated up front. |
| `changed-files.txt` | The exact diff surface. |

Regenerate and verify the authority document with:

```
python tools/render_m084_authority.py --check
```

## The one thing a reviewer should check first

Whether the document's claims are still true of the code. That is what
`tests/integration/test_m084_authority_contract.py` exists for: it checks the
schema is closed, that the prose is the deterministic rendering of the
contract, and — the part that actually matters — that each mechanical claim
holds against the code and migration that implement it. A contract can be
perfectly rendered, perfectly validated, and false; the third check is what
prevents that.
