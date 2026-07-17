# MILESTONE 000B.4 - PHASE 2, CATEGORY 1 EMPIRICAL VALIDATION PROTOCOL

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000B.4-P2-C1-EVP |
| Title | MILESTONE 000B.4 - PHASE 2, CATEGORY 1 EMPIRICAL VALIDATION PROTOCOL |
| Version | 1.0 |
| Status | DRAFT / PROTOCOL UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Independent Quality Reviewer | Independent Reviewer role - not currently filled by an independent human; MILESTONE-000A ownership caveat applies by citation |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - this protocol is not approved or frozen |
| Governing baselines | MILESTONE-000A v1.1; MILESTONE-000B.0 v1.2; MILESTONE-000B.1 v1.0; MILESTONE-000B.2 v1.2; MILESTONE-000B.3 v1.2; MILESTONE-000B.4 Phase 1 v1.1 |
| Current research input | MILESTONE-000B.4 Phase 2 Category 1 L1 Market Data v1.4 |
| Change log | v1.0: initial vendor-neutral empirical validation protocol for Category 1 L1 trades, quotes, and NBBO. Designs the experiment only; performs no testing, ranking, recommendation, vendor selection, vendor rejection, implementation, or Decision Freeze. |

### 1A. Identifier Continuity Check

Before creating identifiers, the current Version 1.4 research document was checked for identifier ceilings:

| Namespace | Highest observed identifier | New identifiers created here |
|---|---:|---|
| RES | RES-0034 | RES-0035 through RES-0040 |
| SRC | SRC-0031 | None |
| DEC | DEC-0033 | DEC-0034 through DEC-0040 |
| ASS | ASS-0010 | ASS-0011 through ASS-0013 |
| CONF | CONF-0001 | None |
| CLM | CLM-0057 | None |
| RISK | RISK-0014 | RISK-0015 through RISK-0029 |

No existing identifier is repurposed. No new SRC or CLM identifiers are created because this protocol introduces no new external source evidence and makes no vendor-capability claim beyond the design of the future test procedure.

### 1B. Prior-Baseline Verification Status

| Artifact | Treatment in this protocol |
|---|---|
| MILESTONE-000A v1.1 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.0 v1.2 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.1 v1.0 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.2 v1.2 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.3 v1.2 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.4 Phase 1 v1.1 | RELIED UPON BY CITATION ONLY |
| MILESTONE-000B.4 Phase 2 Category 1 v1.4 | VERIFIED AGAINST LOADED CURRENT DOCUMENT for identifier ceilings, current status, candidate universe, and unresolved blockers |

No frozen baseline was edited. No independent validation is claimed for any frozen baseline that was not directly loaded and checked in this protocol pass.

---

## 2. Purpose

This document defines the vendor-neutral empirical validation protocol that will later be used to test actual Category 1 L1 trades, quotes, and NBBO data from candidate vendors.

The protocol designs the experiment. It does not execute the experiment.

Its purpose is to make every candidate testable under the same reproducible methodology before any future vendor Decision Freeze.

---

## 3. Scope

In scope:

- US-listed common equities.
- Broad-market and sector ETFs.
- Raw trades.
- Raw quotes.
- NBBO, consolidated BBO, or reconstructible best-bid/best-offer evidence.
- Historical data relevant to the approved Core Trading Session.
- Vendor-neutral empirical testing procedure.
- B3 thirty-criterion operationalization for Category 1.
- Evidence capture, preservation, auditability, and rerun rules.

Out of scope:

- Other asset classes.
- Execution brokers as execution venues.
- Category 2 or later data domains.
- Production implementation architecture.
- Vendor scoring, ranking, recommendation, selection, or rejection.
- Statistical-power or final calibration decisions deferred to MILESTONE-000C.

---

## 4. Explicit Non-Goals

This protocol does not download data, call APIs, open accounts, purchase subscriptions, run tests, compute vendor scores, choose sample members, set affordability thresholds, or freeze any vendor decision.

It also does not alter MILESTONE-000B.3's 30-criterion inventory, create a 31st criterion, or silently invent fields not represented by the inherited B2/B3 governance boundary.

---

## 5. Governing Inputs and Dependency Boundary

The protocol depends on:

- MILESTONE-000B.2 for canonical field and domain expectations, relied upon by citation.
- MILESTONE-000B.3 for the frozen 30-criterion data-quality baseline, relied upon by citation.
- MILESTONE-000B.4 Phase 1 for the six frozen vendor dimensions, relied upon by citation.
- MILESTONE-000B.4 Phase 2 Category 1 v1.4 for current candidate categories, unresolved risks, and deferred items, verified from the loaded document.

Dependency boundary:

- This protocol may define how to test a criterion.
- It may not change the criterion.
- It may define result states.
- It may not declare a vendor result.
- It may define evidence artifacts.
- It may not infer license permission from marketing or product descriptions.

---

## 6. Empirical Validation Objectives

The future empirical validation must answer:

- Whether each tested product exposes enough raw evidence to evaluate each applicable B3 criterion.
- Whether observed raw data passes, fails, is not applicable, is not testable, is calibration-pending, or is blocked by access.
- Whether the vendor product/feed/version tested is comparable to other candidates.
- Whether timestamp, sequence, correction, venue, condition, and snapshot evidence is preserved.
- Whether the evidence can be rerun, reviewed, and traced to an immutable raw snapshot.

---

## 7. Candidate-Neutral Testing Principles

1. Identical test design applies to all candidates.
2. Product/feed/version differences are recorded, not hidden.
3. Absence is never converted to zero.
4. A missing field is not synthesized unless labeled project-derived.
5. Documentation support is never empirical PASS.
6. Full-feed, broker-filtered, SIP, direct-feed, historical, live, tick, bar, normalized, and raw products are compared only with their class differences visible.
7. A vendor is not penalized for a capability that belongs to a different product tier unless that tier difference is explicitly recorded.
8. All raw records remain immutable.

---

## 8. Data-Access and Eligibility Preconditions

Before any future test begins, the tester must document:

- Vendor legal entity.
- Product, feed, terminal, API, or delivery mechanism.
- Entitlement tier.
- Account or institution requirement.
- Professional/non-professional status if applicable.
- Retention rights.
- Redistribution and publication restrictions.
- Derived-data/non-display rights if relevant.
- Whether testing, storage, and reviewer access are permitted.
- Product version and extraction path.

If any permission is unresolved, the future result state is **BLOCKED BY DATA ACCESS** or **APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED**, not PASS or FAIL.

---

## 9. Standardized Test Dataset Specification

The future test package must contain the same vendor-neutral structure for every candidate:

