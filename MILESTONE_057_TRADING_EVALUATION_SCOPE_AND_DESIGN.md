# MILESTONE-057 - First Trading Intelligence Vertical Slice - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M056. This milestone is a **phase transition**: the prior four macro milestones (M053-M056) closed the core evidence/governance engine (Campaign/Run/EvidencePackage/Review); M057 is the first milestone to add genuine trading-domain functionality on top of it.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M057 frozen baseline: `e3ba3b67dc4e57484d655e8ffe335c580cb69714` (the final M056 Owner Freeze hash-recording HEAD; M056 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` immediately before this document was written.

## 2. Trading Capability Inventory (Phase 1)

Exhaustive keyword search across all governance markdown and all source under `src/empirical_platform/` for: market, symbol, instrument, equity, ETF, quote, bar, candle, OHLCV, price, volume, session, strategy, signal, indicator, decision, recommendation, risk, entry, stop, target, position, order, execution, confidence, score.

| Capability | Classification | Evidence |
| --- | --- | --- |
| Market/bar/instrument value objects | **C - absent, required** | No pre-existing type anywhere in `src/`; built fresh this milestone as `decision_candidate/market_data.py` |
| Strategy evaluation logic | **C - absent, required** | No pre-existing strategy/signal code anywhere; built fresh as `decision_candidate/strategy.py` |
| Decision/evidence record type | **C - absent, required** | No pre-existing "decision candidate" domain type existed as code; built fresh as `decision_candidate/candidate.py` |
| `decision_candidate` package + architecture wiring | **B - partial (placeholder)** | `src/empirical_platform/decision_candidate/__init__.py` already existed as an empty placeholder (`"No decision_candidate behavior is implemented."` docstring only), and `tools/check_architecture.py` **already** declared `"decision_candidate": {"shared", "identifiers", "audit", "evidence"}` in its `ALLOWED` table -- a pre-planned dependency shape from the project's original M012-era foundation, predating this session. This directly informed the M057 design decision (Section 8 below) to link `DecisionCandidate` to `EvidencePackage`, not `Run`. |
| `acquisition`/`normalization`/`validation`/`audit`/`archive`/`registry`/`governance` packages | **B - partial (placeholder)** | All exist as empty packages (docstring-only `__init__.py`), part of the same pre-planned pipeline shape. None given real behavior this milestone; out of scope. |
| `datasets` package (`DatasetManifest`) | **A - implemented** | Given real behavior in M055 (Run manifest data). Considered and rejected as the trading vertical's data-ingestion vehicle -- `DatasetManifest` models acquisition-of-a-dataset-as-a-whole, not per-bar OHLCV time series; reusing it would force a bad abstraction. |
| Campaign/Run/EvidencePackage/Review core engine | **A - implemented** | Fully composed end-to-end (M053-M056); this milestone's evaluation output integrates with it as a typed reference plus an ArtifactReference, per Section 8. |
| Live/streaming market-data ingestion, broker/exchange connectivity | **E - explicitly out of scope** | Mission Phase 4 non-goal; would require external network I/O and real-money risk this milestone must not introduce. |
| Portfolio/position/order/execution management, leverage, short selling, options/futures/crypto, overnight trading, RL/self-modifying strategy logic, LLM-driven price prediction | **E - explicitly out of scope** | Mission Phase 4 non-goals, verbatim. |
| Any risk/entry/stop/target/confidence-score modeling beyond the one deterministic strategy's own reason codes | **D - useful later** | Deliberately deferred; would expand scope well beyond "first vertical slice proving the architecture." |

## 3. Scope Authority Determination (Phase 2)

Exhaustive search of every `MILESTONE_*.md` governance file and every source docstring found **no authoritative frozen trading scope** anywhere in repository history -- no prior milestone ever froze rules for instrument universe, session hours, bar granularity, long/short posture, or leverage. Per the mission's explicit instruction ("If no sufficiently precise authoritative scope exists: STOP DESIGN EXPANSION and create only the minimum explicit M057 scope needed"), this document now **originates**, transparently and for the first time, the following minimum scope, adopted from the mission's own suggested conservative default:

