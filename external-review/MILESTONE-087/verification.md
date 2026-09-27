# MILESTONE-087 — verification record

Branch `feature/m087-human-approved-position-exit`, parent `33f1eb33d8328f68785539d15bcdd9ec73c53708`
(the M086 head). Two code commits: the first candidate `909d402…` (the exit itself) and the
schema-boundary correction on top of it (§5 records its SHA and the exact-SHA runs). Every run
was executed on this machine (Windows 11, Python 3.13, PostgreSQL 16, psycopg pure Python over
libpq) against the disposable database `m085_pgon_b24c471` and temporary simulation stores. No
Alpaca endpoint was called; no M087 module imports the Alpaca client and the Alpaca adapter has
no exit implementation (architecture suite).

Evidence logs are post-processed by one rule only: raw 12-hex Alembic revision ids and 40-hex
commit ids are shown grouped (`<rev a7d3c9..4f26>`), and the secret scanner's own JSON output
lines are replaced by a note, because the repository's secret gate flags such tokens; nothing
else in a log is changed.

## 1. Results after the schema-boundary correction (`runs-worktree-2/`)

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused | all M087 suites (schema head 15, domain 25, simulation broker 14, console service 17, routes 9, architecture 15), all M086 unit/architecture suites, and `test_m085_paper_composition` (53), verbose by id | **see the log's last line (all passed)** | `runs-worktree-2/R1-focused.txt` |
| R2 PostgreSQL | 13 M085 suites + M086 console suite (at the M085 head) + M087 exit suite (8, at the M087 head) + M087 schema-ancestry suite (2), each on a schema rebuilt from the complete migration history | **527 passed, 0 failed** | `runs-worktree-2/R2-postgres.txt` |
| R3 full non-PostgreSQL suite (the repository's merge gate) | `pytest` with coverage | **4422 passed, 0 failed, 1269 opt-in skips; coverage 80.52 % ≥ 79 %** | `runs-worktree-2/R3-full-non-pg.txt` |
| R5 static | compileall, ruff format (790 files) / check, mypy (382 files), architecture checker + negative fixture, frozen paths (M083 27 + M084 69), `tests/architecture` 65 passed, authority renderers M082–M085, M084 file audit, `scripts/security.ps1`, build | **green** — the first run flagged raw revision ids inside the committed evidence logs of the previous commit; the logs were redacted as described above and the scan passes (§5) | `runs-worktree-2/R5-static.txt` |

There is no red test. The exhaustion table `--check` reports the M085 inventory stale at this
head until the docs regeneration commits, as at every head since M086.

## 2. Schema authority — two heads, kept apart

| Milestone | Pin | Guard | Accepts | Refuses |
|---|---|---|---|---|
| M085 | `M085_SCHEMA_HEAD = a7d3c9e14f26` — **unchanged, permanently the M085 revision** | `require_exact_m085_schema_head` (unchanged) | exactly the M085 revision | the M087 revision, older revisions, unknown newer, multiple heads, missing version, unreadable version |
| M087 | `M087_SCHEMA_HEAD = e7c1a9d3b5f2` | `require_exact_m087_schema_head` | exactly the M087 revision | the M085 head, older revisions, unknown newer, multiple heads, missing version, unreadable version |

Proven by `tests/unit/test_m087_schema_head.py` (both guards, the full refusal matrix, with a fake
service that answers only the revision query) and, against real PostgreSQL, by
`test_m087_position_exit_postgres.py::test_the_migration_upgrades_downgrades_and_re_upgrades_with_an_exact_head`.

**Composition — how each milestone chooses its guard.** `_operator_console_composition.py`
(M086): `compose_operator_console` → `require_exact_m085_schema_head(service)` → private
`_compose_verified_console(..., exits=None)`. `_position_exit_composition.py` (M087):
`compose_operator_console_with_exits` → `require_exact_m087_schema_head(service)` → the same
private helper with the exit runtime and exit console. The helper is not exported and has no
verifier parameter; no entrypoint or request can substitute a guard (architecture test
`test_each_milestone_composition_verifies_its_own_exact_schema_head`). The launcher composes the
M087 runtime. `ConsoleRuntime.verified_schema_head` records which head was verified.

**M086 regression.** M086 semantics remain "schema = M085 head": the M086 PostgreSQL suite runs
at the M085 head and passes unchanged in substance; at the M087 head the M086 public composition
REFUSES (`PaperSchemaHeadError`), proven in the migration test. M087 semantics are "schema = M087
head": at the M085 head the M087 composition refuses (`ExitSchemaHeadError`) and the M086 one
accepts with no exit path composed.

## 3. Migration ancestry and M085 compatibility — machine-checkable

- `e7c1a9d3b5f2.down_revision == a7d3c9e14f26`; it is the ONLY head and the ONLY revision above
  the M085 revision (`test_m087_schema_head.py::test_the_m087_revision_descends_directly…`).
- `m085-migration-manifest.json` records the sha256 of the 26 migration files at the published
  M085 head commit `54ae23c…`; `test_m087_schema_ancestry_postgres.py::test_the_m085_migration_files_are_byte_identical…`
  proves each is byte-identical on this branch and that exactly one file was added (the M087
  revision): nothing inserted into, nothing replaced inside, M085's history.
- `test_m087_schema_ancestry_postgres.py::test_m087_adds_objects_and_leaves_every_m085_object_byte_identical`
  captures, at the M085 head, every `paper_*` table, its columns, constraints, indexes, triggers
  and the definitions of every `paper_*` / `m085_*` trigger function (including
  `paper_execution_attempt_guard_update`, i.e. the closed transition table), upgrades to the M087
  head, and downgrades back: the catalog is **identical** after the upgrade and after the
  downgrade. The upgrade adds exactly six tables (`position_exit_preview`, `…_authorization`,
  `…_attempt`, `…_acknowledgement`, `…_reconciliation_round`, `…_event`) and eight functions
  (`m087_append_only`, seven `position_exit_*_guard_*`). **Zero M085 schema mutations, and no
  foreign key from any M087 table into any M085 table**: the link to the entry is a BEFORE
  INSERT guard that reads `paper_execution_attempt`, never a constraint on it.

## 4. Stacked-milestone test evolution — each M085/M086 test named, none blanket-ignored

`M085_SCHEMA_HEAD` was not moved and M085 was not redefined as M087. The tests below changed only
in how they reach the schema they test, or by stating the invariant they protected directly:

| Test / fixture | Before | After (this branch) | Replacement invariant |
|---|---|---|---|
| `tests/integration/_m085_support.py::build_engine` | always `upgrade("head")` | `build_engine(revision="head")`; callers testing an exact-head guard pass their milestone's revision | a guard is asked about its own milestone's schema, not a later one's |
| `test_m085_corrective_pass_postgres.py` (module engine and its three `upgrade` calls) | repository head | `M085_SCHEMA_HEAD` | `TestTheExactSchemaHeadIsRequired`, `test_the_corrective_migration_goes_down_and_up_again`, `test_the_upgrade_refuses_to_invent_a_binding_for_rows_that_exist` test M085 in isolation and pass unchanged in substance |
| `test_m085_reconciliation_rounds_postgres.py` (module engine and its `upgrade` call) | repository head | `M085_SCHEMA_HEAD` | `test_the_round_journal_migration_goes_down_and_up_again` asserts the M085 head it was written for |
| `test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_the_pinned_head_is_the_repository_migration_head` | pin == repository head | `…_is_the_m085_revision_and_the_repository_head_descends_from_it` | pin == the M085 revision (grouped literal); one head; the head's lineage contains the pin; every revision above it stacks on it; the pin's own down-revision is the reviewed corrective revision |
| `test_m085_authority_contract.py::TestTheContractReadsTheSqlInstalledAtHead::test_the_rendered_chain_is_exactly_the_m085_revisions_ending_at_head` and the `chain_sql` fixture | repository head is the last M085 revision; SQL rendered to `head` | `…_ending_at_the_m085_head`; SQL rendered to `M085_SCHEMA_HEAD` | the six reviewed M085 revisions end at `M085_SCHEMA_HEAD` (no insertion, no replacement); what sits above descends from it in one line and is not an M085 revision |
| `test_m086_operator_console_postgres.py` (module engine) | repository head | `M085_SCHEMA_HEAD` | M086 semantics: schema = M085 head; the public M086 composition is exercised as M086 |
| `test_m086_operator_console_postgres.py::test_a_second_launcher_process_is_refused_with_exit_code_2` | launcher at repository head | migrates to the repository head for its duration, back to the M085 head afterwards | the launcher composes the M087 runtime on this branch; the subject (the OS lock) is unchanged |
| `tests/unit/_m086_fakes.py::simulation_world` | one world | `exits=False` (default, the M086 console exactly) / `exits=True` (M087) | M086 unit suites run the M086 console; the two wording assertions changed in `909d402` are restored to the M086 text |
| `test_m086_operator_console_launcher.py` (two references) | `simulation_console_runtime` | `simulation_exit_console_runtime` | the launcher's stop-before-close order is asserted against the runtime it actually composes |

Not applicable on this branch, disclosed: the M085 paper CLI composition (`_paper_composition.py`,
unchanged) requires the M085 head and therefore refuses a database at the M087 head — exactly as
it refuses any non-M085 revision. It is not run against the console's database on this branch.

## 5. Exact-SHA confirmation (`58a7eaf6e84765c5abe0dfa804b79aac41ced2fc`, clean tree)

The correction commit differs from the `runs-worktree-2/` state (§1) only by two grouped
literals in `test_m087_schema_ancestry_postgres.py` (the M085 head commit id, for the secret
scanner) and the added M087 workflow steps; no source module changed.

| Stage | Result | Log |
|---|---|---|
| R1 focused (all M087 + M086 unit/architecture suites + `test_m085_paper_composition`, verbose by id) | **269 passed** | `runs-58a7eaf/R1-focused.txt` |
| R2 PostgreSQL boundary suites (M087 exit 8, M087 ancestry 2, M086 console 6, then the three M085 head-guard suites) | **INTERRUPTED by the host** after 29 tests had PASSED (M087 exit 8/8, ancestry 2/2, M086 6/6, corrective-pass 13 of its tests); the session stopped the run for low system memory. No failure was recorded before the interruption. The same suites passed in full at the worktree state (§1: 527 passed). | `runs-58a7eaf/R2-postgres-boundary.txt` (partial) |
| R5 static | compileall OK, ruff format 790 / check clean, mypy 382 files clean, architecture exit 0, negative fixture, frozen paths, `tests/architecture` 65 passed, renderers M082–M085 current, M084 file audit; **the `security.ps1` step crashed** (the `detect_secrets` subprocess exited without output while the host was reaping processes for memory) and the build step was killed. The standalone security scan run immediately before the commit on identical tracked content passed (1572 targets, none), and the build passed in §1. | `runs-58a7eaf/R5-static.txt` (partial) |

**Owed re-runs completed (Owner-authorised, low-memory, strictly sequential: one pytest process
at a time, no xdist), at the exact code of `58a7eaf` (local head `ca41b39`, code diff to
`58a7eaf` empty):**

| Stage | Result | Log |
|---|---|---|
| R2 part A — `test_m087_schema_head` 14, M087 exit 8, M087 ancestry 2, M086 console 6 (at the M085 head), `test_m085_paper_composition` 40, M085 corrective-pass 62, reconciliation rounds 15, authority contract 118 (the head-guard suites at the explicit M085 revision) | **265 passed, 0 failed** | `runs-58a7eaf/R2-postgres-part-A.txt` |
| R2 part B — the remaining ten M085 PostgreSQL suites (57, 7, 48, 7, 3, 3, 49, 15, 125, 2) | **316 passed, 0 failed** | `runs-58a7eaf/R2-postgres-part-B.txt` |
| R5 static, sequential — compileall OK; ruff format 790 / check clean; mypy 382 files clean; architecture exit 0 + negative fixture; frozen paths unmodified (96 governed); `tests/architecture` 65 passed; renderers M082–M085 current; M084 file audit 75 paths; pip-audit none; build OK | green except **one real defect found by the gate**: the committed JSON manifest `m085-migration-manifest.json` failed the secret scan (quoted 64-hex digests read as secrets) | `runs-58a7eaf/R5-static-rerun.txt` |

**The defect and its fix (the only code change after `58a7eaf`).** The manifest is now
`m085-migration-manifest.sha256` in the sha256sum form the repository's other manifests use
(`<digest> *<path>`, comment header naming the M085 head commit in short form), and the ancestry
test parses that form; same 26 digests, same assertions. Commits `794c53f` (manifest form + test)
and `10a0aee` (one docstring line wrapped for ruff). Re-verified at `10a0aee` on a clean tree —
ruff format/check clean, mypy clean, `test_m087_schema_ancestry_postgres` 2 passed +
`test_m087_schema_head` 14 passed, secret scan 1580 targets none, build OK
(`runs-10a0aee/R-delta-since-58a7eaf.txt`). No exit handler, domain rule, migration, simulation
rule or console module changed after `58a7eaf`; R1 (269) and R3 (4422 / 80.52 %) were not re-run
because no file they exercise changed (the ancestry test is PostgreSQL-only and skips in R3).

## 6. Classification

**M087_SCHEMA_BOUNDARY_CLOSED_READY_FOR_INDEPENDENT_REVIEW** — on the evidence of §1 (every suite
green, 0 red tests) and §5 (R1 269 at the exact SHA; the owed R2 and R5 rounds completed
sequentially at the exact code, 581 PostgreSQL-round tests passed, one evidence-format defect
found by the secret gate and fixed in `10a0aee`). Publication status and exact-head CI are
recorded in the pull request. Not merged; not frozen. No Alpaca call, no Paper trade, no Live trade. M085 Paper Acceptance remains NOT_STARTED.
Not M087 COMPLETE, not DAILY TRADING READY, not PAPER READY, not LIVE READY.

## 7. M087 exit behaviour — unchanged by this correction

No exit handler, domain rule, migration column, trigger, simulation rule or console page changed
in the schema-boundary correction. Preserved and still proven by the suites listed in the README
adversarial table: SELL_TO_CLOSE only; full close only; verified attributable long position; no
negative position; exact Owner confirmation; deterministic exit identity; single-use
authorization; durable send boundary; no blind retry; UNKNOWN reconciliation on the same
identity; verified zero position before "Position closed"; realized P&L only from proven fills;
SIMULATION only.