| Component | Protocol requirement | Numeric status |
|---|---|---|
| Instrument set | Must include US-listed common equities and broad-market/sector ETFs; listing venues must be represented; liquid and less-liquid instruments must both be included | Statistical-design question deferred to 000C |
| Date set | Must include ordinary Core Trading Session days, half-days, known halt/LULD-pause periods, corporate-action-adjacent dates where relevant, and ordinary no-special-event days | Statistical-design question deferred to 000C |
| Session boundary | Must use approved Core Trading Session boundary with timezone and daylight-saving handling recorded | Inherited by citation |
| Raw trades | Required where product claims trade support | Minimum engineering requirement |
| Raw quotes | Required where product claims quote support | Minimum engineering requirement |
| NBBO/BBO | Required as raw NBBO, consolidated BBO, vendor BBO, or reconstructible BBO with source classification | Minimum engineering requirement |
| Bars | Used only where fixed-slot completeness C1a is evaluated | Criterion-dependent |
| Metadata | Vendor, product, feed, entitlement, delivery mechanism, extraction time, product version, account status, and license evidence | Minimum engineering requirement |
| Snapshot identity | Dataset snapshot ID and extraction manifest | Minimum engineering requirement |
| Raw copy | Immutable raw snapshot with checksum/hash | Minimum engineering requirement |
| Normalized copy | Project-normalized comparison copy plus transformation log | Minimum engineering requirement |

No final sample size is chosen here. Any sample-size, power, or statistical coverage number is deferred to MILESTONE-000C unless inherited from a frozen baseline.

---

## 10. Sampling Design

The sampling framework must be reproducible but not executed in this protocol.

Date selection rules:

- Draw from a predeclared date universe.
- Preserve ordinary, half-day, halt/LULD, corporate-action-adjacent, and no-special-event strata.
- Record the reason each date enters the sample.
- Do not replace an unavailable vendor date silently; record unavailable as unavailable.

Instrument selection rules:

- Draw from a predeclared instrument universe.
- Include common equities and ETFs.
- Include listing-venue representation.
- Include liquid and less-liquid strata.
- Preserve delisted, renamed, symbol-changed, and corporate-action-affected instruments where applicable.

Comparability rules:

- The same instrument/date/session package is used across vendors.
- Product versions and feed variants are recorded.
- If a vendor cannot provide the exact product class, the test records that mismatch rather than substituting silently.
- Future reruns preserve the original sample manifest and append a rerun manifest.

Protocol mechanics are defined here. Calibration and statistical-power questions are deferred to 000C.

---

## 11. Canonical Field-Mapping Procedure

For each vendor product, create a field map before testing:

| Step | Requirement |
|---|---|
| 1 | Preserve raw vendor field name, raw type, raw value, units, timezone, precision, and source record layout |
| 2 | Map to canonical project fields only when meaning is documented or contract-confirmed |
| 3 | Mark unmapped vendor fields as unmapped; do not discard |
| 4 | Mark unmapped vendor condition/venue codes as unmapped; do not coerce |
| 5 | Mark every derived field as project-derived or vendor-derived |
| 6 | Record transformations, rounding, timezone conversion, symbol mapping, and code mapping |
| 7 | Distinguish raw, adjusted, corrected, cancelled, replacement, and derived records |

Canonical mapping failure does not equal vendor FAIL unless the criterion's required evidence is absent after documented mapping attempts.

---

## 12. Timestamp and Clock-Integrity Test Procedure

Timestamp classes:

- Exchange/event timestamp.
- Source publication timestamp.
- SIP or venue dissemination timestamp.
- Vendor receipt timestamp.
- Vendor processing timestamp.
- System ingestion timestamp.
- Normalization timestamp.
- Decision-available timestamp.
- Research execution timestamp.

For each timestamp, record state:

- present.
- absent.
- vendor-derived.
- project-derived.
- contract-confirmed.
- empirically verified.
- unverifiable.

Testing requirements:

- Detect timestamp truncation, timezone conversion error, daylight-saving ambiguity, duplicate timestamps, sequence-number ties, negative lag, non-monotonic venue event time, and cross-clock-domain mismatch.
- Do not assume every vendor exposes every timestamp.
- Decision-available timestamp may be vendor-native or project-derived, but derivation must be reproducible and must cite source timestamp fields.

---

## 13. B3 Thirty-Criterion Applicability Matrix

Allowed applicability states:

- **APPLICABLE - EMPIRICALLY TESTABLE:** direct data can test the criterion.
- **APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED:** criterion depends on vendor documentation, contract, entitlement, or support confirmation.
- **NOT APPLICABLE TO CATEGORY 1:** criterion belongs to a different domain for pure L1 trades/quotes/NBBO.
- **NOT TESTABLE WITH CURRENT PRODUCT:** product lacks required evidence even if the criterion is conceptually relevant.
- **CALIBRATION-PENDING:** criterion needs a later 000C calibration decision.
- **BLOCKED BY DATA ACCESS:** access, entitlement, or license prevents testing.

Allowed result states:

- **PASS:** future empirical evidence satisfies the criterion.
- **FAIL:** future empirical evidence violates the criterion.
- **NOT APPLICABLE:** criterion is outside Category 1 or product scope under the applicability rule.
- **NOT TESTABLE:** product lacks required test evidence.
- **CALIBRATION-PENDING:** no result until calibration is frozen.
- **BLOCKED BY DATA ACCESS:** access or license prevents testing.

