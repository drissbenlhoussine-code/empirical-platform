# MILESTONE-084 — Validation Results

What was executed, what it produced, and what it does not establish. Anything
that was not executed is listed as not executed rather than omitted.

> **Supersedes** the earlier version of this document, which reported the
> campaign before sections 5–9 had been run and before the M083 frozen-boundary
> correction. Conclusions it drew that are no longer accurate are marked below
> rather than deleted.

---

## 1. Quality gates

Each run separately and recorded by its own exit code. Chaining these behind
`&&` is how a failing gate was once recorded as passing in this campaign: the
short-circuit means only the first failure is visible and the rest are never
reached, so a reader sees one number that describes several commands.

| Gate | Command | Exit |
|---|---|---:|
| Format | `ruff format --check .` | 0 |
| Lint | `ruff check .` | 0 |
| Types | `mypy` (strict, 344 files) | 0 |
| Architecture | `python tools/check_architecture.py` | 0 |
| Frozen boundary | `python tools/check_frozen_paths.py` | 0 |
| Authority | `python tools/render_m084_authority.py --check` | 0 |
| File audit | `python tools/render_m084_file_audit.py --check` | 0 |
| Exhaustion | `python tools/render_m084_exhaustion_table.py --check` | 0 |

`render_m084_authority.py --check` needs the repository root importable
(`PYTHONPATH=.`), which is how the test suite and CI invoke it. Run without it,
it exits 1 on `ModuleNotFoundError: tools` — an invocation artifact, not a gate
failure, and recorded here because reporting it as a red gate would be as wrong
as reporting a red gate as green.

## Suppression accounting

Counted by `tokenize`, not by grep, so a comment is distinguished from a
docstring that quotes one. Across the whole base-to-head diff:

| Kind | Count | Where |
|---|---:|---|
| `# noqa` | 112 | tools/migrations 64, tests 31, src 17 |
| `# type: ignore` | 117 | 88 are `[arg-type]` on protocol test doubles |
| **Coverage pragmas** | **0** | none |
| **Skipped tests** | **0** | none |

`noqa` by rule: S603 (35) and S607 (33) on fixed subprocess argument vectors
with no shell; E501 (20) on long SQL and message strings; BLE001 (14) where an
attack harness must catch whatever the product raises in order to report it;
S608 (5); DTZ001 (3); E402 (2).

These are the numbers `tools/render_m084_exhaustion_table.py` prints, recounted
here rather than carried forward. An earlier revision of this table said 88 and
116 while the generated exhaustion row said 105 and 117: a hand-copied count
goes stale the moment the code moves, and this one had. The correction in §10a
added seven more `noqa` — six S603/S607 on fixed `git` and `detect-secrets`
argument vectors, one E501 — which is the difference between 105 and 112.

The two numbers that matter are the last two, and both are zero. **No coverage
line is excluded and no test is skipped.** Two `# pragma: no cover` markers did
exist in production code — see FIND-H5-01 below — and were removed rather than
justified, because both branches turned out to be reachable from a unit test.

The coverage floor is unchanged from the base commit; it was not lowered to
make anything pass.

---

## 2. Concurrency (§3)

`tests/integration/test_m084_concurrency.py` — 36 races, sequenced with
`threading.Barrier` and `threading.Event`. A barrier timeout is a failure bound,
never a proof of ordering: `sleep` is not used to establish that two things
raced.

Three repetitions, each on a database dropped and rebuilt through the full
migration history. The distinct `pg_database.oid` per repetition is the proof
the run started from a new database rather than a leftover one:

| Repetition | Database | oid | Result |
|---|---|---:|---|
| 1 | `empirical_conc_r1` | 1174427 | **36 passed** |
| 2 | `empirical_conc_r2` | 1176417 | **36 passed** |
| 3 | `empirical_conc_r3` | 1178404 | **36 passed** |

Identical test-id digest `0dbbdc6fd184f7bf` across all three. Anti-vacuity:
dropping `uq_trade_approval_decision_one_per_proposal` failed exactly the two
races that depend on it; restoring returned 36 passed with an empty diff.

## 3. Mutation campaign (§4)

