# M079 — Reality Gate

> **Updated after Owner review.** The first candidate's central safeguard —
> re-folding a failed key against the unfiltered event set to separate
> "incomplete" from "corrupt" — was itself a temporal leak and has been
> **retracted**. The claim this document makes is correspondingly narrower and
> the safeguard is now structural. Superseded passages are marked in place.

## The question the mission demands be answered exactly

**Does M079 prove what the ledger NOW says happened by effective time, or what
evidence was actually AVAILABLE by knowledge time?**

**The second — but stated more carefully than the first candidate stated it.**

M079 reports the operator assertions that **the ledger records as having been
recorded** by a knowledge cutoff, about what they say happened by an effective
cutoff. It does **not** claim to prove what evidence was *actually* available,
because `recorded_at` is an operator-supplied field rather than a
system-assigned immutable receipt time.

The first question — what the ledger now says — is already answered by M076 and
M078, and M079 does not change or replace them. Setting `knowledge_as_of` to
the present reproduces M076's answer exactly, and a named test asserts it.

**These are different products and the milestone exists because conflating them
is a look-ahead leak.**

## What M079 proves

That the ledger **records** a given set of operator assertions as having been
recorded by time `K`, and the position state derivable from exactly those, at
effective time `E`.

Every field of the output is a function of that surviving evidence and the two
cutoffs. Two ledgers that agree on every row with `recorded_at <= K` produce
byte-identical snapshots, however much they differ afterwards — proven in the
unit suite by object equality and per field, and over **two real PostgreSQL
databases** in the integration suite.

## What M079 does not prove

| Not proven | Why |
|---|---|
| broker execution | no broker concept exists anywhere in the module |
| actual fills | nothing in the ledger is a fill |
| actual holdings | `KNOWN_OPEN` means known **to the ledger**, not known to be true |
| market truth | no market price is read |
| valuation | asserted prices are M076's own, never revalued |
| profitability or P&L | no exit-price arithmetic exists; no field names a return, gain, loss or proceeds |
| causation | no causal claim is made |
| investment advice | none given |
| that the operator's assertions are true | M079 reports what was **on record**, not what happened |

## Could a reasonable user misread the output?

| Misreading | Prevented by |
|---|---|
| "this position was verified open at `K`" | the status is `KNOWN_OPEN`, the banner says **KNOWN means known TO THE LEDGER, NOT known to be true**, and a limitation repeats it on every snapshot |
| "the operator held nothing on Aug 11" | `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF` is explicitly distinct from "nothing happened", and a limitation says the exclusion is *the firewall's own effect, not an absence of activity* |
| "the ledger is corrupt" when evidence is merely truncated | ⚠ **RETRACTED.** The original answer separated `INCOMPLETE_KNOWLEDGE_SEQUENCE` from `LEDGER_INCOHERENT_FOR_POSITION` by re-folding the key unfiltered. That discriminator read evidence recorded after `K` and is gone. The honest answer is that **M079 does not claim to know which it is**: both report `UNRESOLVED_KNOWLEDGE_SEQUENCE`, whose meaning is stated as *cannot be known from the evidence recorded by this cutoff alone* |
| "the operator kept poor records" | incompleteness is worded as a property of the **snapshot**, not of the operator |
| "this quantity is final" | the banner states a position reported open **may later prove to have been reduced** by an assertion recorded afterwards |
| "M079 disagrees with M076, so one is wrong" | both cutoffs are echoed in every rendering, and the design contrasts the two products explicitly |
| "this is a profit figure" | no field names a return, gain, loss, P&L or proceeds; asserted to be so by a test that walks every dataclass field |

## The safeguard is structural, not textual

The mission's rule is that no disclaimer may rescue misleading semantics.

M079's central guarantee is enforced by **arithmetic, not wording**: an
assertion with `recorded_at > K` is never in the candidate set, so it cannot
influence any count, status or derived position. The firewall is a predicate,
not a caveat.

⚠ **The following paragraph is RETRACTED.** It described the discriminator as a
safeguard when it was in fact the leak:

> ~~The second guarantee — that incompleteness never masks corruption — is
> likewise a computation: the key is re-folded against the unfiltered event set,
> and only a failure that *disappears* when the knowledge filter is removed is
> called incomplete.~~

The corrected second guarantee is stronger and simpler: the snapshot logic lives
in `_snapshot_from_known_evidence`, which is **never given the unfiltered
events**. Post-cutoff evidence cannot influence state, status, reason, counts,
limitations, ordering or classification, because it is not reachable. A test
asserts this against the function's own signature and source, so a refactor that
reintroduces the unfiltered set fails loudly.

## One thing worth stating plainly

M079 makes the platform's answers **less** convenient on purpose, and the Owner
correction made them less convenient still.

A historical snapshot will often show less than the operator now knows, and
sometimes show a position it cannot resolve at all — and it will no longer even
tell you whether that gap is likely to close, or how many assertions it hid from
you. Both of those would have required reading the future. That is the honest
shape of partial knowledge, and inventing coherence to avoid it would defeat the
milestone.
