# Performance improvement plan

## Status and agreed scope

Planning only: no performance fixes have been implemented by this document.

**User decision: leave station rotation exactly as it is.** Preserve model detail, materials, lighting, windows, shields, combat effects and player colours. Do not obtain speed by removing visual passes, reducing geometry or changing gameplay.

The filename `PERFROMANCE_IMPROVE.MD` is intentional and follows the requested name.

## Reported problem

During a Windows–macOS multiplayer match, macOS hosted and frame rate fell below 8 FPS. The user reported one second of game time taking approximately 5–8 seconds of real time. That exact mixed-platform match has not yet been reproduced or accepted on both machines.

## Investigation baseline

Source inspected: commit `725826143670c9c99066d49249cc930534274e90`, version 0.12.0.

### Multiplayer pacing finding

`main.py:advance_simulation` services at most one LAN simulation tick per rendered frame. The simulation expects 30 ticks per second. With 8 rendered frames per second, this limits progress to at most 8 ticks per real second: one simulation second takes at least 3.75 real seconds. Lower frame rates and input-barrier waits can make it slower.

This explains a slowdown mechanism, not the complete cause or measured breakdown of the reported match. Investigate render throughput and network readiness separately. Both peers run lockstep simulation; do not assume hosting alone causes the cost.

### Executed local stress benchmark

Environment: native macOS, Apple M4, Python 3.11.16, pygame-ce 2.5.8, SDL 2.32.10, Cocoa, OpenGL 2.1 Metal - 90.5, shader enabled. Effective viewport 1280×800, actual 4× MSAA, reported swap interval 0.

Workload: existing `corvette-combat-v1` fixture; 500 ships plus two remote command stations; five warmup frames and 30 measured frames, with all 35 requested simulation ticks executed.

| Stage | Median ms | p95 ms |
| --- | ---: | ---: |
| Simulation | 23.781 | 32.417 |
| Camera | 2.364 | 2.431 |
| World rendering | 86.479 | 173.691 |
| HUD | 6.100 | 7.523 |
| Swap | 0.356 | 2.925 |
| Complete frame | 122.916 | 207.682 |

Stage medians are independent statistics and should not be added to reconstruct the frame median. Full-mode stages use `glFinish` boundaries: these are synchronized CPU/driver/completed-GPU durations, not isolated GPU timings or ordinary gameplay FPS. Capture-adjacent swap/frame samples are excluded by the benchmark.

The fixture excludes AI, audio, input, menus and networking. It is a dense combat stress test, not evidence for a developed colony/station-heavy match. Final counts included 1,200 effects; interval-wide counts, rather than the final projectile count alone, must establish combat activity.

A separate instrumented run (500 ships, three warmup frames, 15 measured frames) identified significant cumulative work in `_draw_ship`, `_draw_ownership_markers`, `_draw_shields`/`_shield_bubble`, repeated `_ship_size` and `_px_per_world` queries, camera basis calculations, and PyOpenGL wrappers. Simulation also spent time in weapons and separation. Profiling overhead changes timings: use this run to identify work, not to calculate speedups against the uninstrumented table.

Original local evidence, subject to scratch-directory pruning:

- `/Users/lukaszjawor/.hermes/cache/scratch/armada-perf-investigation/full.json`
- `/Users/lukaszjawor/.hermes/cache/scratch/armada-perf-investigation/full.prof`

The findings and timing table above survive independently of those temporary artifacts. Regenerate evidence when resuming; do not treat these historical timings as current acceptance.

## Proposed workstreams, in priority order

### 1. Decouple LAN tick servicing from render frequency

**Files to inspect:** `main.py`, `game/net/`, existing LAN pacing and recovery tests/diagnostics.

