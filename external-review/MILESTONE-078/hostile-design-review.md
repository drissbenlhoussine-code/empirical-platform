# M078 — Hostile Design Review (pre-implementation)

My own attack on my own design. **Not an independent review.** Every **FIXED**
item was corrected in the design document before a line of code was written.
Failed first designs are recorded rather than deleted.

**79 attacks. 22 genuine defects found and fixed; 4 accepted with stated
reasons.**

## A. Authority assumptions

| # | Attack | Verdict |
|---|---|---|
| A01 | Treats a citation as proof the operator traded | PASS — vocabulary is `ASSERTED_POSITION_*`; §8 marks the ledger non-authoritative for broker reality |
| A02 | **Treats absence of a citation as proof the operator did nothing** | **FIXED — the sharpest honesty hole.** The first draft called this `NOT_ACTED_UPON`, which asserts conduct. Renamed `NO_ASSERTED_POSITION_RECORDED`, and §8 marks absence non-authoritative for anything about real conduct |
| A03 | Uses "adherence"/"compliance"/"followed" language that judges the operator | **FIXED** — that vocabulary is banned outright in §6 and enforced by test |
| A04 | Assumes the session's plan set is complete | PASS — it is the session's own persisted record, authoritative for what was recommended |
| A05 | Assumes a cited plan id refers to a real plan | PASS — membership test against this session's plan ids only; an unknown id simply does not match |
| A06 | Assumes the ledger is the operator's whole activity | **FIXED** — stated as a limitation: the ledger is what was written down, not what happened |
| A07 | Silently promotes `candidate` to `recommendation` | PASS — only plans the session recorded as approved enter the audit |
| A08 | Infers intent from a citation | PASS — no intent is modelled anywhere |

## B. Hidden broker/market assumptions

| # | Attack | Verdict |
|---|---|---|
| B01 | Any output implies broker confirmation | PASS — no broker concept exists in the module |
| B02 | Any output implies a fill | PASS — no fill concept |
| B03 | Any output implies a current market price | PASS — **no price is read at all** |
| B04 | Any output implies P&L | PASS — **structurally impossible; see §7, no arithmetic over prices** |
| B05 | Any output implies profitability | PASS — same structural guarantee |
| B06 | "Closed" implies a realized result | **FIXED** — `ASSERTED_POSITION_CLOSED` is defined in §6 as a lifecycle fact only, explicitly not "realized" |
| B07 | Counting closed positions becomes a track record | ACCEPTED — counts of records are not performance; no money and no outcome is attached to any of them |

## C. Temporal

| # | Attack | Verdict |
|---|---|---|
| C01 | `as_of` defaults to now, making results irreproducible | **FIXED** — `as_of` is required with no default |
| C02 | `as_of` defaults to the session's own `as_of`, which always shows nothing | **FIXED** — rejected for exactly that reason; a default would silently pick the one window guaranteed to be empty |
| C03 | Future events inflate follow-through | PASS — M076's `event_timestamp <= as_of` filter, reused unchanged |
| C04 | Excluded future events are hidden | PASS — count surfaced |
| C05 | Exact-boundary event dropped by an off-by-one | PASS — inclusive `<=`; named boundary test |
| C06 | Two offsets for one instant disagree | PASS — aware datetimes compared as instants |
| C07 | Naive `as_of` silently assumed UTC | PASS — M076 rejects it at the boundary |
| C08 | `recorded_at` leaks into the answer | PASS — the fold reads `event_timestamp` only |
| C09 | **`as_of` before the session's own `as_of` reads as "operator recorded nothing"** | **FIXED** — that window ends before the session existed; the result now carries an explicit limitation instead of an implied accusation |
| C10 | A position opened before the session but citing its plan | ACCEPTED — impossible to cite a plan that did not yet exist except by operator error; it still matches by id and is reported, which is the honest handling |

## D. Determinism and identity

| # | Attack | Verdict |
|---|---|---|
| D01 | Entry order depends on input order | PASS — `(rank, symbol)` total order, ranked before unranked |
| D02 | Unlinked-position order depends on set iteration | **FIXED** — first draft built them from a set; now ordered `(symbol, position id)` |
| D03 | Duplicate plan ids in one session | PASS — deduplicated by id; a plan is one entry |
| D04 | The same plan cited by two positions | **FIXED** — first draft overwrote status; now counts are retained per plan |
| D05 | **A plan cited by both an open and a closed position** | **FIXED** — precedence defined: `ASSERTED_POSITION_OPEN` wins as the currently-true fact, and both counts are retained so the closed one is not lost |
| D06 | Blank or whitespace citation treated as an identifier | **FIXED** — carried forward from M077's R04 defect; blank is not an id |
| D07 | Two runs over identical inputs differ | PASS — pure function, no clock, no randomness |
| D08 | Repeated invocation mutates state | PASS — read-only, no writes exist on the dependency |

## E. Missing, empty and contradictory data

| # | Attack | Verdict |
|---|---|---|
| E01 | Empty ledger reported as an error | PASS — every plan `NO_ASSERTED_POSITION_RECORDED`, stated |
| E02 | Unreadable ledger reported as "nothing recorded" | **FIXED** — distinct `LEDGER_UNAVAILABLE`; absence must never render as a pass |
| E03 | Incoherent persisted events crash the audit | **FIXED** — caught and reported as `LEDGER_INCOHERENT` |
| E04 | Session with no approved plans is an error | PASS — `NO_APPROVED_POSITION_PLANS`, and unlinked positions are still reported |
| E05 | Session not found is swallowed | PASS — the repository error propagates; not disguised |
| E06 | A database failure becomes a soft verdict | PASS — propagates, per the M077 A1 precedent |
| E07 | Mixed valid/invalid citations | PASS — each judged independently |
| E08 | A plan with no `position_plan_governance_id` | PASS — not an approved plan; excluded from the audit set |

