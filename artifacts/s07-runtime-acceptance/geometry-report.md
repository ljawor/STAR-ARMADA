# S07 selected geometry — bounded CPU acceptance

## Result

At `8b3f03b9ec6371ac7a469123741e130af03d983b`, the new standalone module passes **8 tests** in **12.385 s**. The instrumented reproduction passes **899 subtests**, zero failures/errors, in **12.487 s**. This is CPU geometry acceptance only, not GL, default activation or release approval.

- **102 core bindings / 106 live consumers**, enumerated via `route_identity` from the real inventory and live DataStore.
- Categories: 18 combat hulls, 7 squadron hulls, 8 construction hulls, 4 logistics hulls, 40 stations, 8 satellites, 16 planet installations, 1 environment prop.
- Selected mesh/revision/hash/payload closure covers all 102 bindings. Both convoy consumers are explicit for each of four faction bindings.
- Raw payload all-role bounds/radii cover all 101 ship/station-family bindings.
- **246 ship consumer cases**: 41 consumers × three headings × two viewport heights. Data faction wins on captured catalogue ships; the four dataless trade convoys use owner faction. Crew/trade share geometry but independently retain **0.8 / 1.0** corvette-calibrated length ratios. Collision radii are deliberately inflated to prove they do not size ship visuals.
- **120 station cases**: 40 current-owner bindings × three cosmetic rotations. All 64 station-family bindings additionally exercise current-owner capture family changes via the real renderer visual-radius consumer.
- **160 attached cases**: 16 installations × all six surface slots, plus eight satellite bindings × eight deterministic orbital placements. Real camera refresh, raw-frame/world-mesh agreement, renderer contact and input picking execute for every case. The south surface slot is checked as a deliberate back-face pick rejection with the legal positive-pitch camera; it is not claimed selectable from below.
- Real `_single_select` picks projected authored geometry. Normal-resolution free ship/station picks explicitly lie beyond the 28-pixel center fallback, followed by a distant miss. Small-resolution readability cases retain small-contact affordances.
- Free ship/station cases also refresh at the real 180-unit close zoom and independently reject near-plane entry into selected bounds.
- Full precise authoritative state hashes remain unchanged around the read-only geometry operations.

## Independent oracle

The test decodes approval-pinned runtime mesh JSON indices directly, separately from resolver/fleet bounds/contact helpers. It computes all-role extrema and radii from referenced triangle vertices, reconstructs rotations and six surface frames independently, checks center-out contacts using ray-plane intersection plus oriented edge containment (not the production Moller–Trumbore implementation), and checks renderer contacts for membership on raw transformed triangles. Scale ratios and the unchanged procedural corvette calibration are independently specified.

The positive test calls real `selection.configure(model_preview=True)` and actual consumers. No selected geometry is mocked in the positive run.

## Negative control and preservation

The control leaves the real resolver/configuration intact but patches **only** `selection.mesh_for` to return `None`. The selected-revision closure then produces **exactly 102 binding assertion failures**, zero errors, in **1.489 s**. The control runner succeeds only if that exact failing result is observed. Raw failure names and tracebacks are retained.

Both measured runs restore the exact outer nonempty DataStore object and ship/station memberships, selection preference object, resolver object and generation. **214** protected model/manifest/approval/pipeline-policy JSON files are hashed before/after and remain unchanged. Individual matrix cases additionally preserve `game.benchmark.state_hash`.

## Reproduce

From the repository root:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest -v test_s07_selected_geometry_matrix
.venv/bin/python artifacts/s07-runtime-acceptance/geometry-runner.py
.venv/bin/python artifacts/s07-runtime-acceptance/geometry-runner.py --negative-selection
```

The runner writes `geometry-results.json` / `geometry-negative-selection.json`; redirect stdout/stderr to new raw logs if preserving another receipt. The standalone test writes no artifacts/settings.

Primary evidence:

- `geometry-standalone.log`: final ordinary unittest invocation.
- `geometry-acceptance.log` and `geometry-results.json`: complete instrumented positive run, enumerated applicability, raw subtest parameters/outcomes and protected hashes.
- `geometry-negative-selection.log` and `geometry-negative-selection.json`: exact selected-seam failure control.
- `geometry-runner.py`: reproducible instrumentation/control runner.

Test module SHA-256: `9df1c2dd8d58c818ca637a97a7fc7484188f58f88efc031d1c035392514dddd4`.

## Limits / uncovered items

- No GL context, rendered pixels, material passes, shield-shell/VFX geometry, construction preview, packaged platform, external pack or approval-policy revalidation.
- The environment prop receives selected revision/payload closure only. Its per-instance field draw transforms, camera/contact/pick behavior are outside the generic ship/station consumer matrix.
- One oblique center-out contact ray per free ship/station rotation; fallback contacts are checked for actual triangle membership, not exact nearest-point optimality across every possible impact.
- One camera view per attached placement, no orbital time evolution or exhaustive camera/heading product. Attached camera boxes are independently reconstructed and observed through real refresh; the extra close-zoom/near-plane sweep is for free ships/stations.
- Owned entities use real GameState visibility. Enemy fog/sensor behavior and OS mouse events are not covered here.
- These fixtures demonstrate existing behavior. No production defect was found in the exercised paths; no production changes were made.

## Retained fixture-development failures

All earlier logs remain, including superseded passing runs. `geometry-initial.log` is large (~38 MB): 64 failures came from a test-only subsidiary-station facade call with reversed arguments and unsupported families; two came from an absolute oriented-edge oracle tolerance inappropriate to tiny squadron triangles. Those fixture errors were corrected (proper facade applicability/signature and area-relative edge tolerance), without changing production code. `geometry-pick-sample-initial.log/json` retain three test-sample failures where a 300-unit squadron view did not put the sampled vertex beyond the center fallback. The fixture now uses a legal closer 180-unit minimum so that its stronger non-center picking assertion is actually exercised. No assertion was weakened.

Owned deliverables are only `tests/test_s07_selected_geometry_matrix.py` and `artifacts/s07-runtime-acceptance/geometry-*`. Other dirty tests/artifacts belong to sibling work. No commits, registration, approved byte changes, default switches, merge or release actions were performed.
