# Controls

Three sabotages of the field, run through the same tool with `--control`, so the checks in
`../native-field-verification.json` can be shown to notice a field that is wrong rather than to
pass everything. Each JSON is the tool's own output.

    python tools/render/verify_native_asteroid_fields.py --out OUT --control scale3

| control | what it draws | rejected by |
| --- | --- | --- |
| `scale3` | every rock three times too large (`ASTEROID_EXTENT / 3`) | `is_a_scatter_not_a_boulder` (`disc_fill` 0.688) |
| `shift` | the belt translated by 0.8 of the field radius | `centred`, `size_matches_projection` |
| `boulder` | one rock filling 0.95 of the radius, the old picture | `is_a_scatter_not_a_boulder` |

These are engineering controls about the measurement, not appearance evidence: the owner was not
asked to look at them and they are not in the manifest's `reviewed_evidence`.

The tool exits 0 for a control only when the control is caught, and exits non-zero if a sabotage
slips through every check.