| ID | Criterion name | Dimension | Severity | Applicability | Required raw fields | Required metadata | Test input | Test logic | Evidence artifact | Initial result state | Direct vendor data required | Source/support substitute | Numeric calibration | Linked deferred item | Downstream consequence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1a | Deterministic fixed-slot expected-record count | Completeness | Structural | APPLICABLE - EMPIRICALLY TESTABLE when bars are used | Bar timestamp, interval, symbol | Session calendar, product type | Bar records | Expected slots vs observed slots | C1a result file | BLOCKED BY DATA ACCESS | Yes | No | Deferred to 000C if tolerance needed | DEF-0001 | Blocks bar-derived completeness claim |
| C1b-i | Explicit source-outage indicator | Completeness | Structural | APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED | Outage flags if exposed | Outage policy | Feed status records/docs | Verify explicit outage evidence | C1b-i evidence file | BLOCKED BY DATA ACCESS | Usually | Yes | No | DEF-0001 | Blocks completeness explanation |
| C1b-ii | Sequence-gap detection | Completeness | Structural | APPLICABLE - EMPIRICALLY TESTABLE when sequence exists | Sequence number, venue, timestamp | Sequence domain | Trades/quotes | Detect gaps/resets per sequence domain | C1b-ii gap report | BLOCKED BY DATA ACCESS | Yes | Support can confirm sequence semantics | No | DEF-0001 | Blocks sequence-based completeness |
| C1b-iii | Timestamp-continuity computability | Completeness | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Timestamp(s), symbol, venue | Timestamp precision/timezone | Trades/quotes | Compute inter-arrival continuity | C1b-iii continuity file | BLOCKED BY DATA ACCESS | Yes | No | Deferred to 000C for tolerance | DEF-0001 | Blocks continuity evidence |
| C2 | Session-window conformance | Completeness | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Timestamp, symbol, record type | Session calendar/timezone | Trades/quotes | Classify inside/outside Core Session | C2 session report | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks session-scoped comparison |
| C3 | Quote-availability measurement | Completeness | Calibration-Dependent | CALIBRATION-PENDING | Bid/ask, timestamp, symbol | Session calendar | Quotes/NBBO | Compute availability metric after calibration | C3 metric file | CALIBRATION-PENDING | Yes | No | Yes - 000C | DEF-0002 | Blocks calibrated quote-availability conclusion |
| C4 | Halt-aware exclusion | Completeness | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Trades/quotes, halt/LULD markers | Halt/LULD source | Event-day data | Exclude known halt/LULD intervals | C4 exclusion report | BLOCKED BY DATA ACCESS | Yes | Halt source can supplement | No | DEF-0001 | Blocks completeness interpretation |
| C5 | Point-in-time universe reconstructability | Completeness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Reference universe | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No Category 1 blocker |
| C6 | Survivorship presence in reference data | Completeness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Reference data | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No Category 1 blocker |
| C7 | Predecessor/successor lineage resolution | Completeness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Corporate/reference lineage | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No Category 1 blocker |
| T1 | Decision-available timestamp derivation | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Event/publication/vendor/ingestion timestamp | Clock domain | Trades/quotes | Derive decision-available timestamp reproducibly | T1 derivation log | BLOCKED BY DATA ACCESS | Yes | Timestamp semantics may require support | No | DEF-0001 | Blocks temporal backtest safety |
| T2 | Venue-level event-time monotonicity | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Event timestamp, venue, sequence if present | Venue/session | Trades/quotes | Check monotonicity by venue stream | T2 monotonicity report | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks venue-time integrity |
| T3 | Ingestion-lag integrity | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE when lag clocks exist | Event and receipt/ingestion timestamps | Clock-domain definitions | Trades/quotes | Compute lag and detect negative/backdated lag | T3 lag report | BLOCKED BY DATA ACCESS | Yes | Support can confirm clock semantics | Calibration deferred for tolerance | DEF-0001 | Blocks latency/availability interpretation |
| T4 | Duplicate-record detection | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Record keys, timestamps, symbol, venue | Duplicate policy | Trades/quotes | Identify duplicate raw records and keys | T4 duplicate report | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks record integrity |
| T5 | Correction/cancellation linkage | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE when corrections exist | Correction/cancel code, original ID | Correction semantics | Trades/quotes | Verify original retained and linked | T5 correction report | BLOCKED BY DATA ACCESS | Yes | Support can confirm semantics | No | DEF-0001 | Blocks correction integrity |
| T6 | Replay ordering | Temporal Integrity | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Event time, sequence, record type | Replay policy | Trades/quotes | Reconstruct event-order replay | T6 replay log | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks replay safety |
| A1 | Positive price validity | Accuracy | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Price fields | Price scale | Trades/quotes | Detect non-positive prices where invalid | A1 price report | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks accuracy PASS |
| A2 | Crossed/locked quote handling | Accuracy | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Bid/ask prices, timestamps | Quote condition policy | Quotes/NBBO | Detect crossed/locked states and classify policy | A2 quote report | BLOCKED BY DATA ACCESS | Yes | Support may explain policy | Calibration deferred if tolerance needed | DEF-0002 | Blocks quote accuracy conclusion |
| A3 | Size validity | Accuracy | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Trade/quote size | Size units | Trades/quotes | Detect negative or invalid sizes | A3 size report | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks size accuracy |
| A4 | Trade/sale-condition mapping | Accuracy | Structural | APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED | Condition codes | Code dictionary | Trades | Map every observed code | A4 mapping file | BLOCKED BY DATA ACCESS | Yes | Yes | No | DEF-0004 | Blocks condition-aware tests |
| A5 | Venue-code conformance | Accuracy | Structural | APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED | Venue/exchange code | Venue dictionary | Trades/quotes | Map every observed venue code | A5 venue map | BLOCKED BY DATA ACCESS | Yes | Yes | No | DEF-0004 | Blocks venue analysis |
| A6 | Session consistency | Accuracy | Structural | APPLICABLE - EMPIRICALLY TESTABLE | Timestamp, session flags if any | Session calendar | Trades/quotes | Cross-check record session classification | A6 session consistency file | BLOCKED BY DATA ACCESS | Yes | No | No | DEF-0001 | Blocks session analysis |
| A7 | Adjustment transformation | Accuracy | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Corporate-action policy | N/A | N/A for pure raw L1 feed | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No pure L1 blocker |
| P1 | Original-record retrievability after correction | Provenance | Structural | APPLICABLE - EMPIRICALLY TESTABLE when corrections exist | Original/corrected record IDs | Correction policy | Corrected records | Verify original is retrievable | P1 provenance report | BLOCKED BY DATA ACCESS | Yes | Support can confirm retention | No | DEF-0001 | Blocks provenance PASS |
| P2 | Correction decision-available timestamp correctness | Provenance | Structural | APPLICABLE - EMPIRICALLY TESTABLE when corrections exist | Correction timestamp(s) | Clock semantics | Corrected records | Verify correction availability timing | P2 correction timing file | BLOCKED BY DATA ACCESS | Yes | Support can confirm semantics | No | DEF-0001 | Blocks correction timing |
| P3 | Dataset snapshot-ID linkage | Provenance | Structural | APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED | Snapshot ID, file ID, extraction ID | Manifest | Test dataset | Verify every output links to snapshot | P3 manifest audit | BLOCKED BY DATA ACCESS | Yes | Yes | No | DEF-0005 | Blocks reproducibility |
| CA1 | Corporate-action lineage completeness | Corporate-Action Correctness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Corporate-action data | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No pure L1 blocker |
| CA2 | Corporate-action decision-available lineage correctness | Corporate-Action Correctness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Corporate-action data | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No pure L1 blocker |
| CA4 | Raw/adjusted non-conflation | Corporate-Action Correctness | Structural | APPLICABLE - DOCUMENTATION OR CONTRACT CONFIRMATION REQUIRED | Raw/adjusted flag if any | Adjustment policy | Trades/quotes/bars if present | Verify raw data not silently adjusted | CA4 raw-adjusted audit | BLOCKED BY DATA ACCESS | Yes where bars/adjustment present | Yes | No | DEF-0004 | Blocks raw-data safety |
| CA6 | Revision-history population | Corporate-Action Correctness | Structural | NOT APPLICABLE TO CATEGORY 1 | N/A | Corporate-action revisions | N/A | N/A | Scope note | NOT APPLICABLE | No | Yes for scope | No | DEF-0003 | No pure L1 blocker |

