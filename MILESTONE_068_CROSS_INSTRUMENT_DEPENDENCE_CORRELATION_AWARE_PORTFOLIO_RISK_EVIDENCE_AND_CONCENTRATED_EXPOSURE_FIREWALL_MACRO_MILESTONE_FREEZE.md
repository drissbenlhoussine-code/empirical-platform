# MILESTONE-068 - Cross-Instrument Dependence + Correlation-Aware Portfolio Risk Evidence + Concentrated-Exposure Firewall - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M068
baseline `0cc287af7a512a774a55edd9cf78359c9b8bbf6f` (the M067 Owner
Freeze hash-recording HEAD; M067 fully `APPROVED_AND_FROZEN`),
independently re-verified at mission start and again during the
logically independent second pass (`git fetch`, `git status`,
`git rev-parse HEAD`/`origin/master` agreed both times: 0 ahead / 0
behind). Full governance and design decisions are recorded in
`MILESTONE_068_CROSS_INSTRUMENT_DEPENDENCE_CORRELATION_AWARE_PORTFOLIO_RISK_EVIDENCE_AND_CONCENTRATED_EXPOSURE_FIREWALL_SCOPE_AND_DESIGN.md`.

## Delivered Capability

A new, additive `decision_candidate.portfolio_dependence` module
computes a post-hoc, deterministic `PortfolioDependenceReport`: given an
already-frozen M067 `PortfolioEvidenceReport` and the exact M064/M065
dataset bundle it declares, derive simple-return series per instrument,
compute canonically-ordered pairwise Pearson correlations under one
explicit temporal-firewalled estimation policy, link dependence to the
real concurrent-exposure timeline M067 already froze, and produce a
dependence-weighted concentration figure alongside the nominal
(capital-only) HHI figure -- exposing when nominal diversification
overstates true historical dependence. Zero changes to any strategy/
ranking/risk/sizing/capital-allocation code. Purely additive PostgreSQL
schema (3 new tables). Two new CLI entrypoints, no HTTP.

## Implementation Evidence

- **Source:** `src/empirical_platform/decision_candidate/portfolio_dependence.py`
  (~720 lines), `portfolio_dependence_repository.py` (Protocol),
  `shared/persistence/postgres_repositories/portfolio_dependence_repository.py`,
  `usecases/run_portfolio_dependence_evidence.py`,
  `usecases/get_portfolio_dependence_evidence.py`,
  `usecases/portfolio_dependence_io.py`,
  `entrypoints/run_portfolio_dependence_evidence.py`,
  `entrypoints/get_portfolio_dependence_evidence.py`,
  migration `c4d8f6a29b17` (down-revision `a3f7c81e4b96`, purely
  additive), plus a `PortfolioDependenceReportId` identifier and
  `pyproject.toml` console-script registration.
- **Tests:** 35 pure unit tests
  (`test_decision_candidate_portfolio_dependence.py`: policy/pair/state
  validation, return-series derivation including the temporal firewall,
  Pearson correlation edge cases, matrix canonicalization/symmetry/
  diagonal, dependence-weighted concentration math, concurrent-state
  derivation, classification thresholds) + 6 acceptance-control tests
  (`test_decision_candidate_portfolio_dependence_controls.py`:
  perfect-correlation, low-dependence, negative-correlation,
  constant-series, false-diversification-attack, future-mutation-attack)
  + 8 PostgreSQL lifecycle/acceptance tests
  (`test_m068_portfolio_dependence_lifecycle.py`: full lifecycle, real
  CLI subprocess, deterministic replay, estimation-policy sensitivity,
  upstream authority-mismatch attacks, duplicate governance ID, tampered
  dataset hash) + 3 independent recomputation integration tests
  (`test_m068_portfolio_dependence_independent_verification.py`), 52 new
  tests total.
- **Full regression:** `1939 passed, 6 skipped, 1 failed` with real
  PostgreSQL opt-in (91.75% coverage). The 1 failure is the pre-existing,
  unrelated M026 credential-repr false positive present identically in
  every prior milestone's equivalent full-suite run this session.

## Canonical Results

Run against the real M064 canonical fixture's own M067 portfolio (35
allocated positions, `max_concurrent_positions_observed=4`) under the
default estimation policy (`lookback_bar_count=20`,
`minimum_overlapping_observations=10`):

```
instrument_count: 6   pair_count: 21   defined_pair_count: 21   undefined_pair_count: 0
highest_pair: (AAPL, GOOG) 0.6433
lowest_pair: (AAPL, AMZN) -0.3667
concurrent_exposure_state_count: 26
peak_nominal_concentration: 0.8589   peak_dependence_aware_concentration: 1.0000
correlation_instability_observed: True   max_window_instability_delta: 0.5575
classification: HIGH_OBSERVED_DEPENDENCE
```

