# M082 - Owner Correction Mission, Findings 16-18

**THIS IS THE AUTHORITATIVE LATEST CORRECTION.** Every other file in this
package, including `owner-correction-mission-findings-12-15.md`, describes an
earlier candidate. Where they conflict with this one, this one wins.

Everything here was **executed**. Nothing is argued.

---

## FINDING 16 - the blank invariant had been WEAKENED, not restored

The findings-12 correction made the database and the domain agree by narrowing
**Python** to a seven-character set. That is agreement bought at the cost of the
invariant: `U+2003 EM SPACE` and twenty other blanks would then have been
accepted by **both** sides.

### Corrected: the complete set, frozen and mirrored

Derived by enumerating every `chr(c)` for which `not chr(c).strip()` holds on
Python 3.13 - **29 characters**:

```
U+0009 U+000A U+000B U+000C U+000D U+001C U+001D U+001E U+001F U+0020
U+0085 U+00A0 U+1680 U+2000 U+2001 U+2002 U+2003 U+2004 U+2005 U+2006
U+2007 U+2008 U+2009 U+200A U+2028 U+2029 U+202F U+205F U+3000
```

* The domain uses **bare `str.strip()`** again - that IS the restored invariant.
  `BLANK_CHARACTERS` exists so the migration can mirror it and a test can prove
  agreement; it is not a second, competing definition.
* The migration carries a **frozen literal**. A migration is history and must
  not import mutable application code, so the 29 codepoints are written out.
* The literal is a **raw** string: those escapes are for PostgreSQL's `E''`
  parser, not Python's. A non-raw literal would have Python decode them first
  and hand PostgreSQL actual control characters instead of escape text.

Verified against PostgreSQL 16.13 before the migration was touched:

```
chars in SQL set: 29
btrim('valve') = 'valve'
btrim('  x  ') = 'x'
btrim('v')     = 'v'
```

### Attacks

30 cases (empty + 29 characters) x 4 persisted columns = **120 executed CHECK
attacks**, all refused. The same 30 are refused through
`AttestOperatorEventReceiptCommand` and `OperatorEventReceipt` construction.
Controls prove `v`, `valve` and `" padded "` still pass on both sides.

**Parity is asserted against the INSTALLED constraint definitions** read from
`pg_constraint`, not against a `btrim` expression the test invents - otherwise
the test would prove only that it agrees with itself.

---

## FINDING 17 - provenance wording

Application-clock and application-constant wording appears only under an
explicit **ON THE SANCTIONED `attest()` PATH** qualification. Generic persisted
rows are described as **UNAUTHENTICATED PROVENANCE**, in both renderers and in
the limitations. A test sweeps the active surfaces for an unqualified per-entry
provenance assertion.

---

## FINDING 18 - active evidence surfaces

* This file is the authoritative latest correction and `README.md` points here.
* Older correction files remain, each carrying its superseded notice.
* No self-hash and no future CI run id is written into its own commit - a commit
  cannot contain either. Both are reported in the delivery report and on PR #12.

---

## Probe errors of my own, recorded

1. **Chunking split a `\uXXXX` escape.** My first wrapping of the 29-character
   literal cut mid-escape and produced a `SyntaxError` in both the domain module
   and the migration. Rewritten to split on escape-token boundaries.
2. **A non-raw literal in the CHECK constraints.** Python would have decoded the
   escapes before PostgreSQL saw them, so the constraint would have contained
   real control characters rather than escape text.
3. **A parametrisation that silently did not expand.** After the first edit the
   suite still collected 32 blank cases instead of 120: the formatter had
   reflowed the block before my replacement, so the anchor never matched and the
   old 8-character list survived. Caught by checking the collected count against
   what 30 x 4 should be, not by the suite passing - **it passed either way**.
