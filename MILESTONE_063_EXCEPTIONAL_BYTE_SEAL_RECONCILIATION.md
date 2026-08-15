# MILESTONE-063 — Exceptional Byte-Seal Reconciliation

**Status:** `EXCEPTIONAL_NON_SEMANTIC_REPAIR_APPLIED`
**Repair commit:** `d02dc06ec7d10a3b591f4ba9e9d0542d36233733`
**Authorized by:** Owner, explicitly and narrowly, during MILESTONE-074 closure.
**Milestone governance unchanged:** MILESTONE-063 remains `APPROVED_AND_FROZEN`.

This document records a non-semantic repair to a frozen milestone. It does
**not** replace, amend, or reinterpret
`MILESTONE_063_..._MACRO_MILESTONE_FREEZE.md`. That freeze document remains
historical truth exactly as written, including the seal value it recorded.
This record exists so the discrepancy between the two is explicit and
auditable rather than silent.

---

## 1. Why a frozen milestone required repair

M063's dataset bundle carries a SHA-256 tamper-detection seal. The seal
recorded at freeze time could never be reproduced from the repository's own
committed bytes. It validated only on a working copy checked out with
`core.autocrlf=true` (i.e. a Windows developer machine), and failed
everywhere else — including GitHub Actions.

The consequence was that **14 M063 unit tests failed on any clean checkout**,
which in turn made the `foundation` CI workflow unable to reach a green state
on any branch, blocking MILESTONE-074 closure. The blocker was inherited by
M074; it was not caused by it.

This is a defect in the *seal*, not in the *dataset* and not in the *science*.

## 2. Exact pre-repair mismatch

| Quantity | Value |
|---|---|
| Fixture path | `tests/fixtures/m063_robustness_study/synthetic_broad_robustness_dataset_bundle.json` |
| Git blob object | `800ecb199c2c47f8d719a5c6e10a7e94d57160c1` |
| Introduced by | `1937594b528627807e060769f9dbefb2c4590f7f` (`feat: implement M063 historical robustness study`) |
| Times the blob has changed since | **0** |
| Committed blob sha256 (LF) | `765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd` |
| Old expected seal (CRLF worktree) | `ca98478ce6156f41c4535eaa040fd3e161229a71acd771a477ee9648ac3dd506` |
| Committed blob line endings | 9721 LF, 0 CRLF, 268805 bytes |
| Windows worktree line endings | 9705 CRLF + 16 LF, 278510 bytes |

The old seal corresponds to a byte sequence that has **never existed in the
git object database**. It was computed from a checkout artifact.

## 3. Semantic equivalence proof

Normalising the CRLF form's `\r\n` to `\n` reproduces the committed blob
**byte for byte**. Independently verified:

- parsed JSON objects compare equal;
- canonical re-serialisations are identical
  (`45804fde0fdffdc1f4a035afbcc458d2329f3f8ae2680e72fc2e585a287d5585`);
- identical `dataset_bundle_id`, version, `source_kind`, universe id/version,
  and membership model;
- identical instrument universe (AAPL, MSFT, GOOG, AMZN, NVDA, TSLA);
- 960 bar records, each equal field-for-field and in order;
- 10 window specifications, each equal and in order.

No content value differs.

## 4. Canonical result equivalence

The frozen M063 pipeline was executed against both byte forms and every
canonical output compared:

| Metric | Both forms |
|---|---|
| classification | `ROBUSTNESS_EVIDENCE_MIXED` |
| window_count | 10 |
| total_evaluated_cutoff_count | 80 |
| total_simulated_trade_count | 59 |
| total_executed_trade_count | 59 |
| positive / negative net-PnL windows | 7 / 3 |
| positive / negative total-R windows | 7 / 3 |
| median_window_net_pnl | 183.944565 |
| median_window_total_r | 1.634932038356822214357869934 |
| all_window_net_pnl_total | 3159.55176410 |
| all_window_total_r_total | 33.84096575766330478385285292 |
| excluding_best_window_net_pnl_total | 1914.24177280 |
| excluding_best_window_total_r_total | 15.59449584874087639535104952 |
| largest positive-window share of positive PnL | 0.3481136196652371557486284593 |
| largest negative-window share of abs. negative PnL | 0.7014969015918107753748046817 |
| best / worst window by net PnL | W08 (1245.30999130) / W07 (-293.055420) |
| best / worst window by total R | W05 (18.24646990892242838850180340) / W06 (-7.737888034172596900624932265) |