27 of 27 families detected. Full matrix in `mutation-matrix.md`. Three defects
found and fixed — an unreachable NO_TRADE reason, an untested approval binding,
and the harness measuring stale bytecode.

## 4. Hostile review (§5)

Five formally separate passes, 183 executed attacks, 0 outstanding findings.
Full matrices in `hostile-review.md`.

| Pass | Adversary | Attacks | Minimum | Findings |
|---|---|---:|---:|---:|
| 1 | Scientific authority | 27 | 25 | 0 |
| 2 | Database adversary | 51 | 40 | 0 |
| 3 | Trading-risk adversary | 39 | 35 | 0 |
| 4 | Operator and product | 34 | 30 | 0 |
| 5 | Software governance | 32 | 30 | 0 |

An attack is code that runs. `DEFENDED` requires the refusal to name the rule
the attack was aimed at — an attack that fails on a typo in its own SQL has
proved nothing, and crediting that as a defence is the easiest way to build a
hostile review that finds nothing and means nothing.

## 5. Performance and scale (§6)

Full data, per-scale query plans and lock measurements in
`performance-results.md`. Each scale ran on its own database rebuilt through
the full migration history, with its own `pg_database.oid`.

FIND-P-01: the operator's queue was a sequential scan of the whole table plus a
top-N sort to return 50 rows — 6.6 ms and 834 shared buffers at 25,000 rows, on
a table nothing is ever deleted from. `ix_trade_proposal_prepared_queue` makes
it 0.163 ms and 4 buffers, flat across every scale.

`counts_by_status` remains linear (0.12 ms at 0 rows, 5.2 ms at 25,000). That
is inherent to a GROUP BY over every row and is recorded as a measured
characteristic rather than hidden behind a speculative index.

## 6. Broker research (§7)

See `broker-and-market-data-research.md` and
`operator-verification-checklist.md`. All three vendors' documentation domains
are blocked by this container's network policy; GitHub and PyPI are not, so
Alpaca's and IBKR's own published packages were read directly. Every fact
carries its verification tier and the conclusion is marked **CONDITIONAL**.

**No broker was contacted. No account, credential, subscription, agreement or
order of any kind.**

---

## 7. Regression, four modes (§8)

### PostgreSQL ON

Base (`707161a`) and candidate each on their own freshly created database, then
the failure sets diffed. A first comparison against a reused database was
discarded as not like-for-like.

| Run | Result |
|---|---|
| Base, `empirical_base` | 24 failed, 3153 passed, 14 skipped, 44 errors |
| Candidate, `empirical_cand2` | 25 failed, 3838 passed, 16 skipped, 44 errors |

Set difference after correction: candidate has no failure base does not, except
transient file-audit drift since regenerated; base carries one coverage
shortfall candidate does not. The remaining 24 failures and 44 errors reproduce
**identically at base** (predominantly `dataset bundle tamper detected`) and are
**not M084's**. Established by execution at the base commit, not by argument.

Before that correction the candidate carried 44 additional M083 failures — see
FIND-R-01 and FIND-R-02 — which **CI never saw, because the foundation workflow
runs no PostgreSQL and skips every one of those tests.** That is a real gap in
the CI signal and is stated here rather than left implicit.

### PostgreSQL OFF

| Run | Result |
|---|---|
| Base | 8 failed, 2497 passed, 718 skipped, 12 errors |
| Candidate | 10 failed, 2925 passed, 1003 skipped, 12 errors |

Set difference: only the file-audit matrix drift, since regenerated.

### Clean database through the full migration history

`empirical_fresh`, created empty: **20 migrations up**, 20 down to base, 20 up
again, ending at `a3f7c21d9b04 (head)` with 55 tables in `public`.

### Clean installed wheel

`python -m build --wheel`, installed into a throwaway virtualenv with nothing
else in it, verified to import from `site-packages` and not from the source
tree. All 15 M084 console scripts present.

Two packaging facts found here and recorded rather than smoothed over. The base
install has no SQLAlchemy, because persistence is an optional extra — correct
pre-existing packaging, and `validate-trading-configuration`, the one command
that touches no database, works without it. And a bare `python3` on this
machine is 3.11 while the wheel requires ≥3.13, so the walkthrough's first run
installed nothing and diagnosed the same failure fifteen times; preparation now
aborts instead.