- **Instrument universe**: US-listed equities and ETFs, ticker symbols matching `^[A-Z]{1,5}$` (enforced by `Instrument.__post_init__`).
- **Session**: regular session only. No pre-market/after-hours semantics exist or are claimed.
- **Granularity**: intraday, `ONE_MINUTE` or `FIVE_MINUTE` bars only (`BarInterval`).
- **Posture**: long-only. No short-selling representation exists anywhere in `decision_candidate`.
- **Holding period**: intraday only. No overnight-position concept exists.
- **Leverage**: none. No leverage/margin field exists anywhere in the new domain types.

This is a **new M057 decision**, not a rediscovered prior rule. Any future milestone that needs to change it must do so explicitly, not by assumption.

## 4. Selected Vertical Slice (Phase 3)

**Input**: a deterministic `ObservationWindow` (an ordered, immutable sequence of `Bar`s for one instrument/interval, minimum 2 bars). **Process**: evaluate the window's last bar (`evaluation_bar`) against its preceding bars (`reference_bars`) under one deterministic, versioned strategy. **Output**: a structured `EvaluationOutcome` (decision + reason codes + measurements), persisted as an immutable `DecisionCandidate` linked to an `EvidencePackage`.

## 5. Non-Goals (Phase 4)

Verbatim from the mission, all honored: not a guaranteed-profit engine; not an autonomous broker; no live order execution; no portfolio management; no leverage; no short selling; no options/futures/crypto; no overnight trading; no reinforcement learning; no self-modifying strategy logic; no LLM guessing price direction. Given identical market data + strategy version + configuration, the evaluation produces the same result every time -- proven by `test_deterministic_replay_produces_identical_outcome` at both the pure-function level (`tests/unit/test_decision_candidate_strategy.py`) and the real-PostgreSQL level (`tests/integration/test_m057_trading_evaluation_lifecycle.py`).

## 6. Candidate Strategy Comparison (Phase 6)

