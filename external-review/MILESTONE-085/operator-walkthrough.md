# MILESTONE-085 — Installed-Wheel Operator Walkthrough

Run at `2026-09-10T00:06:35.837490+00:00` (UTC) against a wheel installed into a
throwaway virtualenv **outside the source tree**. Every command below is an installed
console script; none is `python -m` against `src/`.

**30 steps. 0 off their declared exit code. 5 blocked.**

Each step declared its expected exit code BEFORE it ran. A step expecting a refusal is
as much a pass as one expecting success.

| # | Step | Expected | Actual | Status |
|---|---|---|---|---|
| 01 | validate a policy file, touching no database | `0` | `0` | **PASS** |
| 02 | a leveraged policy is refused before it can be stored | `1` | `1` | **PASS** |
| 03 | verify the paper environment is the pinned paper host | `0` | `0` | **PASS** |
| 04 | read the paper account, read-only, and store one snapshot | `0` | `0` | **PASS** |
| 05 | store the policy as version 1 | `0` | `0` | **PASS** |
| 06 | open an evaluation context, binding it to the M083 watermark | `0` | `0` | **PASS** |
| 07 | NO_TRADE 1 of 3 -- a feed that is not real time | `0` | `0` | **PASS** |
| 08 | NO_TRADE 2 of 3 -- liquidity below the configured floor | `0` | `0` | **PASS** |
| 09 | NO_TRADE 3 of 3 -- an instrument off the watchlist | `0` | `0` | **PASS** |
| 10 | evaluate one instrument and derive a proposal | `0` | `0` | **PASS** |
| 11 | a human approves -- the one command no automation may run | `0` | `0` | **PASS** |
| 12 | derive the single order intent the approval permits | `0` | `0` | **PASS** |
| 13 | read the intent back -- NOT_SUBMITTED | `0` | `0` | **PASS** |
| 14 | the paper execution status of an untouched intent | `0` | `0` | **PASS** |
| 15 | dispatch WITHOUT any authorization is refused | `1` | `1` | **PASS** |
| 16 | freeze the submission preview against real broker evidence | `0` | `0` | **PASS** |
| 17 | authorizing with a WRONG fingerprint is refused | `1` | `1` | **PASS** |
| 18 | a human authorizes that exact fingerprint | `0` | `-` | **BLOCKED** |
| 19 | dispatch the one authorized order | `0` | `-` | **BLOCKED** |
| 20 | reconcile using the same client order id | `0` | `-` | **BLOCKED** |
| 21 | cancel the acknowledged order | `0` | `-` | **BLOCKED** |
| 22 | reconcile again, to a terminal state | `0` | `-` | **BLOCKED** |
| 23 | the complete audit history behind this intent | `0` | `0` | **PASS** |
| 24 | the paper dispatch queue | `0` | `0` | **PASS** |
| 25 | engage the execution kill switch | `0` | `0` | **PASS** |
| 26 | dispatch is refused while the kill switch is engaged | `1` | `1` | **PASS** |
| 27 | engaging an already-engaged switch writes nothing | `0` | `0` | **PASS** |
| 28 | lift the execution kill switch | `0` | `0` | **PASS** |
| 29 | after a fresh process, the state still comes from the database | `0` | `0` | **PASS** |
| 30 | an unknown intent is a refusal, not a traceback | `1` | `1` | **PASS** |

## Blocked steps

**Reason:** the preview refuses authorization on real broker evidence: the quote is 14777s old, older than the 60s limit

These steps need an authorizable preview, which needs a fresh quote. The
freshness tolerance was NOT widened to manufacture one -- that is the control
this milestone exists to demonstrate, and weakening it to produce a green
walkthrough would make the walkthrough worthless. See
`paper-acceptance-results.md` for the measured numbers.