This is the honest, un-massaged result on the real fixture -- not
required to be high or low. Notably, the real data independently and
organically reproduces the mission's own central thesis without any
special-casing: 3 concurrent-exposure states involve multiple
concurrently open positions in the *same* instrument (repeated
NVDA/TSLA entries), driving `dependence_aware_concentration` to `1.0000`
while `nominal_concentration` sits far lower (`0.4022`, `0.3384`,
`0.5000` respectively) -- a real, un-synthesized example of nominal
capital spread understating true historical dependence.

## Hostile Review

81 explicit attack/verification cases were catalogued in
`external-review/MILESTONE-068/hostile-review-matrix.md` (empty/single/
duplicate-instrument samples, perfect/negative/zero-variance/
insufficient-observation correlation edge cases, canonical-pair-order
and symmetry/diagonal enforcement, dependence-weighted concentration
math including the conservative undefined-pair treatment, classification
thresholds and vocabulary honesty, the false-diversification central
product proof (both synthetic and organic real-data), correlation
instability, concentration stress, database-level CHECK/FK/UNIQUE
enforcement, PostgreSQL round-trip and raw-SQL agreement, real CLI
subprocess evidence, independent recomputation, and no-optimization/
no-broker/no-network/no-LLM/no-M069-scope-creep claim-honesty greps).
One genuine defect was found and fixed inline:

1. The first draft of every correlation-based acceptance control opened
   every synthetic position at the exact same instant as each series'
   own first bar, leaving zero prior return history at the canonical
   estimation cutoff -- a test-construction flaw (not a production
   defect: the temporal firewall itself was working exactly as
   specified). Diagnosed by inspecting the exact cutoff/temporal-firewall
   code path, fixed by shifting every control's synthetic entry/exit
   timestamps to occur after the return sequence had already
   accumulated. The future-mutation-attack control was additionally
   strengthened from a vacuously-passing case (both original and mutated
   reports equally insufficient-observations) into a genuine,
   non-vacuous proof.

This fix was independently re-attacked and re-verified during the
second pass. No CRITICAL or MAJOR finding remains open.

## Canonical Validation

`ruff check src tests` clean. `mypy` clean (255 files, project config).
`tools/check_architecture.py` exit 0. Full `pytest tests/ -q` (unit +
integration, PostgreSQL opt-in, run alone with no concurrent process
against the container): `1939 passed, 6 skipped, 1 failed` (the
pre-existing M026 false positive only) in 1143s, 91.75% coverage. Every
frozen predecessor milestone (M020-M067) remains green. `pip_audit`
clean. Secret scan: 6 findings across the new M068 files, all the same
pre-existing, already-accepted "Hex High Entropy String" false-positive
pattern (migration revision hex IDs, reused M064 hash constants), zero
genuinely new secret material. Wheel build confirmed all 8 new M068
source files and both new console scripts present.

## Attempting to Disprove the Central Claim

M068's central claim: **"When several concurrently-held positions look
diversified by capital weight alone, their historical price dependence
can tell a different story -- exposed honestly, without ever fabricating
a correlation value or leaking future data into a past estimate."**
During the independent second pass, this was directly attacked from four
independent angles against raw persisted data (never reusing the
production dependence-computation helpers): (1) no
`portfolio_dependence_pair` row is ever non-canonically ordered or
duplicated; (2) no `DEFINED` correlation ever falls outside `[-1,1]`;
(3) no concentration figure (nominal or dependence-aware) ever falls
outside `[0,1]`; (4) a from-scratch temporal-firewall falsification --
independently recomputing the earliest concurrent-exposure instant's own
return series twice, once against the full bar history and once against
an in-memory copy with every later bar deleted -- found the two
independently-derived return dictionaries byte-identical. No evidence of
a fabricated value or future-data leakage was found under any of the
four attempts.

## Logically Independent Second Pass

Full record: `external-review/MILESTONE-068/independent-second-pass.md`.
Summary: a genuinely different, freshly-created PostgreSQL container
(`m068-second-pass-pg`, `postgres:16`, port 32776, never used by any
earlier M068 evidence), Git truth re-established from scratch
(`HEAD == origin/master` at `0cc287a`, 0/0), all 22 migrations (M020
through M068) applied cleanly to an empty database, every acceptance
step driven through the real installed CLI executables, a standalone
stdlib+psycopg-only independent recomputation matching production
exactly (0 mismatches across 21 pairs), the hostile-review-fixed defect
re-attacked and confirmed still fixed (24-test integration suite rerun),
and the central claim directly attacked and held under all 4
falsification attempts (see above).

## No Optimization / No Cherry-Picking / No Broker / No Network / No LLM / No M069 Scope Creep

