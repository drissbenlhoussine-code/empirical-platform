# M079 — Hostile Design Review (pre-implementation)

My own attack on my own design. **Not an independent review.** Every **FIXED**
item was corrected in the design document before a line of code was written.

**81 attacks. 25 genuine defects found and fixed; 7 accepted with stated
reasons.** Two of the fixes are load-bearing: T07 (incompleteness masking real
corruption) and C05 (a single exclusion count hiding *why* evidence is
missing).

## A. Effective time versus knowledge time — the central distinction

| # | Attack | Verdict |
|---|---|---|
| A01 | `recorded_at` used as effective time | PASS — eligibility is explicit: `event_timestamp <= E` **and** `recorded_at <= K`; neither field crosses into the other's role |
| A02 | `event_timestamp` used as knowledge time | PASS — same |
| A03 | One cutoff silently serves both | **FIXED** — the first draft had a single `as_of`. Two required parameters, no default on either |
| A04 | `knowledge_as_of` defaults to now, making the answer irreproducible | **FIXED** — required, no default |
| A05 | `knowledge_as_of` defaults to `effective_as_of`, silently choosing an epistemic stance | **FIXED** — rejected for that reason and stated in §6 |
| A06 | M076's frozen `as_of` is reinterpreted to mean knowledge time | PASS — `effective_as_of` is passed into M076 unchanged, which is exactly what its `as_of` already means |
| A07 | M079 re-implements the fold to add knowledge filtering | **FIXED** — separation of duties: M079 applies **only** the knowledge filter and delegates the effective filter and the fold to M076 |
| A08 | `K < E` is nonsense and should be rejected | **ACCEPTED as meaningful** — "what did we know on Aug 11 about what happened by Aug 20?" is a real question; permitted with a limitation naming the stance |
| A09 | `K > E` leaks the future | PASS — `K` bounds *recording*, `E` bounds *occurrence*; a later recording of an earlier event is exactly what the firewall is for |
| A10 | Setting `K` to now is a hidden effective-time query | ACCEPTED — it legitimately reproduces M076's answer, and §6 says so explicitly rather than hiding it |

## B. Back-dating and the incomplete prefix

| # | Attack | Verdict |
|---|---|---|
| B01 | Backfilled `OPENED` visible too early | PASS — excluded until `K` reaches its `recorded_at` |
| B02 | Backfilled `OPENED` never becomes visible | PASS — visible once `K` advances; a named scenario |
| B03 | `CLOSED` visible without its `OPENED` | **FIXED** — the sharpest case. The fold raises `POSITION_NOT_OPEN`; reporting that as corrupt data would be a false diagnosis. Classified per key as `INCOMPLETE_KNOWLEDGE_SEQUENCE` |
| B04 | `REDUCED` visible without its `OPENED` | **FIXED** — same classification, same reasoning |
| B05 | The missing opening is inferred so the fold can proceed | PASS — **nothing is invented**: no quantity assumed, no state guessed |
| B06 | One incomplete key withholds the entire snapshot | **FIXED** — classification is **per key**; a global withholding would destroy the capability for the common case |
| B07 | Per-key isolation requires copying M076's fold | **FIXED** — M079 folds **one key at a time** through M076's own function and catches per key. Nothing is copied |
| B08 | A key complete at `K` is later contradicted by a backfilled reduction | **ACCEPTED and named** — a `KNOWN_OPEN` quantity may later prove reduced. That is not an error, it is what was known; §6 and the banner say `KNOWN_` means *known to the ledger by K*, not *true* |
| B09 | Out-of-order insertion changes the answer | PASS — eligibility is a pure predicate over two fields; insertion order is irrelevant |
| B10 | An event recorded before it happened (`recorded_at < event_timestamp`) | ACCEPTED — M076 permits it and it is meaningful (recording an intention, or a clock difference); M079 does not editorialise |

## C. Boundaries, counts and determinism

