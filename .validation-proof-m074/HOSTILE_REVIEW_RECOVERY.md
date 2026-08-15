# M074 — Fresh adversarial review (post-interruption recovery run)

Independent of `HOSTILE_REVIEW.md` and `HOSTILE_RE_REVIEW.md`, which were
produced before the interruption on the owner's Windows workstation. This pass
was run from scratch on Linux, on fresh clones, against a freshly created
PostgreSQL 16 instance. It found one real defect, which is fixed in this
branch; everything else below was checked and held.

**Verdict key:** PASS = checked and held. FAIL = defect found. FIXED = defect
found in this pass and repaired in this branch. NOTED = true, in scope, and
recorded for the owner rather than changed.

## Findings

**F1 — FIXED. Naive/aware `coverage_end` sentinel crashed candidate ordering.**
`_evaluate_compatibility` returned bare `datetime.min` (naive) for candidates
rejected at H1–H4, W, C, or empty `window_results`, while every candidate that
reached rule T got an aware timestamp from an M064 window. Both kinds were then
sorted through one datetime key in `find_compatible_historical_evidence`, so a
call holding one early-rejected and one late-rejected candidate raised
`TypeError: can't compare offset-naive and offset-aware datetimes`.
`BuildDailyResearchBriefHandler` catches it, so the brief still rendered — but
it rendered the "discovery failed … not a confirmed absence of compatible
evidence" warning and zero candidates, when the lookup had in fact succeeded
and both candidates had already been correctly classified INCOMPATIBLE with
reasons. Reproduced, fixed via the named aware `NO_COVERAGE_DERIVED`, and
covered by two regression tests.

**F2 — NOTED. `absence_reason` is present in the empty-evidence JSON branch and
absent from the populated branch.** A consumer that reads the key
unconditionally will `KeyError` on a brief that has candidates. Not changed —
the JSON contract is M074's to set and the owner should decide whether the key
becomes always-present-and-nullable.

**F3 — NOTED. Discovery issues one `find_portfolio_report_for` per M064 study.**
Classic N+1 against `portfolio_study`. Correct, deterministic, and negligible at
the current row counts; worth a single keyed fetch if the study table ever grows.

## Checks

### M063 exceptional repair (1–14)

| # | Check | Verdict |
|---|---|---|
| 1 | Fixture blob OID unchanged since M063 implementation (`800ecb19`) | PASS |
| 2 | Fixture bytes not modified by the repair | PASS |
| 3 | Committed blob digest = repaired seal on LF clone | PASS |
| 4 | Committed blob digest = repaired seal on `autocrlf=true` clone | PASS |
| 5 | Old seal `ca98478…` corresponds to no object in the git database | PASS |
| 6 | CRLF→LF normalisation reproduces the blob byte for byte | PASS |
| 7 | Repair diff is exactly 4 lines, one seal constant per file | PASS |
| 8 | No M063 domain, usecase, repository or migration file touched | PASS |
| 9 | `.gitattributes` `-text` scoped to one explicit path | PASS |
| 10 | `git check-attr text` = `unset` for the M063 fixture only | PASS |
| 11 | M063 freeze document not rewritten | PASS |
| 12 | Sealed `external-review/MILESTONE-063/` package untouched | PASS |
| 13 | 14 previously-failing M063 unit tests now pass on LF | PASS |
| 14 | Exception documented in a standalone governance record | PASS |

### M064 / M065 preservation (15–24)

| # | Check | Verdict |
|---|---|---|
| 15 | Every M064 fixture blob OID identical master vs branch | PASS |
| 16 | Every M065 fixture blob OID identical master vs branch | PASS |
| 17 | No M064 test file modified by this branch | PASS |
| 18 | No M065 test file modified by this branch | PASS |
| 19 | `git check-attr text` = `unspecified` for all M064 fixtures | PASS |
| 20 | `git check-attr text` = `unspecified` for all M065 fixtures | PASS |
| 21 | M064 bundle still materializes to `af996c09…` under `autocrlf=true` | PASS |
| 22 | M064 `MANIFEST_HASHES.json` unmodified | PASS |
| 23 | M064 `membership_manifest_hash` proven line-ending independent | PASS |
| 24 | Earlier record's claim about `membership_manifest.json` corrected | FIXED |

### Freeze-impact on earlier milestones (25–34)

| # | Check | Verdict |
|---|---|---|
| 25 | M067 migration `a3f7c81e4b96` AST-identical to master | PASS |
| 26 | M067 `test_m067_portfolio_study_lifecycle.py` AST-identical | PASS |
| 27 | M068 `portfolio_dependence_io.py` AST-identical | PASS |
| 28 | M068 `run_portfolio_dependence_evidence.py` AST-identical | PASS |
| 29 | No new migration revision added | PASS |
| 30 | No `create_table` / DDL added anywhere | PASS |
| 31 | No new table | PASS |
| 32 | Alembic revision graph unchanged | PASS |
| 33 | No frozen domain enum or vocabulary extended | PASS |
| 34 | No recorded historical outcome altered | PASS |

