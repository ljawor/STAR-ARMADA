# STAR ARMADA — caller-local orbit terrain reuse

## 1. Scope

Second Mac performance pass on 2026-10-15, against immutable control
`7a0e8938a97ae6ff02630d0b35de9d093e65a8c4`. This is a narrow follow-up to
`GRAPHICS_MAC_OPTIMIZATION.md`, not a new art milestone. Filip's laptop, native
Windows graphics and physical mixed-machine play remain deferred. No merge,
release, balance change, quality cut, visibility cache or LAN pacing change.

The candidate changes only `game/systems/construction.py` and
`game/systems/satellite_orbits.py`, with new regressions in
`tests/test_orbit_spacing_batch.py`. Tested source hashes are recorded in the
round-two evidence `candidate-manifest.json`.

## 2. Fresh profiling and choice

Four stock/stress combat/distributed workloads ran in serial fresh processes,
each with an ordinary control, cProfile stages and a separate fine-scope run:
12 successful runs with 10 warmup +30 measured ticks. All initial/final precise
state and final LAN checksums matched within each workload. These diagnostic
40-tick windows are not comparable as gains against the earlier 70-tick tables.

Profiles found 32,640 calls to `orbit_geometry` per 30 measured ticks in every
workload: each spacing check rebuilt identical terrain inputs for many live or
paid satellites, despite cached numerical orbit plans. Fine scopes measured
about 6.4 ms/tick stock and 12.2 ms stress inside terrain geometry. Nested
instrumented costs overlap and are opportunity bounds, not promised savings.

Stress-combat simulation still spends heavily on live sensor validation:
3,369,645 `SensorQueries.radius` calls versus only 652 actual
`effective_sensor_range` calls over the profiled 30 ticks. Reusing presentation
snapshots in simulation would break same-tick liveness; no such change was made.
Hit geometry, apparent-size/projection work and canonical LAN serialization also
remain measured candidates, not implemented optimizations in this pass.

## 3. Change and safety boundary

A `_check_station_spacing` invocation creates a private input collector lazily,
only when valid orbit geometry needs terrain. It gathers eligible live planets
once in stable ID order and freezes their numerical body tuples. Each geometry
query excludes its own parent by object identity, retaining the original exact
terrain-key shape and ordering. No exclusion is based solely on mutable IDs.

The collector exists only on that synchronous, read-only spacing call's stack.
It is not stored on state, the construction system or an entity. There are no
gameplay callbacks or terrain mutations in that path. Standalone public
`orbit_geometry` queries retain live input assembly. Every later spacing call,
even within the same tick, reads current terrain anew. Configuration, catalogue
hulls, parent geometry, bounds, station spacing, visibility, queue ownership and
paid reservations retain their original checks and first-rejection order.

No legality/visibility answers, orbit-update-wide snapshot, cross-call/tick
cache or changed floating-point arithmetic is introduced. The existing bounded
numerical terrain solver cache is unchanged.

## 4. Paired uninstrumented results

Apple M4 /24 GiB, Cocoa, GL 2.1 Metal -90.5, observed 1280x800 drawable/viewport,
actual 4x MSAA, shader enabled, reported swap interval 0. No data, pass-skip or
no-cull override. Same original stock/stress fixtures and catalogue inputs.

Three fresh-process full trials per revision and fixture, with alternating
control/candidate order, plus one sim-only run per revision: 32 accepted reports.
Each uses 10 warmup +60 measured ticks; 60 stage samples and 59 frame/swap samples
because the capture-adjacent last frame/swap is excluded. Values below are
medians of the three trial means, not pooled durations or profiler timings.

| Workload | Simulation ms, control → candidate | Frame ms, control → candidate | Frame reduction |
|---|---:|---:|---:|
| stock-distributed | 21.55 → 18.64 | 42.03 → 39.09 | 7.0% |
| stock-combat | 22.35 → 19.48 | 57.23 → 54.51 | 4.7% |
| stress-distributed | 53.92 → 45.95 | 112.17 → 104.06 | 7.2% |
| stress-combat | 208.64 → 199.28 | 346.30 → 338.03 | 2.4% |

| Workload | Frame p95 ms, control → candidate | Frame p99 ms, control → candidate |
|---|---:|---:|
| stock-distributed | 43.90 → 41.47 | 45.44 → 41.94 |
| stock-combat | 60.22 → 58.72 | 61.93 → 59.37 |
| stress-distributed | 136.80 → 129.25 | 139.42 → 131.35 |
| stress-combat | 571.05 → 569.87 | 580.56 → 574.18 |