| # | Attack | Verdict |
|---|---|---|
| C01 | Effective boundary exclusive by an off-by-one | PASS — inclusive `<=`, matching M076 so the two cannot disagree |
| C02 | Knowledge boundary exclusive | PASS — inclusive `<=`, symmetric with C01 |
| C03 | The two boundaries use different inclusivity | **FIXED** — an early draft had `<` on knowledge; made symmetric and stated |
| C04 | Exact-instant event at either cutoff | PASS — included on both; named tests |
| C05 | **A single "excluded" count hides *why* evidence is missing** | **FIXED** — M076's own count only sees exclusions among knowledge-survivors. M079 reports **two** counts: excluded by effective cutoff and excluded by knowledge cutoff. Without this an operator cannot tell "hadn't happened yet" from "hadn't been recorded yet" |
| C06 | Same instant, different UTC offsets, disagree | PASS — aware datetimes compared as instants |
| C07 | Naive `effective_as_of` | **FIXED** — rejected at the query boundary as a request error, not a data claim |
| C08 | Naive `knowledge_as_of` | **FIXED** — same; it would never reach M076, so M079 must reject it itself |
| C09 | Key order depends on dict iteration | PASS — `(instrument_symbol, position_governance_id)` total order |
| C10 | Ordering ties | PASS — `position_governance_id` is unique per key |
| C11 | Two runs over identical inputs differ | PASS — pure function, no clock, no randomness |
| C12 | Counts drift from the reported sets | PASS — derived from the sets themselves |

## D. Distinguishing incompleteness from corruption

| # | Attack | Verdict |
|---|---|---|
| T07 | **`INCOMPLETE_KNOWLEDGE_SEQUENCE` masks genuinely corrupt data** | **FIXED — the most important finding of this review.** The fold raises the *same* exception type for a knowledge-truncated prefix and for real corruption (say two `OPENED` events on one key). Labelling every per-key failure "incomplete knowledge" would hide corruption behind an innocent-sounding status. **Discriminator:** re-fold the key against the *unfiltered* event set. Fails at `K` but succeeds unfiltered → the failure is *caused by* knowledge filtering → `INCOMPLETE_KNOWLEDGE_SEQUENCE`. Fails both ways → the underlying data is genuinely incoherent → reported as such |
| D02 | The discriminator itself leaks future knowledge into the answer | PASS — it decides only *how to label a refusal*; no state from the unfiltered fold is ever reported |
| D03 | The discriminator doubles the work | ACCEPTED — it runs only on the failure path, which is rare |
| D04 | A key corrupt only *after* `K` is called corrupt at `K` | PASS — the unfiltered fold covers all events, so a key coherent at `K` is reported from its `K`-view regardless of later corruption |

## E. Frozen-contract preservation

| # | Attack | Verdict |
|---|---|---|
| E01 | M076's fold is modified | PASS — read-only, delegated |
| E02 | M076's `as_of` semantics change | PASS — `effective_as_of` *is* `as_of` |
| E03 | M077 or M078 semantics change | PASS — neither imported nor altered |
| E04 | A new table or migration is added | PASS — `recorded_at` is already `TIMESTAMPTZ NOT NULL`; §10 justifies adding nothing |
| E05 | An index on `recorded_at` is needed | **ACCEPTED as not needed** — M079 reads through the existing `list_all()` and filters in memory, exactly as M077/M078 do, so no new query shape reaches PostgreSQL |
| E06 | M062/M064/M065 seal debt touched | N/A — no fixture, no byte seal |
| E07 | The M072 brief is modified | PASS — M079 is a separate query and CLI; the brief is about today |

## F. Vocabulary and misreading

| # | Attack | Verdict |
|---|---|---|
| F01 | `KNOWN_OPEN` reads as "verified open" | **FIXED** — defined as *known to the ledger by `K`*, not known to be true; stated in the banner and asserted by test |
| F02 | Output reads as broker-confirmed | PASS — no broker concept; banner denies it |
| F03 | Output reads as execution or a fill | PASS — forbidden-vocabulary test over `VERIFIED`, `EXECUTED`, `FILLED`, `REALIZED`, `CONFIRMED` |
| F04 | Asserted notional reads as a valuation | PASS — carried through under M076's own semantics, explicitly never revalued |
| F05 | Any P&L is implied | PASS — no exit-price arithmetic exists anywhere |
| F06 | `INCOMPLETE_KNOWLEDGE_SEQUENCE` reads as an accusation of bad record-keeping | **FIXED** — worded as a property of the *snapshot*, not of the operator |
| F07 | "Snapshot" implies a verified state of the world | ACCEPTED — bounded by the banner, which says it is a snapshot of *evidence*, not of holdings |
| F08 | A reader mistakes M079's answer for M076's | **FIXED** — both cutoffs are echoed in every rendering, and §6 contrasts the two products explicitly |