Reconciliation: exactly 30 unique criteria are preserved: Completeness 10, Temporal Integrity 6, Accuracy 7, Provenance 3, Corporate-Action Correctness 4. P4 is an alias of T5; CA3 is an alias of A7; CA5 is an alias of C7. C1b-ii applicable/not applicable are states of one criterion. C1b-iv remains excluded and is not counted.

---

## 14. Per-Criterion Empirical Test Specifications

Each applicable criterion uses this common evidence structure: objective, inputs, prerequisites, canonical fields, normalization assumptions, deterministic procedure, evidence captured, pass condition, fail condition, non-applicable condition, blocked/not-testable condition, severity consequence, false-positive risk, false-negative risk, calibration boundary, and rerun rule.

| ID | Executable-in-principle test specification |
|---|---|
| C1a | Objective: verify fixed-slot bar completeness when bars are used. Inputs: bar timestamps and interval. Prerequisites: bar product and session calendar. Fields: symbol, interval, bar timestamp. Procedure: build expected Core Session slots; compare observed slots. Pass: all required slots accounted for under frozen tolerance. Fail: unexplained missing/extra slots. N/A: no bar product used. Blocked: no data access. False positive: holiday/half-day calendar error. False negative: vendor silently fills bars. Calibration: tolerance deferred to 000C. Rerun: same manifest/calendar. |
| C1b-i | Objective: verify explicit source-outage evidence. Inputs: outage flags/status records/docs. Procedure: check whether source outage is separately represented from no trading. Pass: explicit outage evidence exists and links to affected intervals. Fail: outage interval indistinguishable from no data. N/A: none for data products claiming completeness. Blocked: no entitlement/status evidence. False positive: vendor uses different terminology. False negative: outage feed not included in test entitlement. Calibration: none. Rerun: include same event days. |
| C1b-ii | Objective: detect sequence gaps when sequence exists. Inputs: sequence number, venue, stream. Procedure: partition by documented sequence domain; detect missing, duplicate, reset, and wrap states. Pass: gaps are detectable or sequence not applicable with confirmation. Fail: sequence claims exist but gaps cannot be audited. N/A: no sequence domain offered and criterion classified not applicable for product. Blocked: no sequence documentation/data. False positive: unrecognized reset. False negative: vendor resequences data. Calibration: none. Rerun: same raw stream. |
| C1b-iii | Objective: determine timestamp-continuity computability. Inputs: event/publication/vendor timestamps. Procedure: sort by stream; compute inter-arrival intervals and discontinuities. Pass: continuity can be computed with documented clocks. Fail: no usable timestamp continuity evidence. Blocked: no timestamp access. False positive: clock-domain mix. False negative: vendor smoothing. Calibration: tolerance deferred to 000C. Rerun: same raw timestamps. |
| C2 | Objective: validate Core Session conformance. Inputs: timestamps, session calendar, record type. Procedure: classify every record as pre/core/post/unknown; flag unexpected core-scope records. Pass: records can be classified and scoped. Fail: timestamp/session ambiguity prevents scoping. False positive: DST/calendar error. False negative: vendor prefilters without disclosure. Calibration: none. Rerun: same calendar version. |
| C3 | Objective: compute quote availability after calibration. Inputs: quotes/NBBO and session intervals. Procedure: calculate availability according to future 000C metric. Pass/fail: unavailable until calibration. State: CALIBRATION-PENDING. False positive/negative: quote staleness and outage classification. Rerun: after calibration with same raw data. |
| C4 | Objective: apply halt/LULD-aware exclusions. Inputs: trades/quotes plus halt/LULD source. Procedure: join intervals to records; exclude or classify impacted periods. Pass: halt-aware completeness can be computed. Fail: known halt/LULD periods cannot be separated. False positive: stale halt source. False negative: missed venue-specific pause. Calibration: none. |
| T1 | Objective: derive decision-available timestamp. Inputs: all exposed timestamps. Procedure: classify clock domains; select or derive earliest defensible decision-available time without lookahead. Pass: derivation is reproducible. Fail: no defensible timestamp. False positive: using research execution time. False negative: ignoring valid vendor receipt time. |
| T2 | Objective: test venue-level monotonicity. Inputs: venue, event timestamp, sequence if present. Procedure: sort by venue stream and detect inversions. Pass: monotonicity holds or inversions are documented corrections. Fail: unexplained inversions. False positive: multi-channel merge. False negative: vendor sorting. |
| T3 | Objective: test ingestion-lag structural integrity. Inputs: event and receipt/ingestion timestamps. Procedure: compute lag and flag negative/backdated/truncated values. Pass: lag is non-negative under documented clocks. Fail: unexplained negative or impossible lag. Calibration: tolerance deferred to 000C if needed. |
| T4 | Objective: detect duplicates. Inputs: raw record keys and all fields. Procedure: compute exact and semantic duplicate groups. Pass: duplicates absent or explainable by documented semantics. Fail: unexplained duplicate raw records. False positive: legitimate correction pair. False negative: changed vendor IDs. |
| T5 | Objective: verify correction/cancellation linkage and original retention. Inputs: correction/cancel codes, original IDs, timestamps. Procedure: trace each correction/cancel to original and replacement. Pass: lineage complete. Fail: unlinked or missing original where required. Alias: P4 maps here and is not separate. |
| T6 | Objective: verify replay ordering. Inputs: event time, sequence, record type. Procedure: reconstruct event replay ordering by documented clocks and tie-breakers. Pass: deterministic replay is possible. Fail: ordering ambiguous for decision use. False positive: using vendor processing order as event order. |
| A1 | Objective: enforce positive-price validity. Inputs: trade/bid/ask prices. Procedure: scan for non-positive prices where invalid. Pass: no unexplained invalid prices. Fail: invalid prices not documented as special codes. False positive: special condition not mapped. |
| A2 | Objective: test crossed/locked quote handling. Inputs: bid/ask prices and condition codes. Procedure: identify crossed/locked states and classify by condition/session/halt. Pass: states are valid or explainable. Fail: unexplained invalid quote state. Calibration: tolerance/handling deferred if needed. |
| A3 | Objective: validate sizes. Inputs: trade/quote sizes and units. Procedure: detect negative or invalid sizes. Pass: sizes conform to documented units and constraints. Fail: unexplained invalid size. False positive: odd-lot/unit mapping error. |
| A4 | Objective: map trade/sale conditions. Inputs: raw condition codes and dictionary. Procedure: enumerate observed codes; map each to documented meaning. Pass: all material codes mapped. Fail: unmapped material codes. Blocked: no dictionary. |
| A5 | Objective: map venue/exchange codes. Inputs: venue codes and venue dictionary. Procedure: enumerate and map observed venue codes. Pass: all material venue codes mapped. Fail: unmapped material venue codes. Blocked: no venue dictionary. |
| A6 | Objective: test cross-field session consistency. Inputs: timestamps, session flags, venue, conditions. Procedure: compare timestamp-derived session against vendor flags/conditions. Pass: consistent or documented. Fail: unexplained conflict. |
| A7 | Objective: classify adjustment transformation applicability. Category 1 pure raw L1 feeds are NOT APPLICABLE unless bars/adjusted fields are included. If included, verify versioned adjustment policy. Alias: CA3 maps here. |
| P1 | Objective: verify original-record retrievability after correction. Inputs: original/correction IDs. Procedure: retrieve original and corrected records. Pass: original retained. Fail: original missing. Blocked: no correction population in sample. |
| P2 | Objective: verify correction decision-available timestamp. Inputs: correction timestamp and original timestamp. Procedure: ensure correction availability is not backdated. Pass: timing defensible. Fail: correction appears available before dissemination. |
| P3 | Objective: verify snapshot linkage. Inputs: manifest, file IDs, extraction ID. Procedure: trace every result to snapshot ID and checksum. Pass: complete linkage. Fail: orphan result file. |
| CA1 | NOT APPLICABLE TO CATEGORY 1 pure L1 trade/quote feed; requires corporate-action domain data. If a tested product bundles corporate-action data, defer to appropriate category protocol. |
| CA2 | NOT APPLICABLE TO CATEGORY 1 pure L1 trade/quote feed; decision-available corporate-action lineage belongs to corporate-action protocol. |
| CA4 | Objective: prevent raw/adjusted conflation. Inputs: raw/adjusted flags, vendor policy, bars if present. Procedure: verify raw trades/quotes are not silently adjusted; bars must disclose adjustment status. Pass: raw/adjusted separation documented and observed. Fail: silent conflation. |
| CA6 | NOT APPLICABLE TO CATEGORY 1 pure L1 trade/quote feed; corporate-action revision history belongs to corporate-action protocol. |

