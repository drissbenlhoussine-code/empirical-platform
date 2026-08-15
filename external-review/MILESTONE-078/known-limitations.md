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
7. **A plan id colliding across instruments is named, not repaired.** One entry
   is audited and the collision is stated.
8. **`CITES_PLAN_OUTSIDE_THIS_SESSION` is relative to this session.** Proving a
   plan id exists nowhere would require reading every session.
9. **No money, by construction.** No price, notional, valuation, P&L or
   profitability figure exists anywhere in the output. This is a limitation as
   much as a guarantee: M078 cannot tell you whether anything was worthwhile.
10. **A database-level failure propagates** rather than being reported as
    `LEDGER_UNAVAILABLE`. Bad *data* is withheld honestly; a broken *database*
    is not disguised as a soft verdict.
11. **Pre-existing, untouched:** the M062/M064/M065 CRLF seal debt. M078
    introduces no fixture and no byte seal.
