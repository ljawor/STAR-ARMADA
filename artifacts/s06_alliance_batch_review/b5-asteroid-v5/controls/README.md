# Controls

Three sabotages of the field, run through the same tool with `--control`, so the checks in
`../native-field-verification.json` can be shown to notice a field that is wrong rather than to
pass everything. Each JSON is the tool's own output; the numbers below are copied from them.

    python tools/render/verify_native_asteroid_fields.py --out OUT --control scale3

| control | what it draws | rejected by | from the JSON |
| --- | --- | --- | --- |
| `scale3` | every rock three times too large (`ASTEROID_EXTENT / 3`) | `is_a_scatter_not_a_boulder` | `disc_fill` 0.676 |
| `shift` | the belt translated by 0.8 of the field radius | `centred`, `size_matches_projection` | `centre_error` 0.125 / 0.083, `size_ratio` 2.67 / 1.22 |
| `boulder` | one rock filling 0.95 of the radius, the old picture | `is_a_scatter_not_a_boulder` | `disc_fill` 1.176 |

`scale3` is the case a bounding box cannot see: the field's box is clipped by the frame, so
`size_ratio` stays at 0.97 / 0.93 and only the disc fill and the frame-edge check object.

These are engineering controls about the measurement, not appearance evidence: the owner was not
asked to look at them and they are not in the manifest's `reviewed_evidence`.

The tool exits 0 for a control only when the control is caught, and exits non-zero if a sabotage
slips through every check.