1. Reproduce the low-render-rate limit through the actual production tick driver in two independent processes.
2. Record rendered FPS, executed simulation ticks per real second, simulation duration, barrier waits, ready-input backlog and maximum advance-call duration for both peers.
3. Compare normal pacing, deliberately low render pacing and real SDL Clock pacing. Include quantized 33/33/34 ms deltas; idealized deltas alone hide accumulator defects.
4. Design a bounded servicing mechanism that can handle already-ready simulation work independently of render frequency. Reconsider the existing one-step/no-catch-up contract explicitly before changing it.
5. Preserve input delay, ordered commands, checksums, nonblocking socket reads, disconnect/recovery handling and deterministic simulation time. Never advance through an unready input barrier or accrue unbounded catch-up debt while stalled.
6. Prove progression, input responsiveness and exact state equality through hitches, stalled peers and reconnects. Then exercise native Windows–macOS LAN.

**Acceptance:** low rendering frequency must not impose an artificial one-tick-per-frame ceiling when inputs are ready and CPU capacity is sufficient. Target the configured 30 Hz; retain the existing normal-pacing gate of at least 27 ticks/sec. Do not claim real-time progress if authoritative simulation itself cannot fit the tick budget.

### 2. Eliminate redundant render-side calculations

**Files to inspect:** `render/renderer.py`, `render/camera.py`, `render/ship_sizes.py`, visibility interfaces.

1. Count repeated basis, projection, visual-size and bounds calculations separately from unprofiled timing.
2. Compute reusable view information once for an unchanged camera/view configuration.
3. Reuse entity visual calculations across hull, ownership-marker and shield passes where their inputs are identical.
4. Invalidate on camera/viewport changes, scene/viewer changes and relevant entity/visual inputs. Keep visual caches render-side and out of saves/checksums.
5. Preserve current live visibility checks: do not replace them with a stale tick-wide visibility cache.

**Acceptance:** exact full-precision simulation equality and matching frozen framebuffer controls; reduced calculation counts and fresh-process timing under identical effective graphics settings.

### 3. Cache station model-space bounds

**Files to inspect:** `render/planet_building_geometry.py:station_camera_box`, `render/camera.py:refresh_scene`, faction/mesh caches.

The attached-hardware path currently gathers vertices and recomputes model-space minima/maxima before camera-ray rejection. This is a concrete optimization candidate, but its contribution in the reported match has not been measured.

1. Measure a developed scene containing surface buildings and satellites, not only free stations.
2. Cache canonical local-space mesh bounds by the actual visual identity, with appropriate invalidation for catalogue/mod changes.
3. Continue applying live position, radius, surface/satellite frame and rotation to the bounds. **Keep station rotation unchanged.**
4. Preserve safe-eye geometry and visibility filtering; compare against exhaustive original bounds and existing close-camera probes.

**Acceptance:** same effective camera eye and picking/projection behaviour, no clipping regression, exact simulation preservation and lower station-heavy camera preparation cost.

### 4. Reduce draw submission and material-state overhead

**Files to inspect:** ship/station drawing, material management, shield/marker/effect helpers and GL resource lifecycle.

1. Separate Python submission overhead from completed rendering cost using measurements and call counts.
2. Investigate batching compatible opaque geometry/material work, followed by appropriate marker/shield work.
3. Use only capabilities supported by the actual native macOS and Windows contexts. Do not assume modern instancing APIs are available in the current OpenGL 2.1 path.
4. Preserve all material roles, shader/fallback behaviour, owner colours, emissive hardware and effect coverage. Preserve transparent ordering and blending.
5. Verify construction, first upload/draw, repeated drawing, resize/rebuild and cleanup before SDL teardown.

**Acceptance:** unchanged controlled images where applicable, documented visual-equivalence tolerances where submission order legitimately changes rasterization, and real GL lifecycle tests. No claimed gain obtained by skipping effects or drawing fewer visible objects.

### 5. Profile and optimize the actual developed-match workload

1. Locate the relevant user replay read-only in both source and packaged-app user-data locations; identify it by metadata, version and content digest rather than unrelated file timestamps.
2. Establish a compatible immutable source baseline before replaying. A compatibility rejection is not a performance result.
3. Retain snapshots at early, developed-base and worst combat stages, with exact entity IDs/counts and executed ticks.
4. Profile simulation, camera, world subpasses, HUD, audio and networking separately. Include planets, asteroids, satellites, colonies, construction and AI.
5. Replays do not contain camera telemetry and snapshots may omit transient effects. Label inferred views and reconstruct effects through actual replay ticks where possible.
6. Optimize remaining simulation hotspots only after measuring them. Preserve nearest-target ties, authoritative candidate order, sequential separation mutations and live detection semantics.

