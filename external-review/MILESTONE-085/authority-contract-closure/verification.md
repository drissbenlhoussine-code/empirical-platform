# Exact-SHA verification — canonical authority contract closure (AUTH-1)

Published head reviewed: **`673394e0834f19df7ce8a4ca9700f4cc793e2bc7`**.
CODE_CANDIDATE_SHA: **`88ea0ed3d036a4243520e1f6b1da57ab9404333b`** (`88ea0ed`).

Executable delta `673394e..88ea0ed` (8 files): `tools/render_m085_authority.py` (v2 tables, digest,
refusal), `external-review/MILESTONE-085/current-authority.json` and `.schema.json` (v2),
`current-authority.md` (regenerated), `tests/integration/test_m085_authority_contract.py` (71 → 118
tests), `tools/m085_mutation_campaign.py` (3 new families, 2 retargeted),
`tests/unit/test_m085_paper_execution_domain.py` (canonical policy key), and ONE production file:
`src/empirical_platform/decision_candidate/paper_execution.py` — the `RECONCILIATION_UNKNOWN_POLICY`
mapping only (a canonical key with the same value and a declared legacy alias; no function, constant
or behaviour changed). Because a production file changed, verification was expanded beyond the
authority suites: every mutation family whose target is that file (79) was rerun in addition to the
6 authority-file families, and the full non-PostgreSQL suite ran (the repository's merge gate,
`scripts/quality.ps1`, runs the whole suite). Commits after `88ea0ed` are evidence-only.

Every run below executed on the exact commit `88ea0ed`, strictly one at a time (the chain script
`R1 → R2 → R3 → R5 → R4`), with no executable file modified (`dirty` counts only documentation
under `external-review/`). No Alpaca endpoint was called; PostgreSQL tests used the disposable
database `m085_pgon_b24c471` (trust auth; placeholder password variable).

## 1. Environment

Windows 11 Pro 10.0.26200; Python 3.13.14; pytest 9.1.1; psycopg 3.3.4 pinned `PSYCOPG_IMPL=python`
over libpq 16.0.13; SQLAlchemy 2.0.51; alembic 1.18.5; PostgreSQL 16.13; detect-secrets 1.5.0;
ruff 0.16.3; mypy 1.20.2. No CI has run on `88ea0ed` (not pushed).

## 2. Results on `88ea0ed`

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused (solo) | all `tests/unit/test_m085_*.py` + PostgreSQL reconciliation rounds (15) + **authority contract (118)** | **1018 passed** (971 at `c4cc3d0` + 47 new authority tests) | `runs-88ea0ed/R1-focused.txt` |
| R2 PostgreSQL (solo) | all 13 `tests/integration/test_m085_*.py` — incl. the authority contract's chain-at-head tests, the migration down/up/up test, the schema-head guard tests (`test_m085_corrective_pass_postgres.py`) and the round-journal guards | **511 passed** in 4 min 51 s (464 + 47) | `runs-88ea0ed/R2-postgres.txt` |
| R3 non-PostgreSQL full suite | `pytest` (root config, coverage), PostgreSQL opt-in unset | **4192 passed, 0 failed, 1254 skipped** (opt-in gates only); **coverage 80.35 % ≥ 79 %** (20 667 / 3 535, identical totals to `c4cc3d0`) | `runs-88ea0ed/R3-full-non-pg.txt` |
| R4 mutations | **85 families**: the 6 whose target is an authority file (schema 3, contract 2, renderer 1) + the 79 whose target is `decision_candidate/paper_execution.py` | **85 / 85 detected, 0 blockers**; tree digest `77d805f490538d35…` identical before and after; tree clean | `runs-88ea0ed/mutation-chunk-00.md`, `R4-chunk-00.txt`, `affected-families.txt` |
| R5 static | compileall; ruff format/check; mypy; architecture + negative fixture; frozen-path guard (M083 27 + M084 69); `tests/architecture`; authority renderers M082–M085 `--check` (M085 now also verifies the meaning digest); M084 file audit; exhaustion table `--check`; `scripts/security.ps1` (pip-audit; secret scan incl. the integer digest — no finding, no rule changed); build | **green** — the exhaustion-table `--check` reports "not the current rendering" at this point by design (the inventory does not yet list this folder and the tree held its uncommitted documentation; regenerated in the two evidence commits below); the log's `dirty=1` is the package README edit under `external-review/` | `runs-88ea0ed/R5-static.txt` |

Not rerun (targets byte-identical between `673394e` and `88ea0ed`, detecting tests unchanged): the
93 families targeting `usecases/paper_execution.py`, the repository, the adapter, `paper_time.py`,
the migrations, the composition, the frozen-path guard and the acceptance tool. Their `093baf7` /
`c4cc3d0` results stand for `88ea0ed`.

Pre-commit: authority families 5/6 then 6/6 after the digest family's anchor followed ruff's
reflow and the detecting test was reordered so the renderer's own `MeaningDriftError` surfaces
(`precommit` matrices in the scratch record; both were anchoring/ordering matters, not survivors).

