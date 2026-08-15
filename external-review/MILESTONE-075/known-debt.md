# M075 — Known Debt

## Inherited, not introduced, not repaired

M062, M064 and M065 record dataset seals taken from Windows working-tree (CRLF)
materializations rather than committed blobs. On a clean LF checkout the affected suites
fail; on `windows-latest` (where CI runs) they pass.

**Blocking assessment, as the mission requires before ignoring or touching it:**

M075 introduces no fixture, no dataset bundle, and no byte seal. Its tests construct
typed domain objects in memory. It reads no file whose bytes are hashed. The debt
therefore does not block M075's capability, its tests, CI, or its reproducibility.

Per the mission's own rule, it is documented and **left alone**. No M062/M064/M065 file
is touched by this branch — verifiable from `changed-files.txt`.

## Introduced by M075

None known. Specifically:
- no new table, no migration, no schema change;
- no new persistence, no new repository, no new I/O;
- no worktree-dependent hash of any kind.

## Deliberately deferred to a future milestone

Durable position state, so that feasibility can account for what the operator already
holds. M075 assesses only the session's own same-day set and says so explicitly in every
rendering. This is the recommended M076 direction — recommendation only, not started.