Repeated independently in the second pass:
`grep -rniE "openai|anthropic|llm|gpt|chat_completion"`,
`grep -rniE "broker|place_order|submit_order|live_trading"`,
`grep -rniE "requests\.|urllib|httpx|socket\.|http://|https://"`,
`grep -rniE "optimi[sz]e|grid_search|best_of|hyperparam"`,
`grep -rniE "markowitz|efficient_frontier|risk_parity|kelly|black.litterman|cluster|factor_model"`
across all new M068 source: no matches beyond the modules' own explicit
docstring disclaimers. No M068 output was ever used to optimize, select,
re-rank, resize, or rebalance a strategy/ranking/risk/sizing/
capital-allocation parameter -- confirmed by inspection: no code path
reads a `PortfolioDependenceReport` field and writes it back into any
upstream decision object. The genuine `HIGH_OBSERVED_DEPENDENCE`
canonical result was accepted and reported as-is, not regenerated with a
different estimation policy to force a more "reassuring" result.

## Product Honesty Gate (Reality Gate)

1. **Does M068 prove diversification?** **NO.** Neither nominal nor
   dependence-aware concentration is ever described as proving
   diversification is adequate or safe.
2. **Does M068 predict future correlations?** **NO.** Every persisted
   report carries the same 6-statement `FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS`
   tuple verbatim, stating explicitly that historical correlation does
   not imply future correlation.
3. **Does M068 optimize allocation?** **NO.** It evaluates the exact,
   already-frozen M067 concurrent-position timeline under one
   predeclared estimation policy -- it never searches for, selects, or
   recommends a different allocation.
4. **Does it measure historical dependence?** **YES.** Pairwise Pearson
   correlation, canonically ordered, honestly represented as undefined
   (never a fabricated 0) when the data does not support a value.
5. **Does it connect dependence to actually concurrent M067 positions?**
   **YES.** Every `ConcurrentExposureState` is derived directly from
   M067's own real event timeline -- positions that never overlap in
   real time are never treated as simultaneous exposure.
6. **Can it expose false nominal diversification?** **YES.** Proven both
   on the mandatory synthetic false-diversification attack and
   organically on the real canonical fixture (repeated same-instrument
   concurrent positions driving dependence-aware concentration to
   `1.0000` far above the nominal HHI).
7. **Does future data affect earlier dependence?** **NO.** Proven at the
   pure-function level, the real-event-timeline level, and via an
   independent from-scratch falsification attempt during the second
   pass -- zero violations found across all three.
8. **Are undefined correlations represented honestly?** **YES.** A
   zero-variance pair is `UNDEFINED_ZERO_VARIANCE`; an
   insufficient-overlap pair is `INSUFFICIENT_OBSERVATIONS`; neither is
   ever silently reported as `0`.

**No claim of diversification, future-correlation prediction, optimal
allocation, hedging effectiveness, profitability, or live-trading
readiness is made anywhere in this milestone.** M068 makes historical
cross-instrument dependence among genuinely concurrent M067 positions
explicit and proves the correlation/concentration mechanics honestly; it
does not certify that the evaluated portfolio is diversified, that its
correlations will hold in the future, or that the platform is ready to
manage live risk.

## Owner Approval

All mandatory phases (0-34) of the M068 mission specification are
complete: repository-authority verification, fresh inventory, core-
boundary/data-authority/return-semantics/temporal-firewall design,
pairwise dependence and correlation matrix semantics, the concurrent-
exposure link to M067's real event timeline, dependence-weighted
concentration math, 6 named acceptance controls (perfect-correlation,
low-dependence, negative-correlation, constant-series, false-
diversification-attack, future-mutation-attack), an estimation window
policy, classification and instability/stress diagnostics, PostgreSQL
persistence, real CLI, a canonical study run against the real M064/M067
fixture (honestly reporting a genuine `HIGH_OBSERVED_DEPENDENCE`
result), independent recomputation, an 81-case hostile review with 1
inline-fixed test-construction defect, full canonical validation, a
logically independent second pass on a genuinely fresh container that
directly attempted and failed to disprove the central claim across 4
falsification angles, and the 8-question reality gate above. Zero
blockers remain.

**Freeze declaration:** `M068 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M068 APPROVED_AND_FROZEN`.

## Deferred / M068 Boundary

Explicitly out of scope and not built: any portfolio optimizer
(Markowitz/efficient-frontier/risk-parity/Kelly/Black-Litterman),
automatic diversification, automatic position resizing, ML clustering,
factor models, any change to strategy/ranking/risk/sizing/
capital-allocation code, any HTTP transport, any broker/execution code.
**MILESTONE-069 was explicitly NOT built, per the mission's own
instruction.**

## Next Permitted Action

MILESTONE-069 -- recommendation only; not started as part of M068.