---

## 15. Data-Capture and Evidence Preservation Standard

Each future vendor test must produce:

- Test manifest.
- Vendor/product/feed identity record.
- Entitlement and license evidence.
- Extraction timestamp.
- Source URLs or contractual references.
- Immutable raw snapshot.
- Checksum/hash.
- Normalized snapshot.
- Transformation log.
- Per-criterion result file.
- Exception log.
- Conflict log.
- Rerun instructions.
- Environment/version manifest.
- Reviewer sign-off field.
- Decision-time freshness verification record.

No proprietary sample may be published unless license terms explicitly permit publication.

---

## 16. Vendor Test Adapter / Normalization Boundary

The vendor test adapter is an audit boundary, not production architecture.

It must:

- Preserve raw source records unchanged.
- Retain every original timestamp.
- Retain original condition and venue codes.
- Retain vendor product/feed/version metadata.
- Record every field transformation.
- Never synthesize a missing field without labeling it derived.
- Never convert absence into zero.
- Never silently convert adjusted data into raw data.
- Preserve correction/cancellation lineage.
- Expose unmapped fields and unmapped codes.
- Separate vendor-native evidence from project-derived evidence.

The adapter may normalize field names for comparison, but raw evidence remains authoritative.

---

## 17. Pass, Fail, Not Applicable, Not Testable, and Calibration-Pending States

| State | Definition | May support Decision Freeze? |
|---|---|---|
| PASS | Empirical evidence satisfies the criterion under the approved protocol | Yes, if all other gates pass |
| FAIL | Empirical evidence violates the criterion | No for blocking criteria unless later waived by governance |
| NOT APPLICABLE | Criterion is outside Category 1 or product scope under the applicability matrix | Yes, only with documented scope rationale |
| NOT TESTABLE | Product lacks required evidence even after access is granted | Usually no; depends on severity |
| CALIBRATION-PENDING | Criterion awaits 000C calibration | No |
| BLOCKED BY DATA ACCESS | Data, entitlement, license, or retention right prevents testing | No |
| DOCUMENTATION/CONTRACT REQUIRED | Empirical result depends on source/support/contract evidence | No until confirmed |

Documentation alone cannot create PASS.

---

## 18. Severity Handling and Blocking Logic

- Structural blocking criteria fail the vendor/product test unless a later governance decision explicitly accepts the limitation.
- Calibration-dependent C3 cannot pass or fail until calibration is completed.
- NOT APPLICABLE must cite the applicability matrix.
- NOT TESTABLE must identify the missing evidence and whether it is product-tier, entitlement, license, or schema related.
- BLOCKED BY DATA ACCESS blocks testing, not necessarily the vendor category.

No numeric severity score is created here.

---

## 19. Cross-Vendor Comparability Controls

Controls:

- Identical instruments and dates.
- Identical Core Session boundaries.
- Identical calendar/timezone logic.
- Equivalent entitlement tier where possible.
- Product class recorded: SIP, direct feed, consolidated feed, broker-filtered, institutional historical product, terminal/API.
- Live versus historical distinction recorded.
- Tick versus bars distinction recorded.
- Raw versus normalized distinction recorded.
- Full-feed versus filtered-broker feed distinction recorded.
- Product version and feed variant recorded.
- Absent data separated from inaccessible data.
- Retail-accessible versus institutional-only products recorded.

A vendor must not be penalized for lacking a capability in the tested tier if a higher tier may contain it; the result must state product-tier mismatch instead.

---

## 20. Reproducibility and Re-Run Requirements

A future rerun must use:

- Original test manifest.
- Original instrument/date selection rules.
- Original raw snapshot if retesting transformation logic.
- New extraction manifest if retesting vendor delivery.
- Versioned code/environment manifest.
- Same calendar and event-reference versions unless rerun objective is to test updated references.
- Delta report explaining all changes from prior run.

Rerun failure must identify whether change is vendor data, entitlement, product version, project normalization, event reference, or calendar logic.

---

## 21. Licensing, Entitlement, and Data-Use Safety Controls

The future test is prohibited from:

