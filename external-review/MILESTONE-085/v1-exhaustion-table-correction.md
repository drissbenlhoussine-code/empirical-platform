# V1 — the M085 exhaustion table: narrow correction, prepared (issue remains OPEN)

Status: **V1 OPEN.** The correction below is prepared in local commits for the Owner's review;
the acceptance table is an Owner-ratified artefact, and nothing here is a claim that Paper
acceptance advanced. Paper acceptance: NOT_STARTED. Not pushed; not merged; not frozen.

## 1. The issue as documented

`tools/render_m085_exhaustion_table.py --check` reported `exhaustion-table.md` (last rendered at
`754ceda`) as "not the current rendering". Re-rendering derived three `EXECUTED_FAIL_BLOCKER` rows
(recorded in `send-boundary-correction/verification.md` §5 with the full inventory):

| Row | Old expectation | Why it conflicted with the scoped ratification |
|---|---|---|
| 21 | any changed path matching `m084|MILESTONE-084` outside six audit-tooling files is unauthorized | it flagged `external-review/MILESTONE-085/m084-frozen-path-digests.json`, the **M085-owned** blob-id manifest introduced by the Owner-ratified freeze extension (`5ae236c`, PROJECT_CHECKPOINT §119) |
| 28 | `changed-files.txt` equals `git diff --name-status <base>...HEAD` | the inventory dated from `754ceda`: 78 recorded vs 163 actual at `37a2d55` (85 unrecorded) |
| 29 | `PROJECT_CHECKPOINT.md` absent from the diff | the Owner ratified exactly one change to it — the §119 record (+61 lines, two hunks), blob `ba9f8439…` unchanged since `5ae236c` |

## 2. The correction (commit `05eec31fb321f43eeb8017c7df67fba670e4f421`, tool + tests only)

- **Row 29** — `checkpoint_untouched_or_ratified(changed, blob_at_head)`: absent from the diff →
  untouched; present → PASS **only** when the blob at HEAD equals the ratified §119 content
  (`RATIFIED_CHECKPOINT_BLOB`, pinned in groups so no 40-hex token exists); anything else →
  "WAS MODIFIED beyond the ratified §119 record", as before. A single flipped character in the
  blob is reported (tested).
- **Row 21** — `m084_paths_authorized(changed, manifest_blob_at_head)`: the pattern is **not**
  widened; the six ratified audit-tooling paths remain authorized; the M085-owned manifest is
  authorized **only** while its blob equals `RATIFIED_M084_MANIFEST_BLOB`; any other manifest
  content and any other matching path is reported (tested, including a `.bak` sibling and a
  second M084 path in the same diff).
- **Row 28** — `changed-files.txt` regenerated from `git diff --name-status a224076...HEAD` at the
  revision that carries it (the docs commit that follows `05eec31`; its SHA is recorded in `crash-consistent-lineage/verification.md` §6); the rule itself is unchanged and
  still compares membership and status letters.
- **Header** — the rendered table now states which rows are executed at rendering time
  (1, 3, 20–26, 28–31) and which derive from recorded documents (2, 4–19, 27 — historical
  evidence of the runs that produced them, not re-executions); that row 12 records a bounded
  submission that was honestly **BLOCKED** and is not a successful external execution; that
  Paper acceptance is NOT_STARTED; and how rows 21 and 29 recognise the ratified content.
- Pins verified against the real objects: checkpoint pin == `HEAD:PROJECT_CHECKPOINT.md` ==
  `5ae236c:PROJECT_CHECKPOINT.md`; manifest pin == `HEAD:…/m084-frozen-path-digests.json`.

Not done, on purpose: no row is forced to pass; no expectation for any other row changed; no
M084 or checkpoint edit is excused in general. A future legitimate checkpoint edit (a §120) will
again fail row 29 until the Owner ratifies it and the pin is moved — that is the intended
behaviour.

## 3. Rendering

The table is rendered at the head that carries the regenerated inventory and committed in the
following docs-only commit; the derived summary line and both SHAs are recorded in
`crash-consistent-lineage/verification.md` §6, not asserted here in advance.

Row 15 reads `mutation-matrix.md` and reports what that document states ("121 of 121"), a
historical figure of the round that produced it; the current campaign has 153 families and its
per-round results live in the correction folders' verification records.

## 4. What remains open

V1 is closed only when the Owner reviews the corrected expectations and ratifies the rendered
table. Until then the table is prepared evidence, not acceptance. The historical rows (2, 4–19,
27) describe earlier runs, not the current candidate; the current candidate's own verification is
in `crash-consistent-lineage/verification.md`.