These synchronized diagnostic costs are **not interactive FPS**. LAN checksum
measurement is separate, outside frame cost, and has no sockets/barriers. No
checksum improvement is claimed. The measured simulation gains justify this
small patch; stress combat remains far from an ordinary interactive budget.

## 5. Exact equivalence and regression gates

- All 32 ordinary reports agree within each fixture on exact initial/final
  simulation hashes and final precise LAN checksum, across both revisions and
  sim/full modes. Every full report passed driver-quality assertions.
- Five fresh-process frozen-clock scenes (both stock, both stress and flagship)
  each have control/control/candidate equality for precise state, LAN checksum
  and exact framebuffer SHA256. Renderer `diff_render=True`, fixed time zero,
  5 warmup +20 measured ticks. All 15 captures are pixel-identical within their
  scene; repeated-control equality establishes a meaningful zero-delta gate.
- All 39 new acceptance captures were inspected in timing/frozen contact sheets.
  No new blank, inverted or missing-HUD render was observed. Existing dark/sparse
  stock framing, dense marker/shield overlap and modest flagship view remain.
- RED operation-count test failed with seven entity scans instead of two. GREEN
  uses one spacing loop plus one terrain assembly, one terrain sort, across live
  and paid satellites; the explicit legacy negative control still reports seven
  scans/six sorts. No geometry path performs no terrain scan; invalid config
  still rejects before assembly.
- Fifteen new tests compare explicit pre-change spacing/geometry oracles,
  exact solver keys, endpoint/ring/paid/hostile first-rejection reasons, viewer
  authority, ignored work/entities, malformed config/hulls/parent/bounds, stable
  duplicate IDs with identity exclusion, same-tick live mutation between calls,
  swept legality and precise-state purity. The numerical solver is unchanged.
- Ninety-five focused orbit, construction, terrain and deterministic-math tests
  passed, including the 15 new regressions. No gameplay assertion was weakened.

## 6. Integration and delivery

Final protected whole-tree retry: **1,660 tests run, zero failures, zero errors,
nine recorded skips**. Seven require the native Windows kernel, one fixture has
shields, and one requires a Git checkout absent from the archive. The Git-only
test separately passed behind native protection in the actual checkout; it is
supplementary, not added to the discovery total. Independent static review
passed with no security/logic findings. All 426 candidate files and the three
live implementation/test files matched their pinned source hashes.

The runner retained all five per-fixture/per-child persistence redirects and a
native descendant-inherited deny-write sandbox protecting the actual checkout
and Application Support. Safety self-test passed with three intentional audit
rejections; both full-suite runs preserved source and user data with zero
unexpected audit violations.

The first 1,660-test discovery had two errors, retained in `full-suite/`: the
malformed-crew real-TCP test and natural Stop-257 test both failed in
`LanSession.host` at `listener.bind` with `Address already in use`, before
manager construction. Networking and test fixture files are byte-identical to
the control. Both tests passed three ordinary repetitions on each revision;
deliberately occupying the existing fixture's released `free_port()` result
reproduced the same bind failure in both tests on both revisions. This establishes
the existing free-port selection vulnerability, not the identity of the process
that occupied either original port. No application/test assertion, bind logic or
timeout was changed. The unchanged candidate's full-suite retry passed.

The new portable operation-count/differential module is included explicitly in
the existing Windows LAN CI list. Native Windows CI outcome is a separate
pushed-head delivery gate, not evidence of Filip's graphics acceptance.

## 7. Reproduction and remaining gates

Use the existing real-driver benchmark CLI from an explicit evidence directory:

```sh
mkdir -p benchmark-reports
SDL_VIDEODRIVER=cocoa .venv/bin/python main.py --benchmark --fixture four-player-stock-combat-v1 --mode full --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --lan-checksum --output benchmark-reports/stock-combat.json --screenshot benchmark-reports/stock-combat.png
PYTHONPATH=tests .venv/bin/python -m unittest test_orbit_spacing_batch test_orbit_terrain_scan test_detmath -q
```

For full discovery on a machine with real saves, use the isolated immutable
snapshot/native sandbox procedure from the previous Mac acceptance report, not
unsafe live-checkout discovery. The evidence contains comparison/frozen/profile
harnesses, manifests, raw reports, captures, operation RED/GREEN logs and the
protected runner. Absolute scratch paths identify this Mac and require explicit
adaptation elsewhere.

No new artwork or catalogue rollout is claimed. Sustained play, agreed
FPS/resolution, owner-approved real-renderer capital/escort/station slice,
packaged runtime and native Windows graphics remain separate gates.