## 3. What the closure proves about the contract (tests, not prose)

| Requirement | Test |
|---|---|
| JSON validates against the closed schema | `test_the_contract_satisfies_its_own_schema` |
| renderer table keys == schema enums, bijectively | `TestTheRendererAndTheSchemaAreBijective` (4 sections + enforcement) |
| each v2 identifier mandatory; removing one fails validation | `TestAuthorityVersionTwoNamesTheRoundGuarantees` (parametrised over 9 + 1 + 6 + 2 identifiers) |
| unknown identifier fails | `test_an_unknown_claim_identifier_is_rejected_before_rendering` |
| enforcement identifiers exhaustive and each pinned to installed SQL | `test_every_enforcement_claim_is_checked_against_installed_sql`, `test_every_database_enforcement_claim_names_sql_installed_at_head` (+8 round fragments) |
| limitations exhaustive | bijection + exact counts (`test_every_list_length_is_exact`) |
| version pinned (2), version 1 rejected | `test_the_authority_version_is_pinned_to_two` |
| Markdown byte-exact from the JSON | `test_the_markdown_is_byte_identical_to_the_rendering`, `--check` |
| a renderer-only semantic change cannot pass under an unchanged contract | `TestTheMeaningIsPinnedToTheContract` (digest declared, schema-pinned, sensitive per table, sensitive to renaming, renderer refuses); mutation family `authority_meaning_digest_pins_the_sentences` |
| migration chain includes `a7d3c9e14f26` (no historical migration edited) | `test_the_rendered_chain_is_exactly_the_m085_revisions_ending_at_head`; runtime `M085_SCHEMA_HEAD` guard tests on PostgreSQL |
| round claims match the code | `TestTheRoundClaimsMatchTheCode` (sort key, subtraction operands, begin-before-lookup order, lock-before-MAX+1, finalisation locks/re-evaluates/compares version, no network call in the repository, exact compared order terms, pure-evaluation refusals) |

## 4. Adversarial self-review

- *Can renderer semantics still change materially without a JSON/schema change?* No: the renderer
  refuses to render and `--check` fails unless the tables digest to the declared integer, which the
  schema pins as a const. A change therefore edits `current-authority.json` and `.schema.json`.
  What remains possible: changing the sentence **and** the digest in the same commit — which is a
  visible canonical-contract change, the property required. The version bump is a reviewer's
  decision, not automated; the digest makes the need for that decision impossible to miss.
- *Does the canonical JSON describe durable rounds, broker-time waiting and fresh re-validation
  explicitly?* Yes — as nine `proves` identifiers, six `database_enforcement` properties, one
  `does_not_prove` and two `structural_limitations`, each with one sentence.
- *Are database-enforcement claims stronger than the triggers provide?* Each is pinned to a trigger
  message or constraint name installed by `a7d3c9e14f26`. Serialised allocation and finalisation
  re-validation are application code and are claimed under `proves`, not as database enforcement.
  Nothing new is claimed against a database owner, DDL, disabled triggers, TRUNCATE/DROP or broker
  truth.
- *Were historical limitations accidentally removed?* No — exact counts are 14+9, 19+1, 18+6, 11+2
  and every v1 identifier is asserted present; the three superuser/blocked-submission identifiers
  are named explicitly in the test.
- *Does "31/31" still risk being read as Paper acceptance?* The rendered table's header, the
  package README and the V1 statement (README §6 of this folder) each say it is engineering
  verification, that row 12 is an honestly BLOCKED submission, and that Paper acceptance is
  NOT_STARTED.
- *Remaining wording debt:* `alpaca-contract-evidence.md` (historical evidence, not regenerated)
  still says "60 seconds since dispatch". The canonical contract and the policy mapping now say
  what is measured; the historical file is left as the record of its round.

## 5. Commits after the code candidate

| Commit | Content | Executable change |
|---|---|---|
| (docs commit following `88ea0ed`) | this folder (README, verification, `runs-88ea0ed/`), package README pointer | none |
| (docs commit following that) | `changed-files.txt` regenerated; `exhaustion-table.md` re-rendered | none |

## 6. Outcome

AUTH-1: **CLOSED.** The canonical contract (authority version 2) names every durable-round
guarantee, enforcement and limitation as its own identifier; the renderer's meaning is digested
into the contract and pinned by the schema, so a renderer-only change of meaning is refused; the
under-claimed broker-answer sentence and the stale policy key name are corrected without changing
behaviour. On `88ea0ed`: R1 1018, R2 511, R3 4192 / 80.35 %, R4 85/85, R5 green.

Recommendation: **READY_FOR_OWNER_PUBLICATION_APPROVAL** — local commits only; not pushed; not
merged; not frozen; not OWNER_ACCEPTED; not READY_FOR_PAPER; Paper acceptance NOT_STARTED; M086
NOT_STARTED; V1 pending Owner ratification (statement prepared in README §6, not self-approved).
No CI has run on `88ea0ed`. The historical full-PostgreSQL baseline (3 failed / 43 errors) remains
non-green and was not rerun.