- Unauthorized redistribution.
- Storing data beyond licensed retention.
- Using professional/non-professional entitlements incorrectly.
- Testing products not licensed for the project.
- Publishing proprietary samples.
- Combining datasets in a license-violating way.
- Inferring permission from marketing language.

Testing may proceed only after entitlement, retention, storage, reviewer access, and testing rights are confirmed.

---

## 22. Failure, Exception, and Conflict Handling

Exceptions must be logged with:

- Criterion ID.
- Vendor/product/feed.
- Record or interval affected.
- Raw evidence pointer.
- Exception type.
- Whether the exception is vendor-native, project-derived, entitlement-related, or license-related.
- Reviewer disposition.

Create a new CONF only when two credible sources or empirical artifacts materially disagree. Do not create a conflict merely because evidence is absent.

---

## 23. Research Registry Entries

**RES-0035 - Standardized empirical sample design for Category 1**
Status: OPEN. Owner: Research Lead. Scope: Sections 9-10. Sources: prior baselines by citation only. Result: protocol mechanics defined; final sample sizes and statistical power deferred to 000C. Stop condition: approved sample manifest template and 000C calibration/power decisions exist. Last reviewed: 2026-07-12.

**RES-0036 - B3 empirical-test operationalization for Category 1**
Status: PARTIALLY ANSWERED. Owner: Research Lead. Scope: Sections 13-14. Sources: B3 by citation only. Result: all 30 criteria mapped to applicability/result/test procedure. Stop condition: independent protocol audit confirms deterministic test coverage for all applicable criteria. Last reviewed: 2026-07-12.

**RES-0037 - Cross-vendor normalization boundary**
Status: PARTIALLY ANSWERED. Owner: Research Lead. Scope: Sections 11, 16, 19. Result: adapter boundary and comparability controls defined. Stop condition: reviewer validates that normalization cannot hide raw vendor defects. Last reviewed: 2026-07-12.

**RES-0038 - Evidence preservation and reproducibility standard**
Status: PARTIALLY ANSWERED. Owner: Research Lead. Scope: Sections 15, 20. Result: mandatory artifacts and rerun requirements defined. Stop condition: independent audit confirms artifact list is sufficient for Decision Freeze evidence review. Last reviewed: 2026-07-12.

**RES-0039 - Licensing preconditions for empirical testing**
Status: PARTIALLY ANSWERED. Owner: Research Lead. Scope: Sections 8, 21. Result: access, entitlement, retention, and data-use controls defined. Stop condition: legal/project owner review confirms controls are sufficient before vendor data access. Last reviewed: 2026-07-12.

**RES-0040 - Protocol result-state taxonomy**
Status: ANSWERED FOR DRAFT. Owner: Research Lead. Scope: Sections 13, 17, 18. Result: deterministic applicability and result states defined. Stop condition: protocol audit confirms states are complete and non-overlapping. Last reviewed: 2026-07-12.

---

## 24. Decision Records

The following protocol decisions are draft protocol decisions, not vendor-selection decisions.

**DEC-0034 - Standardized test package structure**
Problem: future vendor tests need comparable evidence packages. Options considered: ad hoc per vendor; vendor-native only; standardized manifest plus raw and normalized snapshots. Selected option: standardized manifest with immutable raw snapshot and normalized comparison copy. Rationale: comparability without hiding vendor differences. Strongest support: Sections 9 and 15. Strongest opposition: some vendors may restrict retention. Best alternative explanation: license limits may force smaller evidence artifacts. Reasons it may be wrong: future licenses may prohibit required retention. Disconfirming search: no vendor data accessed. Assumptions: ASS-0011. Risks: RISK-0026. Dependencies: RES-0035, RES-0038. Affected artifacts: test manifest. Validation/reversal: legal/entitlement review shows artifact retention impossible.

**DEC-0035 - Result-state taxonomy**
Problem: documentation, blocked access, calibration, and empirical results must not be conflated. Options: PASS/FAIL only; PASS/FAIL/NA; full state taxonomy. Selected option: full taxonomy in Section 17. Rationale: prevents documentation support from becoming empirical PASS. Support: Section 13. Opposition: more reviewer burden. Reasons it may be wrong: state taxonomy may need expansion after first dry run. Risks: RISK-0029. Dependencies: RES-0040. Validation/reversal: protocol audit finds ambiguous state assignment.

**DEC-0036 - Raw-preservation and adapter boundary**
Problem: normalization can hide defects. Options: normalize only; raw only; raw-preserving adapter. Selected option: raw-preserving adapter with transformation log. Rationale: comparability plus auditability. Support: Sections 11 and 16. Opposition: larger storage burden. Reasons it may be wrong: license retention limits. Risks: RISK-0019, RISK-0026. Dependencies: RES-0037, RES-0038. Validation/reversal: legal or technical audit rejects preservation method.

**DEC-0037 - Cross-vendor comparability standard**
Problem: product/feed differences can create unfair comparisons. Options: compare whatever is available; compare only identical products; compare with explicit product-class controls. Selected option: explicit product-class controls. Rationale: avoids silent tier substitution. Support: Section 19. Opposition: may reduce comparable candidate set. Risks: RISK-0017, RISK-0018, RISK-0020. Dependencies: RES-0037. Validation/reversal: future dry run shows controls insufficient.

**DEC-0038 - Evidence preservation standard**
Problem: future Decision Freeze needs reviewable evidence. Options: summary only; per-criterion artifacts; full artifact bundle. Selected option: full bundle in Section 15. Rationale: traceability and rerun readiness. Opposition: storage/licensing burden. Risks: RISK-0026. Dependencies: RES-0038, ASS-0011. Validation/reversal: license review prohibits required artifacts.

**DEC-0039 - Test authorization and licensing precondition**
Problem: empirical tests may violate license terms. Options: test first; rely on public terms; require entitlement confirmation first. Selected option: require entitlement, retention, and testing-right confirmation first. Rationale: licensing safety. Opposition: slows research. Risks: RISK-0026, RISK-0028. Dependencies: RES-0039. Validation/reversal: project counsel/owner defines alternate process.

**DEC-0040 - Criterion applicability standard**
Problem: Category 1 must preserve B3 while classifying non-L1 criteria. Options: omit non-applicable criteria; mark all testable; preserve all 30 with applicability states. Selected option: preserve all 30 with applicability states. Rationale: maintains canonical B3 count and prevents silent deletion. Opposition: longer protocol. Risks: RISK-0029. Dependencies: RES-0036. Validation/reversal: frozen baseline amendment changes B3.

---

## 25. Assumption Updates