| Candidate | Assessment | Selected? |
| --- | --- | --- |
| Simple moving-average crossover | Well-understood, but crossing point requires tracking a running average across the whole window, adding stateful complexity disproportionate to "prove the architecture" | No |
| RSI-threshold signal | Requires a multi-bar smoothed indicator (Wilder's smoothing) -- more surface area than needed for a first slice, without more architectural insight | No |
| **Prior-window breakout with volume confirmation** | Two simple, independently-explainable, closed-form conditions computed directly from `reference_bars`; produces a genuinely explainable NO_TRADE (each condition independently true/false, both reported); minimal statistical machinery (`max`, arithmetic mean); strongest "prove the pipeline, not the trade" fit | **Yes** |
| Fixed-percentage price-target signal | Ignores volume entirely; weaker proof of a multi-factor, explainable decision structure | No |
| Pure-random signal generator (control case) | Deliberately considered as a baseline "does the pipeline work regardless of intelligence" case, but rejected: the mission explicitly forbids randomness (Phase 4/17), and a random strategy cannot be deterministically replayed | No |

**Selected: `PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION`, version `"1"`** (`decision_candidate/strategy.py`). Decision rule: `LONG_CANDIDATE` iff the evaluation bar's close exceeds the maximum high of the most recent `reference_window_size` (default 5) reference bars, **and** the evaluation bar's volume exceeds the mean volume of those same reference bars; otherwise `NO_TRADE`. Both conditions are independently reported via `EvaluationReasonCode` regardless of the outcome.

> **THIS STRATEGY EXISTS TO PROVE THE TRADING-EVALUATION ARCHITECTURE. ITS PRESENCE IS NOT A CLAIM OF PROFITABILITY.** No backtest, no historical win-rate, and no forward-performance claim has been made or is implied anywhere in this milestone. See Section 16.

## 7. Strategy Versioning Contract (Phase 7)

`STRATEGY_ID = "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"`, `STRATEGY_VERSION = "1"` (both `str` constants in `strategy.py`), plus `StrategyParameters(reference_window_size: int = 5)` -- a frozen, explicit parameter object rather than hidden constants, so a future version-`"2"` could vary the window size without changing strategy identity. Every persisted `DecisionCandidate` records `strategy_id`, `strategy_version`, and `reference_window_size` verbatim, so a stored evaluation is fully reproducible from its own record plus the original `ObservationWindow`.

## 8. Structured Evaluation Result Contract (Phase 8) and Core Integration (Phase 10)

`EvaluationOutcome` carries `decision: TradingDecision`, `reasons: tuple[EvaluationReasonCode, ...]` (always exactly 2, one per condition), and `EvaluationMeasurements` (`current_close`, `current_volume`, `reference_high`, `reference_average_volume`). The persisted `DecisionCandidate` additionally carries identity (`DomainIdentity[DecisionCandidateId]`), `instrument`, `interval`, `evaluation_timestamp` (= the evaluation bar's own timestamp -- fully deterministic, never a wall-clock `created_at`), and `target_evidence_package_id: EvidencePackageId`.

**Core-integration decision**: `DecisionCandidate.target_evidence_package_id` is a typed direct reference to `EvidencePackageId`, mirroring `Review.target_evidence_package_id`'s existing shape exactly -- **not** a `RunId` reference, as an earlier design instinct considered. This was overturned by repository truth: `tools/check_architecture.py` already encoded `"decision_candidate": {"shared", "identifiers", "audit", "evidence"}` as a pre-existing, pre-planned dependency shape from the project's original foundation, predating this session -- i.e. the project's own original architects had already decided a future "decision candidate" concept should relate to `evidence`, not `run`. The resulting `DecisionCandidate`'s own `governance_id` is additionally recorded as a **separate** `ArtifactReference` on its target `EvidencePackage`, via the already-frozen M040 `record_evidence_package_artifact_reference` entrypoint, invoked as its own explicit step by the caller -- **not** merged into the `EvaluateTradingObservationHandler`, per the established one-aggregate-mutation-per-command discipline used by every command in this project. This is proven end-to-end in `test_positive_long_candidate_persists_retrieves_and_links_to_evidence`.

`DecisionCandidate` is deliberately **not** a sixth CQRS lifecycle aggregate: it is immutable, has no `save()`, no optimistic-concurrency column, and no transition history -- `DecisionCandidateRepository` exposes only `get()`/`add()`, a narrower Protocol than the existing 3-verb pattern, justified because the record is append-once by construction (one evaluation, one persisted outcome, no revision).

## 9. NO_TRADE Semantics (Phase 9)

`NO_TRADE` is mandatory, first-class, and structurally indistinguishable in representation from `LONG_CANDIDATE` -- same table, same columns, same reason-code shape, same retrieval path. `evaluate()` always returns exactly 2 reason codes (one per condition) regardless of decision, so a `NO_TRADE` result is always genuinely explained (e.g. `PRICE_NOT_ABOVE_REFERENCE_HIGH`, `VOLUME_ABOVE_REFERENCE_AVERAGE` -- one condition can hold while the other fails). Three distinguishable cases are proven end-to-end: a positive `LONG_CANDIDATE` (`test_positive_long_candidate_persists_retrieves_and_links_to_evidence`), a valid `NO_TRADE` (`test_valid_no_trade_is_persisted_as_a_first_class_outcome`), and invalid input -- insufficient reference bars raises `ValueError` before any persistence attempt (`test_invalid_input_insufficient_reference_bars_raises_value_error`, `tests/unit/test_decision_candidate_strategy.py`).

## 10. Persistence Model (Phase 11)

New table `decision_candidate` (migration `a1c93f7e2b04`, `down_revision = "5b58cdd7751b"`), created and round-tripped (`upgrade`/`downgrade`/`upgrade`) against a real disposable PostgreSQL container. All SQL lives in `PostgresDecisionCandidateRepository` (`shared/persistence/postgres_repositories/decision_candidate_repository.py`) -- no direct SQL anywhere in `decision_candidate`, `usecases`, or `entrypoints` (enforced by `tools/check_architecture.py`'s `FORBIDDEN_IMPORT_PREFIXES["decision_candidate"]` entry, added this milestone). `target_evidence_package_governance_id` foreign-keys to `evidence_package.governance_id`. Mapper round-trip correctness (full dataclass equality after `add()`+`get()`, including `Decimal`/enum/array field reconstruction) is proven by every acceptance test in `tests/integration/test_m057_trading_evaluation_lifecycle.py`, plus duplicate-`add()` (`AggregateAlreadyExists`) and missing-`get()` (`AggregateNotFound`) error paths, confirmed during development via an ad-hoc smoke script and formalized in the acceptance suite.

## 11. Application Layer (Phase 12) and Production Boundary (Phase 13)

`EvaluateTradingObservationCommand`/`EvaluateTradingObservationHandler` (`usecases/evaluate_trading_observation.py`): validated `ObservationWindow` + `StrategyParameters` in, strategy evaluated, `DecisionCandidate` persisted and returned. `GetDecisionCandidateQuery`/`GetDecisionCandidateHandler` (`usecases/get_decision_candidate.py`) mirrors the established Query pattern, no bounded snapshot needed (the record has no mutation/version internals to hide).

Exposed through the same lightest-sufficient production boundary already established since M050: a real CLI, composed through the unmodified, shared M053 `entrypoints._composition.postgres_repository_runtime()` helper. `evaluate_trading_observation` accepts a deterministic JSON bar-fixture file path plus a governance identity and target `EvidencePackage`, parses it into `Bar`/`ObservationWindow` objects, and prints the structured, persisted result as JSON. `get_decision_candidate` retrieves by identity. No HTTP/UI layer was built -- not required for this vertical slice, per the mission's explicit instruction. Both entrypoints are registered in `pyproject.toml` `[project.scripts]`.

**Architecture boundary correction, applied inline** (no correction milestone, per established practice): `entrypoints` cannot import `decision_candidate` directly (`tools/check_architecture.py`'s `"entrypoints": {"shared", "application", "identifiers", "usecases"}` set was not extended). The two new usecases modules now explicitly re-export (`import X as X`, the same idiom used in M054's `ReviewDisposition` correction) the domain types the entrypoints construct: `DecisionCandidate`, `ObservationWindow`, `StrategyParameters`, `Bar`, `BarInterval`, `Instrument`. This is a zero-behavior-change, mypy-strict-driven re-export, not a new design decision.

## 12. Market-Data Fixture (Phase 14)

`tests/fixtures/m057_market_data/` (see its own `README.md`): three JSON bar-fixture files, explicitly and repeatedly labeled synthetic/hand-authored, not live or historical market data. `synthetic_aapl_1min_long_candidate.json` (six bars, ends in a genuine breakout), `synthetic_aapl_1min_no_trade.json` (six bars, quiet), `synthetic_aapl_1min_lookahead_probe.json` (six bars, look-ahead regression probe -- see Section 14).

## 13. PostgreSQL Acceptance Evidence (Phase 15)

`tests/integration/test_m057_trading_evaluation_lifecycle.py`, run against a real, freshly migrated, disposable PostgreSQL 16 container (opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, matching every prior milestone's convention): 4/4 passing --

- `test_positive_long_candidate_persists_retrieves_and_links_to_evidence` -- real `LONG_CANDIDATE`, persisted, retrieved, independently verified via direct SQL bypassing the repository read path, and linked to its target `EvidencePackage` via a real `record_evidence_package_artifact_reference` call.
- `test_valid_no_trade_is_persisted_as_a_first_class_outcome` -- real `NO_TRADE`, persisted and retrieved identically to a positive candidate.
- `test_deterministic_replay_produces_identical_outcome` -- the same fixture evaluated twice under two independent identities produces byte-for-byte identical decision, reasons, measurements, and evaluation timestamp.
- `test_lookahead_probe_reference_statistics_exclude_the_evaluation_bar` -- see Section 14.

Additionally verified via a real subprocess CLI invocation (`python -m empirical_platform.entrypoints.evaluate_trading_observation ...` / `get_decision_candidate`) against a separate disposable container during development, matching the established real-external-caller verification technique used in every prior milestone.

## 14. Independent Mathematical Verification (Phase 16)

`tests/unit/test_decision_candidate_independent_verification.py`: a separately-authored recomputation (`_independently_recompute`) that reads the raw fixture JSON directly and recomputes `reference_high` (via Python's builtin `max`) and `reference_average_volume` (via `statistics.mean`) **without calling `strategy.evaluate()` and without constructing `Bar`/`ObservationWindow` objects** -- the only code shared with the production path is the fixture files themselves. All three fixtures' independently-recomputed decision and measurements are asserted equal to the real production `evaluate()` output. 3/3 passing.

## 15. Look-Ahead-Bias Audit (Phase 18, MANDATORY)

**Structural defense**: `ObservationWindow.__post_init__` enforces strictly increasing timestamps with no duplicates (`market_data.py`), and `evaluation_bar`/`reference_bars` are defined as `bars[-1]`/`bars[:-1]` respectively. This makes it **structurally impossible** to construct a window containing any bar dated after the evaluation bar -- there is no code path, buggy or otherwise, through which a bar the caller did not choose to include could enter an evaluation. The evaluation cutoff is therefore always exactly the evaluation bar's own timestamp; the included set is exactly `window.bars` (all of them, both reference and evaluation); the excluded set is everything the caller chose not to include when constructing the window -- there is no external data source, so "excluded" is entirely a caller decision, never a system-side lookup.

**Residual risk audited**: given that structural defense, the one meaningful look-ahead-adjacent risk left in this architecture is narrower -- whether the evaluation bar's **own** OHLCV values could silently contaminate the reference-window statistics it is compared against (e.g. an off-by-one bug slicing `window.bars[-reference_window_size:]` instead of `window.reference_bars[-reference_window_size:]`, which would fold the evaluation bar into its own baseline). `evaluate()` (`strategy.py`) computes `reference_bars = window.reference_bars` before ever touching `parameters.reference_window_size`, so this class of bug is already structurally avoided in the current implementation -- but Phase 18 requires a regression test that would fail if it were ever reintroduced.

**Regression test**: `synthetic_aapl_1min_lookahead_probe.json` -- five ordinary reference bars (`reference_high = 100.50`, `reference_average_volume = 1012`) followed by an evaluation bar with a deliberately extreme `high = 200.00` and `volume = 5000`, but a `close = 150.00` chosen to clear the *true* reference high (100.50) while falling *short* of the *contaminated* reference high (200.00) a leaking implementation would compute. Under the correct implementation: `150.00 > 100.50` (price condition true) and `5000 > 1012` (volume condition true) -> `LONG_CANDIDATE`. Under a hypothetical off-by-one leak (folding the evaluation bar into its own 5-bar reference slice, dropping the oldest true reference bar): `reference_high` would jump to `200.00`, flipping the price condition to false and the decision to `NO_TRADE`. `test_lookahead_probe_reference_statistics_exclude_the_evaluation_bar` (integration) and `test_lookahead_probe_fixture_matches_independent_recomputation` (independent-verification unit test) both assert the correct `LONG_CANDIDATE` outcome with `reference_high == 100.50` and `reference_average_volume == 1012`, and would fail loudly under the described bug class. Both pass against the current implementation.

## 16. Hostile Trading Review Summary (Phase 17)

Twenty-question review conducted against the implementation; findings folded inline (no correction milestone):

1. **Determinism** -- `evaluate()` is a pure function of `(window, parameters)`; no randomness, no wall-clock read, no I/O. Confirmed by `test_deterministic_replay_produces_identical_outcome` at both unit and integration level.
2. **Decimal/numeric semantics** -- all price fields are `Decimal`; `reference_average_volume` is computed as `Decimal` division, never `float`. Confirmed by type checks in `Bar.__post_init__` and by exact `Decimal` equality assertions throughout the test suites.
3. **Timestamp ordering** -- enforced by `ObservationWindow.__post_init__` (strictly increasing, tz-aware).
4. **Duplicate-bar rejection** -- covered by `test_window_rejects_duplicate_timestamps`.
5. **Interval consistency** -- `ObservationWindow` requires one consistent `BarInterval` across all bars; covered by `test_window_rejects_mismatched_interval`.
6. **Instrument consistency** -- same enforcement; covered by `test_window_rejects_mismatched_instrument`.
7. **Strategy-version preservation** -- `DecisionCandidate.strategy_id`/`strategy_version` are always the module constants, persisted and round-tripped; confirmed by acceptance-test SQL assertions.
8. **Decision reproducibility** -- see item 1.
9. **NO_TRADE correctness** -- see Section 9.
10. **Positive-candidate correctness** -- see Section 6/13.
11. **Measurement correctness** -- see Section 14 (independent verification).
12. **Reason-code correctness** -- always exactly 2, independently reported per condition; confirmed by unit tests covering all four combinations of price/volume condition truth.
13. **Persistence round-trip** -- see Section 10/13.
14. **Evidence/core integration** -- see Section 8/13.
15. **No look-ahead bias** -- see Section 15.
16. **No future-bar usage** -- see Section 15 (structural defense).
17. **No randomness** -- confirmed by source inspection of `strategy.py` (no `random` import, no non-deterministic input).
18. **No LLM dependency** -- confirmed by source inspection; no network call, no model invocation anywhere in `decision_candidate`.
19. **No profit guarantee encoded** -- no field, comment, or return value anywhere in `decision_candidate` asserts or implies expected return, win rate, or profitability; see the disclaimer in Section 6 and this document's own title.
20. **No unrelated scope creep** -- confirmed: no HTTP/UI layer, no `Run.cancel()`/`EvidencePackage.invalidate()` work, no unrelated aggregate-completeness work was touched this milestone; `git status`/`git diff` confirm the changeset is limited to `decision_candidate`, its usecases/entrypoints/persistence/migration, and this governance document.

## 17. In-Scope

Market-data domain (`Instrument`/`Bar`/`BarInterval`/`ObservationWindow`), strategy contract and `evaluate()` function, `DecisionCandidate` record and `DecisionCandidateRepository` Protocol, `PostgresDecisionCandidateRepository` and its migration, two usecases (`evaluate_trading_observation`, `get_decision_candidate`), two production entrypoints and their `pyproject.toml` registration, three labeled synthetic fixture files, one PostgreSQL acceptance test file (four scenarios), one independent-verification unit test file (three scenarios), the architecture-checker wiring required to keep the boundary honest, and this governance document.

## 18. Out-of-Scope

Any transport/HTTP/UI layer; any live or historical market-data ingestion; any additional strategy beyond the one selected; any portfolio/position/order/risk/execution modeling; any change to Campaign/Run/EvidencePackage/Review aggregate behavior; any change to `Run.cancel()`/`EvidencePackage.invalidate()`/any other aggregate-completeness gap; any claim, benchmark, or backtest asserting the selected strategy is profitable.

## 19. M058 Boundary

This scope selects exactly one MILESTONE-057 capability. No MILESTONE-058 capability, terminology, or sequencing decision is made anywhere in this document. **M057 does not claim the strategy is profitable.**

## 20. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
