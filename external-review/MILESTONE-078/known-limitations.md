# M078 — Known Limitations

1. **Absence of a record is not evidence of inaction.**
   `NO_ASSERTED_POSITION_RECORDED` means nothing was written down citing that
   plan. It does **not** mean the operator ignored it, rejected it or failed to
   act. The ledger records assertions, not conduct.
2. **Presence of a record is not evidence a trade occurred.** Every matched
   position is an operator assertion. There is no broker, no confirmation and
   no reconciliation.
3. **A citation is not a causal link.** That an operator cited a plan is what
   they recorded; it is not proof the plan caused the position.
4. **The audit sees only the ledger.** Activity the operator never wrote down
   is invisible, and the report cannot distinguish "did not act" from "did not
   record".
5. **`as_of` is required and the answer depends entirely on it.** There is no
   default, deliberately: the obvious default — the session's own `as_of` — is
   the one window guaranteed to show nothing.
6. **An instrument mismatch is reported, not resolved.** A position citing a
   plan for a different instrument is flagged; M078 does not decide whether the
   citation or the symbol is wrong.
7. **The plan governance id must be usable as an identity, or nothing is
   audited.** It is the join authority between the session and the ledger, so
   it is validated *before* any lineage is read:
   - a **blank or whitespace-only** plan governance id withholds the audit;
   - **one plan governance id mapped to conflicting instrument identity**
     withholds the audit;
   - in both cases `outcome = NOT_ASSESSABLE` and
     `reason = SESSION_PLAN_REFERENCES_INCOHERENT`;
   - **no arbitrary winner is audited.** When `PLAN-X` names both `AAPL` and
     `TSLA`, a citation of `PLAN-X` refers to neither in particular, and
     choosing one by sort order would invent an answer the session data does
     not contain;
   - a **`rank` divergence is presentation metadata, not identity ambiguity** —
     with the same id and the same instrument the join is unambiguous, so the
     audit proceeds and the divergence is reported;
   - **exact identical duplicates** (same id, instrument and rank) are
     deterministically deduplicated and the count is reported.

   *This supersedes the earlier behaviour, which named the collision and
   audited one entry. That was deterministic but not semantically safe; see
   `owner-correction-pass.md`.*
8. **`CITES_PLAN_OUTSIDE_THIS_SESSION` is relative to this session.** Proving a
   plan id exists nowhere would require reading every session.
9. **No money, by construction.** No price, notional, valuation, P&L or
   profitability figure exists anywhere in the output. This is a limitation as
   much as a guarantee: M078 cannot tell you whether anything was worthwhile.
10. **A database-level failure propagates** rather than being reported as
    `LEDGER_UNAVAILABLE`. Bad *data* is withheld honestly; a broken *database*
    is not disguised as a soft verdict.
11. **M078 is an EFFECTIVE-TIME audit, not a point-in-time one — and this is
    the limitation most likely to be misused.**

    M076 defines two distinct timestamps: `event_timestamp` is when the
    operator says the event happened, and `recorded_at` is when the assertion
    was written down. **Only `event_timestamp` drives the fold**; `recorded_at`
    never does. M078 inherits that semantics unchanged.

    The consequence: **an assertion backfilled later can change the answer for
    an earlier `as_of`.** Auditing the same session at the same `as_of` today
    and again next month can legitimately produce different results, because
    the operator may have written down, in the meantime, an event they date to
    the original window.

    Therefore **M078 does NOT prove what information or evidence was available
    to the system at historical time `t`.** It reports what the ledger *now*
    says about `t`.

    **It must NOT be used as point-in-time calibration or forward-evaluation
    evidence without a `recorded_at` / evidence-availability firewall** — that
    is, without additionally constraining which assertions had been *recorded*
    by the moment being evaluated. Using an effective-time audit as if it were
    point-in-time is a look-ahead leak: it would credit the system with
    knowledge it did not have.

    This documents existing frozen M076 semantics. Neither M076 nor M078 code
    was changed to address it in this pass, and doing so would be a separate,
    explicitly authorized milestone.

12. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt. M078
    introduces no fixture and no byte seal.
