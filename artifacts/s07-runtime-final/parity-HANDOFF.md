# Authored role-submission parity — CPU handoff

Base HEAD: `56906ea7c73c219fbdc91c68176104b23d0f7712`. No commits or native GL performed.

## Result and scope

Only `_draw_ship_role_batch` production AST changed. Authored meshes bypass the two legacy role thresholds, preserving all six submitted roles at every apparent size; procedural and unresolved namespaced shapes retain the original `<16` and `<34` behavior. No assets/manifests/default-selection files changed. Existing station and asteroid controls remain intact.

Modified: `render/renderer.py` (owned function only), `tests/test_s07_lod_environment.py`. Added: `tests/test_s07_authored_lod_parity.py`, these `parity-*` evidence files. All GL endpoints are CPU recorders installed before executing extracted production AST. Resolver selection is a seam, not a native resolver/mesh/pixel test.

## RED → GREEN

- `parity-red.log`: retained initial test-fixture error (`logistics` instead of actual registry category `logistics_hull`), not behavioral RED.
- `parity-red-behavior.log`: real pre-fix RED, 222 authored subtest failures from suppressed roles; the legacy test passed. SHA256 `bd890489d79c3e684cf844c6738a29ff215abcf87e2f8484b94d52ff72dd714a`.
- `parity-green-focused.log`: first minimal-fix pass (2 tests).
- `parity-green-union.log`: updated authored/legacy old expectations, 7 tests passed.
- `parity-green-final.log`: 8 tests passed in 0.736s (external elapsed 0.829s). 37 core ship/squadron/construction/logistics bindings × 10 apparent sizes = 370 authored cached/uncached role cases, including 0, 1, both thresholds ±1e-6 and exact, 60 and 1000px. Legacy namespaced, unresolved namespaced and procedural controls also pass. Negative controls restore authored suppression, remove legacy suppression and skip selected-rock RNG. SHA256 `2bba87388a1164ba08177e26bcef6d9b4443deac8ad9ae5d8c01e7d4b488f242`.
- Every test subprocess uses `run-bounded.py --seconds 60`, independent process-group SIGKILL/wait, not tool timeout. `parity-watchdog-control.log.json` proves a sleeping control is terminated: deadline 0.25s, elapsed 0.256s, child exit -9, timed_out true.
- `git diff --check` passed. AST comparison with HEAD excluding only the owned function was identical. `git diff --name-only HEAD -- assets art/manifests` was empty.

## Confirmed remaining state mismatch — parent-owned regions

`parity-state-probe.py` executes actual `_draw_ships`, `_draw_ship_role_batch`, and `_draw_ship` bodies with CPU GL/material-state recorders for a stationary authored frigate at 60px, shader available both true and false. `parity-state-trace-attempt2.json` records all six role submissions and matches base/dark/trim/lit/cool state; **accent differs**:

- Cached `_draw_ships` calls `_material_matte()` **before** accent: specular `(0,0,0)`, shininess 0.
- Uncached `_draw_ship` calls `_material_matte()` **after** accent: accent inherits trim specular `(.85,.85,.85)`, shininess 12.

This is exact production call/state evidence, not proof that it accounts for every historical 3/5-pixel delta. Fix requires a parent decision/edit in `_draw_ship` and/or `_draw_ships`, neither edited here. Preserve quality: do not fix by weakening criteria or deleting authored detail. Cached caller already describes matte accent as intended; choosing the correction still belongs to parent.

`parity-state-trace.json` retains the initial diagnostic assertion error (incorrectly expected lit/cool differences too). Corrected probe shows only accent differs in the recorded stationary single-ship high-level material/enable/shader state. Successful state trace SHA256 `59acb469cb0b8cfcb22140add6da189f28dbec71cc9af01c7ca2794a96a7ce93`.

Additional structural differences requiring native investigation rather than assumptions: cached traversal is role-major across entities, uncached entity-major (depth ties/overlaps); cached emits every trail before hulls and every engine glow after hulls, whereas uncached interleaves per entity. One-entity CPU state recording does not adjudicate those pixels, driver state, rasterization, or motion.

## Pins at handoff

- `_draw_ship_role_batch` exact source region SHA256: `8313054094264c6a498f1123660e059a79f4f495dac3bd19c14ad9155f9d67c9`
- `render/renderer.py`: `41e377942fbccd54953409cb8b13b6f3ec82801d01e4545580c0aaf3d55a9b26`
- `tests/test_s07_lod_environment.py`: `5c7c246baab7af3c067b5e4d70088df9e296d7ce1f055b4a826008d4386695e0`
- `tests/test_s07_authored_lod_parity.py`: `98e395c1c600edc2a36c4c6c579c53c8ff2cdd0960fb494904cc234ae1ab21ac`

No full S07, native material parity, pixel parity, motion, performance or platform acceptance claim. Parent retains exclusive native GL and must verify exact pixels after resolving the accent mismatch.