All 10 per-window results (regime label, realized volatility, cutoffs, trade
counts, win/loss/time-exit/no-entry, gross and net PnL, average R, total R,
win rate, profit factor, maximum realized-PnL drawdown, timestamps) are
equal, as are all 10 derived backtest runs.

Across the entire canonical payload exactly **one** leaf field differs:
`dataset_bundle_sha256` — the seal itself, which by construction records
which bytes were read. There is no scientific difference of any kind.

## 5. Repair selected

`M063_SEAL_REPAIR_DECISION = UPDATE_SEAL_ONLY` (plus a narrowly-scoped
determinism guarantee).

Options weighed:

| Option | Verdict |
|---|---|
| **A. Correct the seal to the committed blob** | Necessary but **not sufficient alone** — would move the failure from Linux/CI onto Windows. |
| **B. Re-commit fixture bytes as CRLF** | Rejected. Changes the bytes of a frozen dataset, requires forcing CRLF in-repo, and is hostile to every non-Windows checkout. |
| **C. Normalise via `.gitattributes` alone** | Necessary but not sufficient alone — the recorded seal would still be wrong. |
| **D. Narrower correction** | None exists that yields reproducibility. |

Applied repair = **A + C, scoped to this one fixture path**:

1. the four M063 seal constants now carry the committed-blob digest;
2. `.gitattributes` pins that single path with `-text`, disabling EOL
   conversion in both directions, so every platform materializes the
   committed bytes verbatim.

Both halves are required. Either alone leaves one platform broken.

## 6. Files changed

| File | Change |
|---|---|
| `.gitattributes` | `-text` pin for the one fixture path, with rationale |
| `tests/unit/test_decision_candidate_robustness_study.py` | seal constant |
| `tests/unit/test_decision_candidate_robustness_study_independent_verification.py` | seal constant |
| `tests/unit/test_m063_robustness_study_application.py` | seal constant |
| `tests/integration/test_m063_robustness_study_lifecycle.py` | seal constant |
| `tests/fixtures/m063_robustness_study/README.md` | documents the reconciliation |

**Not changed:** the fixture bytes; any M063 domain, usecase, repository, or
migration file; strategy, ranking, risk, or sizing logic; any recorded
historical outcome; the M063 freeze document; the sealed
`external-review/MILESTONE-063/` package.

## 7. M064 / M065 preservation

M064 and M065 fixture bytes, seals, and git attributes are **unchanged**.
Verified by recomputing worktree digests before and after the repair:

| Fixture | Digest (unchanged) |
|---|---|
| M064 `survivorship_aware_dataset_bundle.json` | `af996c09…` |
| M064 `instrument_master.json` | `2fb478ce…` |
| M064 `membership_manifest.json` | `798c9f36…` |

The `-text` pin is scoped to a single explicit path and cannot reach them.

## 8. Known remaining defect (NOT repaired — outside authorization)

**M064 carries the identical latent defect.** Its seals also record Windows
CRLF worktree digests rather than committed-blob digests:

| Fixture | Committed blob | Seal records |
|---|---|---|
| `survivorship_aware_dataset_bundle.json` | `15a4d263…` | `af996c09…` |
| `membership_manifest.json` | `3c4ad211…` | `caa9fa89…` |

This does not currently break CI because the affected M064 tests are
PostgreSQL-gated and are skipped there. It **will** fail on any clean-checkout
run with PostgreSQL enabled. M074's own integration tests inherit the same
constants and the same exposure.

This was deliberately left unrepaired: the owner's authorization covers M063
only, and the closure mission explicitly requires M064/M065 seals to remain
unaffected. It is recorded here so the exposure is documented rather than
discovered later, and it warrants its own authorization.

## 9. Verification performed

- 14 previously-failing M063 unit tests now pass; 22/22 in the M063 unit set.
- Full default suite: 1861 passed, 357 skipped, coverage 80.01% (floor 79%,
  not lowered).
- `ruff format --check`, `ruff check`, `mypy`, and the architecture checker
  all pass.
- Clean-clone reproduction with `core.autocrlf=false`.
- GitHub Actions `foundation` workflow on the repaired head.