**Acceptance:** improvements demonstrated on representative developed scenes as well as the fixed stress benchmark. Native mixed-platform acceptance remains separate from local source tests.

## Resume checklist

- [ ] Inspect Git status, current main/open PRs, releases and existing performance tools before editing.
- [ ] Read this document and preserve the decision to retain station rotation and visual quality.
- [ ] Identify the reported game's build, graphics settings, map, approximate population and compatible replay.
- [ ] Freeze baseline revision and collect standalone timing without concurrent tests/profilers.
- [ ] Add a red-capable regression for each confirmed cause before implementation.
- [ ] Implement one root cause per feature branch/PR; coordinate shared-file ownership if work runs in parallel.
- [ ] Compare baseline/candidate precise state and controlled real-GL frames.
- [ ] Run focused regressions, independent review and the stable full suite.
- [ ] Exercise candidate frozen packages; then test Windows–macOS with the Mac hosting, and reverse roles as a control.
- [ ] Record per-peer FPS, simulation ticks/sec, stage times, barrier waits, settings, hardware/power mode and candidate revision.
- [ ] Report measured gains and remaining bottlenecks. Merge/publication require separate authorization.

## Existing tool entry points

Run from the repository root. Create an existing writable evidence directory and replace `<evidence-dir>` below; do not type that placeholder literally.

```sh
# Focused performance/reporting/GL lifecycle contracts
PYTHONPATH=tests .venv/bin/python -m unittest test_performance test_separation_performance test_fog_render test_gl_lifecycle -q

# Fixed-combat simulation-only measurement
.venv/bin/python main.py --benchmark --mode sim --units 500 --frames 60 --warmup 10 --output <evidence-dir>/sim.json

# Real SDL/OpenGL measurement; never use SDL dummy for this
.venv/bin/python main.py --benchmark --mode full --units 500 --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --output <evidence-dir>/full.json --screenshot <evidence-dir>/full.png

# Inspect this tool's current options/baseline selection before using its comparison
.venv/bin/python tools/benchmark_compare.py --help

# Final stable whole-tree suite, after timing and integration are complete
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
```

Also inspect the current camera diagnostics (`tools/diag_close_zoom.py`, `tools/diag_camera_refresh_perf.py`) and production LAN pacing/recovery diagnostics before selecting gates. The fixed-combat benchmark is not a replacement for developed-base or multiplayer acceptance.

## Implementation steps (in progress)

### Step 1 — Cache per-frame view-dependent calculations

**Files:** `render/renderer.py`, `render/camera.py`, `render/fleet_materials.py`

1. Add a per-frame render cache keyed by `(state.tick, camera geometry, selection, local_player, marker_mode, skip set, frozen time)`.
2. Cache the camera eye, basis, forward vector and the constant `height / (2 * tan(fov/2))` scale factor.
3. Cache per owner: `_owner_color`, `_relation`.
4. Cache per visible entity: position tuple, `_ship_size` / station visual radius, `_px_per_world` at camera depth, apparent screen size, shield radius, in-front test and owner color.
5. Reuse these values across `_draw_ships`, `_draw_ownership_markers`, `_draw_shields`, `_draw_selection_rings` and effect passes; do not recompute them for every subpass.
6. Make `FleetMaterials.hull_pass()` safe when called outside an active hull program (no-op) so batch helpers can switch passes without `GLError 1282`.

**Measured result (M4, 500 corvettes, 1280×800, 4× MSAA, vsync off):**
- `world` median: **98.5 ms → 88.0 ms** (~10.7 % reduction)
- `frame` median: **133.5 ms → 125.4 ms** (~6.1 % reduction)
- full-precision simulation checksum unchanged.

### Step 2 — Batch ship/station draws by material role

**Files:** `render/renderer.py`