---

## 8. Operator walkthrough (§9)

`tools/m084_operator_walkthrough.sh`, run entirely through console scripts from
the installed wheel against a database rebuilt through the full migration
history. **18 steps, all at their expected exit code.**

A step that expects a refusal is as much a pass as one that expects success;
accepting "0 or nonzero, either is fine" would make the walkthrough
unfalsifiable.

Steps 1–15 are the operator's own path: validate a policy offline, watch a
leveraged policy be refused, store it, read it back, open an evaluation context
bound to the M083 watermark, evaluate, read the proposal, list the queue, read
system status, approve as a human, issue the one intent, read it back as
NOT_SUBMITTED, watch a second intent be refused, read the audit chain, and check
the kill switch.

### Three NO_TRADE demonstrations, three distinct reasons

| # | Input | Reported reason |
|---|---|---|
| 16 | A `DELAYED` feed | `MARKET_DATA_NOT_REAL_TIME` |
| 17 | Average daily volume below the floor | `LIQUIDITY_INSUFFICIENT` |
| 18 | A symbol not on the watchlist | `INSTRUMENT_NOT_WATCHLISTED` |

Each prints every check evaluated, not only the reported reason.

---

## 9. Frozen M083 boundary (§10)

Two results, obtained separately. Neither substitutes for the other.

**FROZEN M083 ACCEPTANCE — PASS.** `tools/m084_frozen_m083_acceptance.py`
checks the frozen commit out into its own git worktree, where the migration
head *is* M083, creates its own database, and runs M083's three unmodified
PostgreSQL suites there: **51 passed**, on a database whose fresh
`pg_database.oid` is recorded per run.

**M084 COMPATIBILITY — PASS.** `tests/integration/test_m084_m083_compatibility.py`,
12 tests M084 owns, at the M084 head.

**A measured limitation, stated rather than repaired away.** M084's
`evaluation_context` carries a foreign key to `evaluation_evidence_watermark`,
and PostgreSQL refuses to `TRUNCATE` a table a foreign key references *whether
or not the referencing table holds a single row*. The restriction is structural:
no ordering, cleanup or transaction shape lets M083's frozen reset statement run
while `evaluation_context` exists. At the M084 head that statement is
inexecutable, so M083's PostgreSQL suites cannot run there unmodified — which is
why frozen acceptance is obtained at M083's own revision instead.

The rejected repairs are on the record as tested, not merely asserted: adding
`CASCADE` does work and was wrong, because it makes "M083 still passes" mean
"M083 passes a test M084 rewrote"; dropping the foreign key trades a real
integrity guarantee for a green suite.

`tools/check_frozen_paths.py` now governs 27 M083-owned paths and refuses any
base-to-head change to them. Its exemption list is empty and asserted empty.

---

## 10. Findings

Every finding this campaign produced, with what was done about it.

