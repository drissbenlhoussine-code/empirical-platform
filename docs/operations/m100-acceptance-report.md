# M100 — Final cloud release closure: acceptance report

Branch `claude/m100-cloud-release-closure-2e3q0o` (identical start point to
`claude/empirical-m100-launch-c492oz` @ `2b7046f`), target `release/v1-personal-paper`.
Contains PR #47's head (`ac5e649`), the earlier M100 corrections (`f23c851`, `2b7046f`) and the
closure work below. PR #47 is **not** merged separately; its content is in this branch's ancestry.
Nothing here was merged, deployed, or sent to a real broker.

## Defect register (final)

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| D1 | P1 | Daily loss / order count / simultaneous positions / exposure never enforced | **CLOSED (PAPER)** — `m100-trading-limits.md` |
| D2 | P1 | Duplicate entry across Prepares | CLOSED (earlier) + now also covered by the D1 gate |
| D3 | P1 | One-shot DAY exit never cancelled / re-armed | **CLOSED (PAPER)** — `m100-exit-state-machine.md` |
| D4 | P1 | DNS rebinding on console | CLOSED (earlier) |
| D5 | P1 | Deploy resume skipped gates | CLOSED (earlier) |
| D6 | P1 cond. | Autostart wrapper restarts console after step 5 | MITIGATED by runbook (unchanged) |

Independent review (four fresh reviewers, code only, no author conclusions) found **no P0**. Confirmed
P1s were fixed: broker read order (position/order snapshot race), a prepared-but-unclaimed re-arm
pair latching a generation after a transient failure, and a refused/erroring cancel stalling an exit
with no escalation. Reviewers also found test-evidence gaps (post-claim gate pass, terminal-Nth
attempt bound, NOT_SENT exclusion, restart test window); each now has a test that fails when the
production line is mutated. Remaining P2 items are listed under "Known limits".

## The 24-step acceptance matrix

No 24-step list exists in the repository, so this milestone **defined** one (the Owner's brief named
the categories: normal execution, rejection, partial fills, duplicate orders, outages, restarts, exits,
reconciliation). It is `tests/integration/test_m100_acceptance_matrix_postgres.py`: real PostgreSQL
Store B at the current head (v2 risk triggers) and Store C at its head, real approved-plan table,
every real handler, **simulated broker only**, controllable clock, no network. Result on the final
code: **24 passed**. Per-step facts: `m100-acceptance-evidence.json` (values in it are recorded by the
tests and partly constants the test asserts, not independent measurements).

| # | Proves |
|---|---|
| 1 | entry chain persists at head with governed v2 risk evidence; nothing sent |
| 2 | normal execution: one order, attempt recorded |
| 3 | reconciliation fills; broker holds the position |
| 4 | duplicate submit never sends a second order |
| 5 | two concurrent submitters → exactly one order (PostgreSQL claim) |
| 6 | broker rejection recorded; flat |
| 7 | partial entry fill blocks exit attribution until entry final |
| 8 | failure before send leaves nothing; NOT_SENT is not counted by the limit gate |
| 9 | ambiguous submission → UNKNOWN, never resent, reconciles |
| 10 | broker outage during limit verification blocks; no attempt; retry works |
| 11 | restart mid-uncertainty resumes from the database without resend |
| 12–15 | daily loss, order count, position slots, position/working-order conflicts block at submit |
| 16 | a claim not yet visible at the broker still holds its slot |
| 17 | engaged kill switch blocks entries, never exits |
| 18 | stop exit sells once; position verified closed |
| 19 | repeated ticks + restarts across re-arms: never overlapping, never oversold |
| 20 | unfilled exit → cancel requested → broker-confirmed → re-armed → fills |
| 21 | partial exit fill → remainder only re-armed; total sold == held |
| 22 | attempts exhausted → durable Store C event + entry kill switch in Store B |
| 23 | restart mid-cancel resumes without a second exit |
| 24 | broker outage then market close: no blind action; waits, then escalates |

Limits of this evidence: the broker is a deterministic simulation (it also ignores the day window
and stages P&L), so real-broker behaviour (fills, `last_equity` semantics, pending states) is
**unproven**. The post-claim limit pass and the exit machine are additionally covered by in-memory
unit tests (`tests/unit/test_m100_*`) including mutation-checked cases.

## The 25 Linux failures/errors — individually diagnosed (earlier run; 28 in this sandbox)

| Count | Tests | Cause | Resolution |
|---|---|---|---|
| 20 | M062 validation-study (6), M064 survivorship (12 errors), M065 historical-import tamper (1), M062 independent hash (1) | seals name the CRLF byte form of fixtures committed as LF (reproduced by hashing both forms) | `.gitattributes` `eol=crlf` for the three fixture sets; passes on Linux; unchanged on Windows |
| 2 | M098 control-token read | **portable defect + code**: POSIX branch reported ENOENT/symlink with the Windows wording | production fix in `console_control.py` (ENOENT → "no readable token"; symlink wording) |
| 1 | deploy integration (dummy console) | tool locates the listener with `ss` (iproute2) absent in the sandbox; passes with a stand-in `ss` | explicit `skipif` with reason (visible); Windows/ubuntu CI exercise it |
| 2 | `test_secret_scan_targets` | `detect_secrets` extra not installed | environmental; passes after `pip install .[security]` |
| 3 | `test_m085_base_pin` | shallow clone (merge-base unavailable) | environmental; pass after `git fetch --unshallow` |
| (2) | `m085_send_boundary_transport` pair | caused by M100's earlier change | fixed earlier; extended again for D1 evidence routes |

This sandbox also fails `test_m026…test_repr_does_not_expose_real_credentials` only because the local
throw-away DB user and password are both `empirical` (the test greps the repr for that word).

## Verification record (final code, Linux, Python 3.13, local PostgreSQL 16)

See the PR description for the exact SHA and CI results. Local: ruff format/check clean,
`tools/check_architecture.py` clean, mypy clean except 25 pre-existing Windows-only attribute errors
in `console_control.py` (CI type-checks on Windows). Unit+architecture suite green; the PostgreSQL
integration suites were run on the final code (details in the PR). Windows-specific behaviour is
verified only by Windows CI, not here.

## Known limits (P2, not release blockers for supervised PAPER)

* Exit orders count toward the daily order limit and appear in the same-symbol conflict check (can
  only make entries stricter). An in-flight *exit* not yet listed by the broker is not counted.
* Evidence read just before the send can age by the few reads that follow it; this system's own
  claims cannot race (durable), a manual broker-side order in that gap can.
* `suspended` broker status maps to a terminal exit state; a later broker reactivation would be an
  unmodelled edge.
* The exit machine's bounds (3 attempts, 90 s rest, 300 s no-reprice-near-close, 120 s cancel
  confirmation, 120 s unprotected) are engineering defaults awaiting Owner approval.
* LIVE remains impossible by construction and unassessed: `LIVE_READY = FAIL / not yet tested`.