## F. Frozen-contract preservation

| # | Attack | Verdict |
|---|---|---|
| F01 | Modifies M076 to expose lineage | PASS — projected from the same event tuple, exactly M077's pattern |
| F02 | Re-implements M076's fold | PASS — `derive_position_state()` remains the sole authority on open vs closed |
| F03 | Changes M077 semantics | PASS — M077 is neither imported nor altered |
| F04 | Adds a section to the M072 brief | **FIXED** — first draft did. Rejected: the brief is about today and follow-through is about the past. A dedicated query and CLI instead, which also removes all frozen-contract risk from M072 |
| F05 | Needs a migration | PASS — zero new table, zero migration |
| F06 | Repairs M062/M064/M065 seal debt | N/A — no fixture, no byte seal |
| F07 | Reuses M067/M068 historical evidence operationally | N/A — neither is read |

## G. Vocabulary and misreading

| # | Attack | Verdict |
|---|---|---|
| G01 | A reader sees "closed" and infers a profit or loss | PASS — no money exists in the output to attach one to |
| G02 | A reader sees a "0 of 5 recorded" summary and reads operator failure | **FIXED** — the summary line now states that nothing recorded means nothing written down, not that nothing was done |
| G03 | `CITES_NO_PLAN` reads as an accusation of unauthorized trading | **FIXED** — §6 defines it as a citation fact; the renderer avoids "unauthorized"/"discretionary"/"off-plan" |
| G04 | Status names imply execution | PASS — forbidden-vocabulary test over `EXECUTED`, `FILLED`, `VERIFIED`, `REALIZED`, `PROFIT`, `PNL` |
| G05 | The word "audit" implies a compliance finding | ACCEPTED — bounded by the banner, which states it reports records rather than judging conduct |
| G06 | JSON field names overclaim where text does not | PASS — one derived object renders both; parity test |
| G07 | A disclaimer is used to rescue misleading semantics | PASS — the semantics carry no money and no conduct judgement; the banner restates rather than rescues |

## H. Concurrency and reads

| # | Attack | Verdict |
|---|---|---|
| H01 | A concurrent M076 write tears the snapshot | PASS — `list_all()` is a single `SELECT`; `READ COMMITTED` gives one consistent statement snapshot, proven by M077's own race test and re-proven here |
| H02 | The audit needs its own lock | ACCEPTED — the requirement is a point-in-time snapshot, which one statement already provides |
| H03 | The audit writes | PASS — no write path on its dependencies |
| H04 | Session and ledger are read at different instants, so they disagree | **FIXED** — the session is immutable once persisted and the ledger is read once; stated explicitly so the reader knows the pairing is coherent |
| H05 | Partial persistence leaves a half-audit | N/A — nothing is persisted |

## I. Numeric

| # | Attack | Verdict |
|---|---|---|
| I01 | Decimal precision loss | N/A — **no Decimal is read**; §7 |
| I02 | Silent rounding | N/A — no arithmetic over money |
| I03 | Quantity overflow or coercion | PASS — quantities are the ints M076 already validated as positive |
| I04 | Counts drift from entries | PASS — counts derived from the entries themselves, never tallied separately |

## J. Look-ahead and causality

| # | Attack | Verdict |
|---|---|---|
| J01 | Future data leaks into a past answer | PASS — `event_timestamp <= as_of` |
| J02 | The result implies the recommendation caused the position | **FIXED** — the citation is what the operator recorded, not a causal link; stated in §6 and in the banner |
| J03 | Historical evidence becomes predictive | N/A — no historical study is read |
| J04 | Survivorship bias in which plans appear | PASS — every approved plan of the session appears, including those with nothing recorded |
| J05 | Selection bias from reporting only open positions | **FIXED** — closed positions are reported too, so the audit is not silently biased toward what is still held |

## K. Interface, architecture and test quality

| # | Attack | Verdict |
|---|---|---|
| K01 | `entrypoints` imports `decision_candidate`, breaking the layer rule | PASS — construction and rendering live in `usecases`, the M076 CLI lesson applied |
| K02 | `usecases` imports `shared.persistence` | PASS — repositories are consumed through their Protocols |
| K03 | The CLI mutates state | PASS — read-only; no append path is reachable |
| K04 | Running the CLI twice gives different answers | PASS — pure over a fixed `as_of`; idempotent by construction |
| K05 | JSON key set changes between runs | PASS — one derived object, fixed keys |
| K06 | A suppressed/absent result is indistinguishable from an assessed one | PASS — the unassessable path carries an explicit reason, never an empty success |
| K07 | **A position citing a plan from another session is lumped in with "cites no plan"** | **FIXED** — these are different facts and were merged in the first draft; now `CITES_NO_PLAN` and `CITES_PLAN_OUTSIDE_THIS_SESSION` are distinct |
| K08 | Tests mirror the implementation rather than attacking claims | PASS — §14 derives the suite from the claims; the no-money guarantee and the vocabulary ban are tested directly |
| K09 | A test asserts a status without asserting the honesty caveat | **FIXED** — a named test asserts that the "nothing recorded" caveat is present in both renderings |
| K10 | Coverage of the "both open and closed cite one plan" case is missing | **FIXED** — added to §14 as a named case after D05 |


## Unresolved

**None.** No correctness or honesty FAIL remains. The five ACCEPTED items
(B07, C10, G05, H02) are bounded, stated and carry reasons.