| ID | Finding | Resolution |
|---|---|---|
| FIND-M-01 | `notional_limit` was an unreachable risk check; `NOTIONAL_ABOVE_LIMIT` a refusal the product could never make | Removed; bound proved by a sweep |
| FIND-M-02 | The approval↔proposal-version binding was untested; deleting it changed no test outcome | Two tests drive it directly |
| FIND-M-03 | The mutation harness measured stale bytecode, which can report a real detection as SURVIVED | Caches purged; `PYTHONDONTWRITEBYTECODE=1` |
| FIND-R-01 | M084's foreign key made M083's fixture `TRUNCATE` illegal | Frozen files restored; M084-owned coverage instead |
| FIND-R-02 | An M083 up/down/up helper aimed at the wrong revision once M084 was stacked above | Same; re-established under M084 ownership |
| FIND-P-01 | The operator queue was a sequential scan on an append-only table | Partial index; plan asserted, not timing |
| FIND-P-02 | The lock instrumentation looked for the wrong lock type and reported "not blocked" for real waits | Reports what it observed |
| FIND-W-01 | 14 of 15 operator commands answered a mistake with a traceback | One refusal shape; defects keep their traceback |
| FIND-H1-01 | `authority_version` was pinned with `minimum`/`maximum`, which this contract's validator does not implement — a decorative constraint | Pinned with `const`; schema may now only use enforced keywords |
| FIND-H3-01 | `order_type_permitted` was a second unreachable check; the configuration already guarantees it | Removed; invariant swept |
| FIND-H5-01 | Two production branches carried `# pragma: no cover` for a reason that did not hold — both are reachable from a unit test | Pragmas removed; both branches covered |
| FIND-CI-01 | The frozen-path guard compared `git diff BASE..HEAD`, which exits 128 in CI's shallow clone — the guard failed exactly where it runs unattended | Compares recorded content, no history needed |
| FIND-CI-02 | It then hashed file BYTES, which a Windows checkout legitimately changes for every non-Python path (`.gitattributes` pins `*.py` to LF) | Compares git blob ids: platform-independent by construction |
| FIND-CI-03 | The blob-id manifest broke the secret scan — and not only for itself: detect-secrets' entropy verdict depends on batch composition, so it changed the verdict for files clean for days | Narrow line allowlist plus one path-scoped rule, with three tests proving the plugin still fires — **SUPERSEDED IN PART by FIND-S-01** |
| FIND-S-01 | Two of FIND-CI-03's rules cleared a finding on the strength of a NAME: `BASE`, `_BASE`, `FROZEN_COMMIT` and JSON `"base"` carrying 40 hex characters were benign anywhere in the repository | The five commit ids are written in eight-character groups, so the scanner has nothing to report and the rules are gone; the manifest rule now checks the value against git's index |

---

## 10a. FIND-S-01 — what FIND-CI-03 got right, and the part that was wrong

**Superseded in part, not withdrawn.** FIND-CI-03's diagnosis stands unchanged
and is not restated here: detect-secrets' entropy verdict depends on the
composition of the scan batch, and a gate with that property will eventually
fail on a commit that did not cause it. So does its path-scoped rule for
`frozen-path-digests.json`, which is still in force. What is superseded is the
pair of repository-wide rules it used for the commit id.

**The defect.** `_BENIGN_HIGH_ENTROPY_LINE_PATTERNS` cleared any line of the
form `BASE|_BASE|FROZEN_COMMIT = "<40 hex>"`, and any JSON line
`"base": "<40 hex>"`, in **every file in the repository**. The reasoning was
that M084's five tools pin the campaign's base commit there, and a git commit id
is a public identifier rather than a credential. That is true of those five
lines and proves nothing about the rule: the name of a constant is evidence
about its author's intent and no evidence at all about its value. A real 40-hex
credential assigned to something called `BASE`, in any file, by anyone, later,
would have been cleared silently — and silently is the whole problem, because
the scanner's output is a count and nobody reads a zero twice.

**Reproduction.** At `e0907c4`, with the rules in place, `BASE = "<forty hex
characters that are no object in this repository>"` is reported by
detect-secrets and cleared by the filter. The same value on `API_TOKEN` is
reported. The difference between those two outcomes is the identifier, and
nothing else. The exact value is in
`tests/unit/test_secret_scan_targets.py::_INVENTED_FORTY_HEX`, written in
four-character groups there; it is not spelled out in this document, because a
40-hex token in a governance file would be a finding — correctly, now that no
rule clears one on the strength of the word next to it.

**The correction, in two parts.**

1. *The commit ids stopped looking like credentials, rather than being excused
   for looking like them.* All five definitions
   (`tools/check_frozen_paths.py`, `tools/render_m084_file_audit.py`,
   `tools/render_m084_exhaustion_table.py`,
   `tools/m084_frozen_m083_acceptance.py`,
   `tests/integration/test_m084_file_audit.py`) now hold the id in
   eight-character groups and join it, and `file-audit-matrix.json` records
   `base_groups` instead of `base` for the same reason — a generated JSON file
   cannot use implicit concatenation. No token in any of the six is a
   40-character hex string, so detect-secrets does not report them at all and no
   rule is consulted. Measured: the unfiltered scan flagged 50 files before and
   44 after; the six that left are exactly these.
