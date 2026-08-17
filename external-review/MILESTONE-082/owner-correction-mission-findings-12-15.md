# M082 - Owner Correction Mission, Findings 12-15

> **⚠ SUPERSEDED by `owner-correction-mission-findings-16-18.md`.** In
> particular its Finding 12 resolution NARROWED the Python blank invariant to
> seven characters; Owner finding 16 restored the complete 29-character set.
> Kept visible as the record of what was believed at the time.

**(Historical) THIS WAS THE AUTHORITATIVE LATEST CORRECTION.** Every other file in this
package describes an earlier candidate. Where they conflict with this one, this
one wins.

Everything here was **executed**. Nothing is argued.

Old head `3960110`. Same branch, same PR (#12).

---

## Repository truth gate

| | |
|---|---|
| base master | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| local head == remote head | `3960110daa4b1c7c461f4af30c0dcba7a76cd0cf` |
| working tree | clean |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-081` |
| PostgreSQL | 16.13 |

---

## FINDING 12 - database and domain disagreed on "blank"

### Reproduced

```
char=space     btrim_passes_check=false   python_says_blank=True
char=tab       btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=newline   btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=cr        btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=formfeed  btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=vtab      btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=nbsp      btrim_passes_check=TRUE    python_says_blank=True   <- mismatch
char=empty     btrim_passes_check=false   python_says_blank=True
```

End to end:

```
tab_only_row_persisted='\t'  check_expression_result=True
report_result=ValueError: attested_by must be non-empty
```

Six of eight characters passed the write boundary and then crashed the read.

### Candidates ranked

| | Candidate | Verdict |
|---|---|---|
| (i) | strengthen PostgreSQL to match Python's native definition | **not achievable** - measured: `[:space:]` and `\s` both EXCLUDE vertical tab and NBSP, and `str.strip()` covers far more of Unicode than any simple SQL expression |
| **(ii)** | **one explicitly enumerated set, used verbatim on both sides** | **SELECTED** - the only option where the two provably agree |
| (iii) | tolerate or silently skip malformed qualifying rows | **refused** - the mission forbids it, and it would hide exactly the class of row that must not exist |

Measured proof that (ii) is the only one that works:

```
char      btrim  posix_space  backslash_s  explicit_set
tab       true   false        false        false
vtab      true   TRUE         TRUE         false
nbsp      true   TRUE         TRUE         false
ok  'x'   true   true         true         true
ok ' x '  true   true         true         true
```

`BLANK_CHARACTERS` is now defined once in the domain and used verbatim in all
four CHECK constraints, with a test asserting they agree character by character
**against the live database**.

**Stated rather than hidden:** an exotic Unicode whitespace character outside
this enumerated set is accepted by BOTH sides. That is agreement, which is the
property that matters - the database is the write boundary and the domain must
never reject what the database stored.

### A worse bug I introduced fixing this one

My first correction wrote the set as `E' \t\n\r\f\v '`. **PostgreSQL's
`E''` syntax has no `\v` escape:**

```
E-escape \v produces: 118   (11 = vertical tab, 118 = letter v)
DANGER btrim('valve', set) = 'alve'
```

The constraint would have stripped the **letter v** out of legitimate
identifiers - strictly worse than the mismatch it replaced. It was caught only
by running the parametrised test over every character on all four columns, and
it is the reason that test enumerates characters instead of asserting a summary.
Corrected to `\x0B`.

---

## FINDING 13 - metadata provenance was overclaimed

### Reproduced

```
direct_sql_receipt_accepted=True
persisted_attested_by=FORGED-BY-DIRECT-SQL
persisted_attester_version=FORGED-VERSION
rendered_per_entry_claim=... attested_by=FORGED-BY-DIRECT-SQL
                         attester_version=FORGED-VERSION (label applied on the
                         sanctioned attest path ...)
json_makes_same_per_entry_assertion=False
```

The text renderer asserted sanctioned-path provenance for a row whose provenance
it cannot authenticate, and JSON never made the assertion - so the claimed
text/JSON parity was incomplete too.

### Corrected to the exact three-way distinction

| Field | On the sanctioned `attest()` path | As a persisted value |
|---|---|---|
| `system_received_at` | application host clock, taken **after** read-back | **unauthenticated provenance** |
| `attester_version` | application constant | **unauthenticated provenance** |
| `attested_by` | **caller-supplied**, passed through unchanged | **unauthenticated provenance** |

**No individual persisted receipt is described as having come through
`attest()`**, because the database does not prove that. Both renderers now carry
`UNAUTHENTICATED PROVENANCE`; neither claims the sanctioned path.

---

## FINDING 14 - crash/reconciliation language reintroduced chronology

### Reproduced, through the sanctioned repository path

```
sanctioned_path_label=1999-01-01T00:00:00+00:00
sanctioned_path_attested_by=CALLER-CONTROLLED

active limitation still says 'permanently unattested': True
active limitation still says 'LATER label':            True
```

The two statements contradicted each other, and the second is false under M082's
own clock model.

### Corrected active semantics

> A crash after event commit but before receipt insertion leaves an **unattested
> gap**. The event remains unattested unless and until a later explicit
> attestation succeeds. That later attestation proves only its own causal
> read-back-before-receipt ordering. Its label is still untrusted and may be
> numerically **earlier** or later; it does not reconstruct the original commit
> time or historical knowledge time.

Legacy-event language corrected in the same terms: the migration performs no
backfill, no historical receipt time is invented, and a legacy event may later be
explicitly attested - creating only **current causal receipt authority**, never
retroactive historical authority.

`permanently unattested`, `only a LATER label` and `later true instant` are gone
as active claims and appear only inside the visible retraction.

---

## FINDING 15 - evidence package reconciliation

See the top-of-file notices added to every superseded file, and the authoritative
final section appended to `validation-results.md`. The current console command is
exactly:

```
empirical-platform-receipt-label-cutoff-view
```

---

## The claim M082 makes, unchanged in substance and narrowed in wording

> A persisted receipt binds a stable receipt identity to an exact M076 event
> governance identity whose real `public` row was observed as originating from a
> prior committed transaction at receipt insertion. It does not attest event
> payload, wall-clock chronology, commit time, historical availability or the
> provenance of persisted metadata labels.