### M074 compatibility rule (35–52)

| # | Check | Verdict |
|---|---|---|
| 35 | H1–H4 short-circuit before coverage derivation | PASS |
| 36 | `None` M070 policy identity does not force a mismatch | PASS |
| 37 | W rejects `window_count < 2` | PASS |
| 38 | C rejects `INSUFFICIENT_SAMPLE` | PASS |
| 39 | Empty `window_results` rejected rather than crashing on `max()` | PASS |
| 40 | F (future evidence) evaluated before S (staleness) | PASS |
| 41 | Staleness boundary is strict `> 90 days` | PASS |
| 42 | Exactly-90-days is not stale | PASS |
| 43 | U1 fed from evaluated symbols only | PASS |
| 44 | U2 fed from eligible symbols only | PASS |
| 45 | U2 superset semantics, not equality | PASS |
| 46 | Empty `requested_universe` rejected explicitly | PASS |
| 47 | Unknown `InstrumentId` dropped, not crashed on | PASS |
| 48 | Missing instrument master degrades to no resolution | PASS |
| 49 | Rule L drops an M067 report whose lineage does not match | PASS |
| 50 | Rule L enforced in the pure rule, not only in the adapter | PASS |
| 51 | At most one candidate carries `is_selected` | PASS |
| 52 | Mixed early/late rejections order without raising | FIXED (F1) |

### Determinism (53–60)

| # | Check | Verdict |
|---|---|---|
| 53 | `_resolve_symbols` returns a sorted, de-duplicated tuple | PASS |
| 54 | Ordering is coverage_end DESC then runtime_id ASC | PASS |
| 55 | Tiebreak on equal coverage is deterministic | PASS |
| 56 | COMPATIBLE candidates ordered ahead of the rest | PASS |
| 57 | No `set` iteration order leaks into output | PASS |
| 58 | No wall-clock or RNG read in the compatibility path | PASS |
| 59 | Second independent PostgreSQL pass reproduces the first | PASS |
| 60 | Repeat full-suite run reproduces identical counts | PASS |

### Persistence boundary (61–72)

| # | Check | Verdict |
|---|---|---|
| 61 | Adapter issues `SELECT` only — no INSERT/UPDATE/DELETE/DDL | PASS |
| 62 | All SQL parameters bound (`:rid`), no string interpolation | PASS |
| 63 | No f-string or `%`-formatted SQL in the adapter | PASS |
| 64 | Read path does not mutate the M070 ResearchSession | PASS |
| 65 | Timestamps read from `TIMESTAMPTZ`, so aware, never naive | PASS |
| 66 | Money read as `Decimal`, never float | PASS |
| 67 | Protocol lives in `decision_candidate`, concrete in `shared.persistence` | PASS |
| 68 | `usecases` does not import `shared.persistence` | PASS |
| 69 | Architecture checker passes on the whole repo | PASS |
| 70 | Negative architecture fixture still reports its 32 violations | PASS |
| 71 | Runtime exposes the query repo as a read-only property | PASS |
| 72 | Absent query repository degrades to no section, not a crash | PASS |

### Honesty and scope discipline (73–82)

| # | Check | Verdict |
|---|---|---|
| 73 | Honesty banner present in both JSON and text renderings | PASS |
| 74 | Banner disclaims today's portfolio, open positions, live risk | PASS |
| 75 | Banner disclaims paper account and profitability | PASS |
| 76 | Banner disclaims survivorship-bias elimination | PASS |
| 77 | Discovery failure distinguished from confirmed absence | PASS |
| 78 | Absence case names the commands that would produce evidence | PASS |
| 79 | No live/paper/broker/order vocabulary in M074 code | PASS |
| 80 | No M068 dependence surface introduced | PASS |
| 81 | `--no-historical-evidence` honoured on both daily paths | PASS |
| 82 | Flag suppresses the lookup itself, not just the rendering | PASS |

### Toolchain and supply chain (83–89)

| # | Check | Verdict |
|---|---|---|
| 83 | `ruff format --check` clean (557 files) | PASS |
| 84 | `ruff check` clean | PASS |
| 85 | `mypy` clean (280 source files) | PASS |
| 86 | `pip-audit` reports no known vulnerabilities | PASS |
| 87 | Secret scan: 957 targets, 0 findings | PASS |
| 88 | `python -m build` produces sdist and wheel | PASS |
| 89 | Coverage floor 79% not lowered; 80.01% / 91.93% achieved | PASS |