2. *The rule that remained checks the value, not the shape.* A line in
   `external-review/MILESTONE-084/frozen-path-digests.json` is cleared only when
   its key is a path git tracks here **and** its value is the blob id git holds
   for that path, read from `git ls-files -s` — never from the value being
   judged. Where git cannot answer, the rule clears nothing: a filter that goes
   quiet when its evidence is unavailable goes quiet exactly where it is least
   watched.

**Negative controls, all executed.** `tests/unit/test_secret_scan_targets.py`
holds five names — `BASE`, `_BASE`, `FROZEN_COMMIT`, JSON `"base"`, and
`API_TOKEN` as the unchanged control — each carrying a 40-hex value that is no
object here, and each must still be reported. Three more hold the manifest rule
non-vacuous: an invented blob id is reported; a genuine blob id filed under the
wrong path is reported; the identical line in `config/credentials.json` is
reported. `tests/architecture/test_frozen_paths.py` adds four: every recorded
entry is a governed path, every recorded id is a real **blob** of this
repository, every recorded id is the object at the base commit where history is
available, and replacing one recorded id with an invented value makes the guard
report that exact path.

**Anti-vacuity on the real file, not a fixture.** One blob id in the committed
manifest was replaced with a value that is no object here; the repository scan
reported `frozen-path-digests.json:2`. The file was restored byte-for-byte —
blob `99a3788d4cbc` before and after — and the scan returned to zero findings.

---

## 11. Three CI failures, and what they were

Every gate in §1 was green locally while CI was red, three times. Each time the
environment was right and the check was wrong, and each was found by CI rather
than by reasoning — which is the argument for having it, and the reason "it
passes locally" is not a result.

The first two are FIND-CI-01 and FIND-CI-02 above: a shallow clone has no base
commit, and a Windows checkout has no LF. The third is FIND-CI-03, and it is the
one worth remembering: **a gate whose verdict depends on the composition of its
input will eventually fail on a commit that did not cause it.** Adding 27 blob
ids did not merely add its own findings; it moved detect-secrets' entropy
verdict for five unrelated files that had been clean for days. Those lines are
now deterministic regardless of what else is scanned — but by removal rather
than by allowance, which is FIND-S-01 in §10a: a value that is not
40 hex characters cannot be judged by a rule about 40 hex characters.

## 11a. A pre-existing platform condition, found and not fixed here

Running the whole suite on Linux to check this correction against `e0907c4`
produced **20 failures and errors on both trees, identically**. They are not
M084's and not this correction's: `tests/fixtures/m062_validation_study/…json`
and the M063/M064 fixtures record `_EXPECTED_SHA256` over the file's RAW BYTES,
and those constants were taken from a **CRLF** checkout. `.gitattributes` pins
only `*.py` to LF, so on Windows the bytes match and CI is green, while on Linux
the same tracked file hashes differently. Verified directly: the fixture's LF
bytes hash to `1b582de9…`, the same bytes with CRLF hash to `3289c380…`, which
is the recorded constant.

It is recorded rather than repaired because it belongs to three earlier
milestones and this mission's authority covers the secret scanner, M084's own
guards and tools, and M084's derived artifacts. The relevance to M084 is the
comparison itself: the failure sets at `e0907c4` and at the corrected head are
byte-identical, so the correction adds no failure and removes none.

## 12. What this does not establish

- Nothing here says the asserted quotes, accounts or sessions match what any
  market or broker showed. Every market input is operator-asserted.
- Nothing here is evidence of profitability, fillability, or execution quality.
- The performance numbers are single-node, loopback, warm-cache figures from a
  development container. They bound what the code does; they do not predict
  production hardware.
- The broker research conclusion rests on a search summary and is
  **CONDITIONAL** until the operator checklist is completed.
- Row-level refusals do not cover `TRUNCATE`, `DROP`, disabling a trigger, or a
  superuser. The authority contract states this as `false`, and hostile attack
  A1-11 demonstrates the `TRUNCATE` succeeding rather than taking the
  disclaimer's word for it.
- CI runs no PostgreSQL. Every PostgreSQL test in this repository is skipped
  there, so a green CI run is not evidence that the database rules hold.
