# Clean-clone seal reproduction — code head `36ef719`

Two clones of the same commit, differing only in `core.autocrlf`.

## M063 fixture

Git blob object: `800ecb199c2c47f8d719a5c6e10a7e94d57160c1`

| Clone | `core.autocrlf` | sha256 of the checked-out file |
|---|---|---|
| LF | `false` | `765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd` |
| CRLF | `true` | `765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd` |
| — | repaired seal constant | `765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd` |

Both clones reproduce the repaired seal. That is what the `-text` pin exists to
guarantee, and it is what the pre-repair seal could not do on either platform
at once.

## M064 fixture (must be, and is, unaffected)

| Measurement | Value |
|---|---|
| `survivorship_aware_dataset_bundle.json`, CRLF clone | `af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff` |
| M064's own recorded seal | `af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff` |

## `git check-attr text`

```text
tests/fixtures/m063_robustness_study/synthetic_broad_robustness_dataset_bundle.json: text: unset
tests/fixtures/m064_survivorship_aware/survivorship_aware_dataset_bundle.json: text: unspecified
tests/fixtures/m064_survivorship_aware/membership_manifest.json: text: unspecified
tests/fixtures/m064_survivorship_aware/instrument_master.json: text: unspecified
tests/fixtures/m065_corporate_action_mechanics/instrument_master.json: text: unspecified
```

`unset` is the M063 `-text` pin. `unspecified` is git's untouched default —
the pin does not reach M064 or M065.
