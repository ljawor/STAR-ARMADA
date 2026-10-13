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

## Delivery gates still open

All proposed fixes, station-heavy measurements, replay-backed reproduction, native Windows performance, mixed-platform LAN pacing, candidate-package acceptance and human visual/gameplay acceptance are **pending**. Creating this plan closes none of those gates.