## G. Absence, error and malformed state

| # | Attack | Verdict |
|---|---|---|
| G01 | Nothing recorded by `K` reported as "nothing happened" | **FIXED** — `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF`, explicitly distinct |
| G02 | Unreadable ledger reported as empty | PASS — `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE` |
| G03 | A database failure becomes a soft verdict | PASS — propagates; M077/M078 precedent |
| G04 | Empty ledger is an error | PASS — a real observation, reported |
| G05 | Every key incomplete | PASS — reported per key; the snapshot still renders |
| G06 | Mixed complete and incomplete keys | PASS — each judged independently |

## H. Interface, architecture, security

| # | Attack | Verdict |
|---|---|---|
| H01 | `entrypoints` imports `decision_candidate` | PASS — construction and rendering live in `usecases` |
| H02 | The CLI mutates state | PASS — no write path is reachable |
| H03 | Repeated invocation differs | PASS — pure over a fixed `(E, K)` |
| H04 | Text and JSON diverge | PASS — one derived object renders both |
| H05 | A new credential, network path or file read | PASS — none |
| H06 | Concurrent M076 writes tear the snapshot | PASS — `list_all()` is a single `SELECT`; `READ COMMITTED` gives one consistent statement snapshot |
| H07 | The CLI accepts one cutoff and guesses the other | **FIXED** — both required, usage error otherwise |

## I. Persistence, SQL and scale

| # | Attack | Verdict |
|---|---|---|
| I01 | Filtering in memory loads the whole ledger | ACCEPTED — identical to M077/M078; the ledger is operator-scale, and a new query shape would add an index requirement for no correctness gain |
| I02 | `recorded_at` round-trips inexactly through `TIMESTAMPTZ` | PASS — same column type and driver path M076 already proves for `event_timestamp` |
| I03 | A row with `recorded_at` NULL breaks the predicate | PASS — the column is `NOT NULL` in the frozen M076 schema |
| I04 | The predicate is applied in SQL on one path and in Python on another | PASS — one path only |
| I05 | A partially-committed write is observed | PASS — M076 commits each event atomically under a per-position advisory lock |
| I06 | Reading the ledger twice within one query gives different sets | PASS — read once, filtered twice |

## J. Compatibility with the frozen chain

| # | Attack | Verdict |
|---|---|---|
| J01 | M079 and M076 disagree at `K = now` | PASS — must be identical; a named cross-check test |
| J02 | M079 and M076 disagree on an effective boundary | PASS — both inclusive, and `effective_as_of` is handed to M076 unchanged |
| J03 | M079 contradicts M078's follow-through over one ledger | PASS — M078 is effective-time by design; the two answer different questions and neither is altered |
| J04 | M079's existence weakens M078's documented limitation | **FIXED** — the opposite is stated: M079 is the firewall M078 named as missing, and M078's limitation stands unchanged for M078 itself |
| J05 | M077's capital view silently gains knowledge-time semantics | PASS — M077 is untouched and unaware of M079 |

## K. Test quality

| # | Attack | Verdict |
|---|---|---|
| K01 | Tests mirror the implementation instead of the claims | PASS — §15 derives the suite from the acceptance scenarios |
| K02 | The look-ahead case M078 documented is never actually tested | **FIXED** — a named test asserts that a backfilled assertion is invisible at the earlier knowledge cutoff and visible at the later one, same `E` |
| K03 | Incompleteness and corruption are never tested apart | **FIXED** — both branches of the T07 discriminator are named test cases |
| K04 | The two exclusion counts are never distinguished in a test | **FIXED** — a test asserts each count independently |
| K05 | PostgreSQL evidence uses a timeline where the defect cannot appear | **FIXED** — the adversarial timeline `T1 < T2 < T3` with `OPENED` recorded last is mandated in §15 |
| K06 | Boundary tests use only one side of each cutoff | **FIXED** — exact instant plus one microsecond either side, on both dimensions |


## Unresolved

**None.** No correctness or honesty FAIL remains. The six ACCEPTED items (A08,
A10, B08, B10, D03, E05, F07) are bounded, stated and carry reasons.