**ASS-0011 - Future vendors will permit retention of enough evidence for audit**
Status: OPEN. Owner: Research Lead. Validation method: entitlement/license review before testing. Deadline: before any vendor data extraction. Risk if false: empirical evidence cannot be preserved for Decision Freeze. Linked risks: RISK-0026.

**ASS-0012 - A common instrument/date manifest can be applied across materially comparable products**
Status: OPEN. Owner: Research Lead. Validation method: dry-run manifest review before vendor testing. Deadline: before empirical execution. Risk if false: cross-vendor comparability weakens. Linked risks: RISK-0015, RISK-0027.

**ASS-0013 - Canonical field mapping can be performed without inventing non-existent fields**
Status: OPEN. Owner: Research Lead. Validation method: adapter dry run on schema samples before empirical scoring. Deadline: before per-criterion testing. Risk if false: normalization may hide vendor limitations. Linked risks: RISK-0019.

---

## 26. Risk Register

| Risk ID | Statement | Trigger | Impact | Preventive control | Detective control | Owner | Closure evidence | Acceptance/blocking condition | Linked RES/DEC/ASS/deferred item |
|---|---|---|---|---|---|---|---|---|---|
| RISK-0015 | Sample-selection bias distorts vendor comparison | Sample manifest favors a vendor/product | High | Stratified manifest and reviewer sign-off | Anti-bias review of sample rationale | Research Lead | Approved sample manifest | Blocks protocol freeze | RES-0035; DEC-0034; DEF-0006 |
| RISK-0016 | Entitlement mismatch causes unfair or illegal testing | Vendor product tiers differ | High | Entitlement record required before test | Compare entitlement fields across vendors | Research Lead | Entitlement evidence | Blocks testing affected vendor | RES-0039; DEC-0039; DEF-0007 |
| RISK-0017 | Product-tier mismatch creates unfair comparison | SIP vs direct vs broker filtered product mixed silently | High | Product-class controls | Product identity audit | Research Lead | Product/feed manifest | Blocks comparison completeness | RES-0037; DEC-0037; DEF-0008 |
| RISK-0018 | Direct-feed versus SIP distinction distorts NBBO conclusions | Feed source not recorded | High | Source classification required | Cross-vendor feed-type audit | Research Lead | Feed-source evidence | Blocks NBBO comparison | RES-0037; DEF-0008 |
| RISK-0019 | Normalization hides vendor defects | Adapter derives or coerces fields silently | High | Raw-preserving adapter boundary | Transformation-log review | Research Lead | Adapter audit log | Blocks empirical PASS | RES-0037; DEC-0036; ASS-0013 |
| RISK-0020 | Timestamp precision loss or clock-domain mismatch corrupts temporal tests | Precision/timezone/clock domain unclear | High | Timestamp-state inventory | Negative-lag and truncation reports | Research Lead | Timestamp audit report | Blocks temporal criteria | RES-0036; DEF-0001 |
| RISK-0021 | Vendor filtering not disclosed | Broker/institutional feed omits records | High | Product/filter disclosure required | Completeness and condition-code anomalies | Research Lead | Filter disclosure or empirical anomaly report | Blocks completeness PASS | RES-0036; DEF-0001 |
| RISK-0022 | Corporate-action contamination affects raw L1 interpretation | Adjusted bars/data mixed with raw data | Medium-High | Raw/adjusted classification | CA4 audit | Research Lead | Raw/adjusted evidence | Blocks raw-data safety | RES-0036; DEC-0040; DEF-0004 |
| RISK-0023 | Insufficient historical overlap prevents comparable tests | Vendor lacks dates/instruments | Medium-High | Same manifest, unavailable state recorded | Coverage comparison report | Research Lead | Historical overlap report | Blocks affected comparison stratum | RES-0035; ASS-0012; DEF-0006 |
| RISK-0024 | Download cannot be reproduced later | Vendor revises historical data or access expires | High | Snapshot/hash and rerun manifest | Rerun delta report | Research Lead | Reproducibility package | Blocks evidence review | RES-0038; DEC-0038; DEF-0005 |
| RISK-0025 | License prevents evidence retention | Retention/publication terms restrictive | High | License review before extraction | Artifact-retention audit | Research Lead | License/retention approval | Blocks testing or evidence freeze | RES-0039; ASS-0011; DEF-0007 |
| RISK-0026 | Protocol overfits to Databento-style multiple timestamps | Protocol assumes unavailable timestamps | Medium | Timestamp classes allow absent/vendor-derived/project-derived states | Timestamp-state distribution review | Research Lead | Timestamp applicability audit | Blocks temporal comparability claims | RES-0036; DEF-0001 |
| RISK-0027 | Documentation support is treated as empirical PASS | Reviewer summarizes support as result | High | Result-state taxonomy | Final verification checks PASS provenance | Research Lead | Per-criterion evidence audit | Blocks protocol/vendor freeze | RES-0040; DEC-0035 |
| RISK-0028 | Unavailable candidate trials create asymmetric evidence | Some vendors cannot be tested | Medium-High | BLOCKED BY DATA ACCESS state | Candidate access matrix | Research Lead | Access-denial/availability evidence | Blocks Decision Freeze for incomplete comparison unless governance accepts | RES-0039; DEF-0007 |
| RISK-0029 | Numeric thresholds are invented outside 000C | Test author inserts arbitrary tolerances | High | Calibration boundary labels | Threshold audit | Research Lead | 000C calibration reference or removal | Blocks protocol freeze | RES-0036; RES-0040; DEF-0002 |

---

## 27. Deferred / Unresolved Item Traceability

| Deferred ID | Item | Owner | Stage | Reason | Blocking status | Linked identifiers |
|---|---|---|---|---|---|---|
| DEF-0001 | Direct vendor-data access and empirical execution | Research Lead | Before vendor Decision Freeze | Protocol does not run tests | Blocks empirical PASS/FAIL | RES-0036; RISK-0020; RISK-0021 |
| DEF-0002 | Calibration and statistical-power decisions | 000C Owner / Project Owner | Before C3 and tolerance-based conclusions | Numeric thresholds belong to 000C | Blocks C3 and tolerance conclusions | RES-0035; RES-0036; RISK-0029 |
| DEF-0003 | Non-Category-1 criteria routing | Research Lead | Before protocol freeze | Corporate/reference-data criteria need explicit scope confirmation | Blocks APPROVED AND FROZEN if ambiguous | DEC-0040 |
| DEF-0004 | Code dictionary and raw/adjusted policy confirmation | Research Lead | Before A4/A5/CA4 testing | Requires vendor dictionaries/contracts | Blocks affected criteria | RES-0036; RISK-0022 |
| DEF-0005 | Evidence storage and retention approval | Research Lead / Project Owner | Before data extraction | License may restrict retention | Blocks testing and evidence preservation | RES-0038; RES-0039; ASS-0011 |
| DEF-0006 | Final sample manifest and 000C statistical design | 000C Owner | Before empirical execution | Protocol defines structure, not final sample sizes | Blocks test execution | RES-0035; ASS-0012; RISK-0015 |
| DEF-0007 | Vendor entitlement/license confirmation | Research Lead | Before testing each vendor | Testing rights must be confirmed | Blocks vendor data access | RES-0039; DEC-0039; RISK-0016; RISK-0028 |
| DEF-0008 | Product/feed equivalence classification | Research Lead | Before cross-vendor comparison | Product-tier mismatch must be visible | Blocks comparison completeness | RES-0037; DEC-0037; RISK-0017; RISK-0018 |

