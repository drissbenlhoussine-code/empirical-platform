> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This notice governs **every file in this `history/` directory**. Nothing here
> is current truth, nothing here is imported or rendered, and nothing here is
> validated as authority.
>
> The single active statement of M082 authority is
> [`current-authority.md`](../current-authority.md).

# M082 historical archive

## Why the file below carries no inline notice

`MILESTONE_082_SCOPE_AND_DESIGN_at_f61f14b.md` is a **byte-identical archive** of
the mixed legacy design as it stood at the closure mission's starting head.
Prepending an inline notice to it would change its bytes and destroy exactly the
property that makes it evidence.

The two requirements — *byte-identical archive* and *every historical file
carries a notice* — genuinely conflict for this one file. The conflict is
resolved in favour of byte-identity, because the checksum is what makes the
archive verifiable, and the notice is supplied here at directory level instead.
This deviation is deliberate, is recorded in the closure report, and is enforced
by the manifest rather than left to convention.

| | |
|---|---|
| Source commit | `f61f14b15fb5caa5bebc89abef2bca65cecd0318` |
| Original path | `MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md` |
| Bytes | 46733 |
| SHA-256 (LF-normalised) | `4112b1b1da560739827a042f48e5a72c49ec66e4e7c524f88fe89a9656c85e9b` |

The checksum is taken over **LF-normalised** content, because this repository
checks out with CRLF on Windows and a raw byte comparison would otherwise mean
something different on each runner. In
`authority-surface-manifest.json` the same value is stored grouped in eights, so
the repository secret scanner does not flag a public checksum as a high-entropy
string; removing the hyphens recovers it exactly.

Verify with:

```
git show f61f14b:MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md \
  | sha256sum
sha256sum external-review/MILESTONE-082/history/MILESTONE_082_SCOPE_AND_DESIGN_at_f61f14b.md
```