1. Replace per-entity `_draw_ship` / `_draw_station` loops with a single pass that collects visible ships/squadrons and stations, pre-resolves their display-list IDs and transforms.
2. Draw all opaque hull roles (`base`, `dark`, `trim`) in role order, binding the hull GLSL program once per role and updating only the `materialPass` uniform per entity.
3. Draw the `accent` pass with matte lighting/texturing disabled once for all entities.
4. Draw all emissive roles (`lit`, `cool`) in a single lighting/texturing-disabled batch.
5. Keep engine trails before the hull pass and engine glows after it; keep station construction rings after station hulls so draw order semantics are preserved.
6. Continue using the existing display lists and do not drop any visual pass.
7. Restore the active shader program to `0` at the end of `_draw_ships` so ownership markers/effects/HUD are not drawn with the hull program still bound.

**Measured result:** same benchmark as Step 1; the role batching is the dominant share of the world-stage reduction. Visual output matches the original when the animation clock is frozen; benchmark screenshots differ only because the benchmark does not freeze `renderer.time`.

### Step 3 — Single visible-entity list per frame

**Files:** `render/renderer.py`

1. Build one filtered list of currently visible alive non-planet entities inside the frame cache.
2. Use this list for hull drawing, shield bubbles, ownership markers and selection rings instead of re-iterating `state.entities.values()` and re-running `can_see` in every pass.
3. Invalidate the list whenever the frame-cache key changes.

**Measured result:** `can_see` and entity iteration are now executed once per visible entity per frame rather than once per render subpass.

### Step 4 — Per-size material-role LOD

**Files:** `render/renderer.py`

1. Add configurable pixel-diameter thresholds (`_LOD_BASE_ONLY_PX`, `_LOD_DETAIL_PX`) to `_draw_ship_role_batch`.
2. For ships below `_LOD_DETAIL_PX`, skip the `dark`, `trim`, `accent` and `cool` detail roles; only the `base` hull and `lit` emissive windows are drawn.
3. For ships below `_LOD_BASE_ONLY_PX`, draw only the `base` role.
4. Stations and close ships retain all six roles so quality is preserved where the detail is readable.
5. The LOD decision uses the same cached `apparent` screen diameter that the readability scaler already computes, so no extra work is added per frame.

**Measured result (same 500-corvette benchmark):**
- world median: **88.0 ms → 75.4 ms** (additional ~14.3% reduction)
- frame median: **125.4 ms → 114.8 ms** (additional ~8.5% reduction)
- cumulative vs baseline: world **98.5 ms → 75.4 ms** (~23.5%), frame **133.5 ms → 114.8 ms** (~14.0%).

### Verification run so far

- `python -m compileall -q game render main.py` — clean.
- `PYTHONPATH=tests ./.venv/bin/python -m unittest test_performance test_separation_performance test_fog_render test_gl_lifecycle -q` — 35 tests OK.
- Full suite (`discover -s tests`) — 1162 tests OK.
- Full benchmark (baseline vs cache+batch vs cache+batch+LOD) on M4, 500 corvettes, 1280×800, 4× MSAA, vsync off:
  - baseline: world median **98.5 ms**, frame median **133.5 ms**.
  - after Steps 1–3: world median **88.0 ms**, frame median **125.4 ms**.
  - after Step 4 LOD: world median **75.4 ms**, frame median **114.8 ms**.
  - simulation checksum unchanged in all runs.

### Remaining work / next steps

- [ ] Decide whether the now-visible shield bubbles are acceptable (the baseline may have inadvertently suppressed them). If they must stay subtle, tune the bubble alpha/radius rather than disabling the pass.
- [ ] Run the complete stable test suite again after LOD.
- [ ] Station-heavy and developed-base benchmarks.
- [ ] Replay-backed reproduction and LAN pacing only after the renderer reliably clears the 33 ms frame budget.
- [ ] Windows native performance and candidate-package acceptance remain pending gates.

## Delivery gates still open

Station-heavy measurements, replay-backed reproduction, native Windows performance, mixed-platform LAN pacing, candidate-package acceptance and human visual/gameplay acceptance are **pending**. The renderer is not yet reliably inside the 33 ms frame budget, so LAN pacing work is still blocked.