---

## 28. Evidence and Dependency Traceability Matrix

| Input / Identifier | Depends on | Produces / Controls | Downstream blocker |
|---|---|---|---|
| RES-0035 | B1/B2/B3 by citation; v1.4 candidate universe | Standardized sample design | DEF-0006 |
| RES-0036 | B3 by citation | Applicability matrix and test specs | DEF-0001, DEF-0002 |
| RES-0037 | v1.4 product/feed distinctions | Adapter and comparability controls | DEF-0008 |
| RES-0038 | Evidence preservation requirement | Artifact list and rerun rules | DEF-0005 |
| RES-0039 | License/entitlement constraints | Safety controls | DEF-0007 |
| RES-0040 | Applicability/result taxonomy | Result-state logic | Protocol freeze |
| DEC-0034 | RES-0035 | Test package structure | Vendor testing |
| DEC-0035 | RES-0040 | Result states | Prevents documentation-as-PASS |
| DEC-0036 | RES-0037 | Raw-preserving adapter | Prevents hidden normalization defects |
| DEC-0037 | RES-0037 | Comparability standard | Cross-vendor comparison |
| DEC-0038 | RES-0038 | Evidence bundle | Decision Freeze evidence review |
| DEC-0039 | RES-0039 | Licensing precondition | Vendor data access |
| DEC-0040 | RES-0036 | 30-criterion applicability standard | Protocol freeze |
| ASS-0011 | License review | Evidence retention | DEF-0005 |
| ASS-0012 | 000C/sample manifest | Cross-vendor comparability | DEF-0006 |
| ASS-0013 | Schema dry run | Adapter validity | DEF-0008 |
| RISK-0015-RISK-0029 | Sections 9-21 | Preventive/detective controls | Protocol freeze or vendor testing as stated |

---

## 29. Anti-Confirmation-Bias Review

Strongest opposing evidence: a fully vendor-neutral protocol may still favor vendors with richer public schemas, longer histories, or Databento-like timestamp models.

Best alternative explanation: apparent vendor failure may reflect entitlement tier, product route, or license limits rather than underlying provider capability.

Reasons this protocol may be wrong:

- It may require evidence that some legitimate products do not expose.
- It may under-specify statistical sampling until 000C.
- It may still require revision after the first dry run.

Disconfirming search performed: no vendor data was accessed. The review is conceptual and based on the loaded v1.4 document plus cited baselines only.

Bias controls:

- Product-tier mismatch state.
- Documentation is not PASS.
- Raw-preserving adapter.
- Same manifest across vendors.
- Explicit calibration deferral.
- Licensing precondition before testing.

---

## 30. Protocol Exit Criteria

| Criterion | Status |
|---|---|
| Separate protocol document created with correct filename | Met |
| No frozen baseline modified | Met |
| Current v1.4 research document not modified | Met |
| No vendor data downloaded or tested | Met |
| Exactly 30 B3 criteria preserved | Met |
| Aliases/states/excluded items not miscounted | Met |
| Result states defined | Met |
| Applicable criteria have deterministic test specifications | Met for draft; requires independent audit before freeze |
| Deferred items have owner, stage, reason, blocking status, and linked identifiers | Met |
| New identifiers continue sequences | Met |
| No numeric threshold invented outside 000C | Met |
| Protocol ready to freeze | Not met - audit, legal/license review, and 000C dependencies remain open |

---

## 31. Quality Rubric

| Category | Max | Score | Evidence |
|---|---:|---:|---|
| Scope discipline | 10 | 10 | No testing, ranking, recommendation, selection, rejection, implementation, or Decision Freeze |
| B3 inventory fidelity | 10 | 10 | Exactly 30 criteria preserved with aliases/exclusions stated |
| Test operationalization | 10 | 9 | All applicable criteria have executable-in-principle specs; future dry run may reveal gaps |
| Sampling design honesty | 10 | 9 | Mechanics defined; statistical design correctly deferred to 000C |
| Timestamp rigor | 10 | 9 | Clock classes and anomaly tests defined; product-specific timestamp schemas remain future work |
| Normalization boundary | 10 | 10 | Raw-preserving adapter controls defined |
| Evidence preservation | 10 | 9 | Artifact list complete; license retention may constrain implementation |
| Licensing safety | 10 | 10 | Testing prohibited until rights confirmed |
| Governance/identifier discipline | 10 | 10 | Identifier ceilings checked and continued |
| Freeze readiness | 10 | 7 | Draft is strong but not independently audited or legally reviewed |

**Total: 93/100.** Full marks are not assigned because protocol freeze still requires independent audit, legal/entitlement review, and 000C calibration/statistical-design dependencies.

---

## 32. Freeze Governance

This protocol may be marked **APPROVED AND FROZEN - EMPIRICAL VALIDATION PROTOCOL** only after:

- Independent audit passes.
- Exit criteria pass.
- 000C calibration dependencies needed for C3/tolerances are resolved or explicitly scoped.
- Legal/entitlement safety controls are accepted by the project owner.
- No blocking protocol-design gaps remain.

Future vendor Decision Freeze still requires:

- Protocol approved and frozen.
- Access rights confirmed.
- Direct testing completed where required.
- B3 empirical results recorded.
- Comparison completeness.
- Licensing/pricing re-verified at decision time.
- Open conflicts resolved or explicitly non-blocking.
- Anti-Confirmation-Bias review.
- No blocking B3 violations.
- Required calibration decisions completed.
- DEC-0033 satisfied.

---

## 33. Final Status

**DRAFT / PROTOCOL UNDER REVIEW.**

No vendor was ranked, selected, rejected, or recommended. No direct testing was performed. No vendor data was downloaded. No implementation architecture was created. No Decision Freeze was attempted.

This document designs the future empirical validation protocol only.

---

*End of MILESTONE-000B.4 Phase 2, Category 1 Empirical Validation Protocol, Version 1.0.*
