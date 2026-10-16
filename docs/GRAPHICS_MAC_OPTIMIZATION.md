# STAR ARMADA — Mac profiling and quality-preserving headroom

## 1. Scope and result

Measured on 2026-10-15. This completes the current Mac acceptance/profiling pass
for the approved graphics roadmap; **Filip’s native Windows laptop testing is
deferred**. This is a performance change, not the Homeworld-inspired art upgrade.
No new geometry, materials, lighting, gameplay rules or camera mechanics ship here.

Control: `44e8af42cdf0dabe44e641156590f90a8ee46661`.
Candidate: the five production changes described below plus three regression-test
files, pinned by SHA256 in `optimized-snapshot-manifest.json` in the evidence.
All eight live files matched the tested immutable candidate after acceptance.
Unrelated local prototypes, artifacts and `docs/UNREAL_PORT.md` are excluded.

The same stock and stress workloads become materially cheaper, without reducing
units, geometry, passes, visibility accuracy or actual 4x MSAA. Final integration:
**1,645 tests run, zero failures/errors, nine recorded skips**, plus one passing
Git-checkout-only supplemental test. Native Windows graphics, packaging,
sustained play and physical mixed-platform LAN remain separate open gates.

## 2. Measurement method

Apple M4, 24 GiB, Cocoa; GL `2.1 Metal - 90.5`, pygame-ce 2.5.8 / SDL 2.32.10.
Requested and observed drawable/viewport 1280x800, actual 4x MSAA, shader on,
reported swap interval zero. `STAR_ARMADA_DATA`, render pass skips and no-cull
inputs were unset. Original fixture recipes, catalogue inputs, normal player
fog and command accounting are unchanged; see `GRAPHICS_BENCHMARK.md`.

Each of four workloads has three fresh-process full trials per revision, run
serially with alternating control/candidate ordering, plus a sim-only control
per revision. Every run uses 10 warmup and 60 measured ticks at 1/30 second.
Capture-adjacent final frame/swap is excluded: 59 frame/swap samples, 60 other
stage samples per full trial. Tables give **medians of the three trial summaries**,
not pooled durations. Raw JSON retains all samples, activity and inventory.

These are synchronized `glFinish` diagnostic costs, **not interactive FPS**.
Inventory/visibility/driver reporting overhead is excluded; sim includes the
read-only activity callback. LAN checksum timing is separate and outside frame
cost; it includes neither sockets nor barrier waits. Do not sum stage summaries
into a promised live frame rate. The short 70-tick window does not establish
sustained combat performance or an owner-approved FPS/resolution target.

One long orchestration command hit the tool's 420-second limit during the second
stress-combat control. Its incomplete directory is retained and excluded. After
verifying no child remained, the complete earlier trials were reused and the
interrupted control plus remaining trials ran serially. No synthetic results
or lowered assertions were substituted.

## 3. Synchronized frame costs

| Scene | Control mean ms | Candidate mean ms | Reduction |
|---|---:|---:|---:|
| stock-distributed | 85.36 | 43.40 | 49.2% |
| stock-combat | 96.39 | 58.61 | 39.2% |
| stress-distributed | 420.91 | 114.56 | 72.8% |
| stress-combat | 550.48 | 340.03 | 38.2% |

| Scene | Median ms, control → candidate | p95 ms, control → candidate | p99 ms, control → candidate |
|---|---:|---:|---:|
| stock-distributed | 84.96 → 43.13 | 89.48 → 45.81 | 93.00 → 47.80 |
| stock-combat | 96.31 → 58.63 | 100.80 → 61.92 | 103.71 → 65.38 |
| stress-distributed | 419.25 → 112.51 | 446.50 → 140.43 | 449.26 → 144.86 |
| stress-combat | 535.53 → 302.26 | 775.98 → 563.74 | 786.00 → 575.15 |

## 4. Stage attribution

Each entry is the median trial-mean milliseconds, control → candidate.

| Scene | Simulation | Camera | World | HUD | Separate LAN checksum |
|---|---:|---:|---:|---:|---:|
| stock-distributed | 26.62 → 21.94 | 8.90 → 1.46 | 36.82 → 14.15 | 12.47 → 5.35 | 8.69 → 8.60 |
| stock-combat | 27.00 → 22.64 | 8.80 → 1.45 | 49.21 → 28.70 | 10.96 → 5.46 | 8.73 → 8.72 |
| stress-distributed | 70.95 → 54.62 | 12.33 → 4.88 | 233.76 → 41.79 | 103.13 → 12.72 | 27.95 → 27.61 |
| stress-combat | 222.46 → 205.06 | 12.29 → 4.78 | 261.79 → 117.25 | 51.99 → 10.61 | 30.80 → 30.68 |

Separate instrumented runs used cProfile around manager step, renderer draw,
HUD composition/upload, HUD GL quad and precise LAN checksum, with overlapping
CPU scopes for camera and world/HUD components. They include warmup and must not
be interpreted as acceptance timings or summed as independent stage costs.

The profiles identify repeated authoritative sensor-range/signature work in
world visibility and minimap construction; repeated model-triangle extrema in
camera collision refresh; and full-fleet sorts while constructing satellite
terrain keys. Hull submission, combat/visibility simulation and canonical LAN
serialization remain material costs after these fixes. No lockstep pacing or
checksum serialization was changed. Stress combat is still far from a normal
interactive budget; these results are headroom, not final scale acceptance.

## 5. Changes retained

1. **Presentation-only sensor batching.** Each synchronous `Renderer.draw` or
   `HUD.render` scope gathers current allied sources lazily per viewer and
   calculates their exact authoritative effective ranges once. It uses the
   original floating-point distance arithmetic, not exploration-grid estimates.
   Nested views share the batch; `finally` restores the previous live-query
   object, including `None`. No visibility answers survive the scope. Simulation
   and input queries remain live under same-tick mutations. Scope contract:
   callers must not mutate sensor sources, modifiers or alliances during drawing.
   The existing render bodies were moved unchanged into private scoped helpers.
2. **Canonical station bounds.** Cache immutable model-space extrema by normalized
   faction/station identity, bounded to 64 keys. Position, yaw, radius, surface
   attachment frame and current faction are still read/applied live. No geometry
   or camera safety box was reduced.
3. **Filter terrain before sorting.** Satellite orbit geometry still scans live
   entities and sorts qualifying terrain by ID with the same exact terrain-key
   tuple. It no longer sorts unrelated ships/stations before discarding them.
   No persistent simulation cache, spacing rule, orbital plan or order changed.

Separate single-sample component controls justified retaining the small changes:
stock camera 9.06 → 1.46 ms and stress camera 12.36 → 4.98 ms with only bounds;
stock sim 26.54 → 22.09 ms and stress sim 73.23 → 56.18 ms with only terrain
filtering. These samples are attribution evidence, not the three-trial combined
acceptance table. Exact state/LAN checks matched in those controls too.

## 6. Determinism, visibility and pixel gates

- All 32 accepted ordinary comparison reports (six full plus two sim per scene)
  agree on precise initial/final state hashes and final precise LAN checksum for
  their identical 70-tick workload. Driver, dimensions, shader and actual MSAA
  assertions passed for every full trial.
- Five scenes have fresh-process **control/control/candidate** frozen-clock
  comparisons: both stock scenes, both stress scenes and the stress flagship
  view. Real renderer `diff_render=True`, fixed `time=0`, 5 warmup +20 measured
  ticks. All three framebuffer SHA256 values match exactly in every scene;
  repeated-same-path controls therefore establish that zero pixel delta is
  meaningful. Precise state and LAN checks also match. No GL depth-readback
  claim is used.
- All 51 exported captures were inspected in contact sheets. No new blank,
  inverted or clipped render was observed. Existing dark/sparse stock combat
  framing, dense shield/marker overlap and modest flagship framing remain;
  these are not approved capital/escort/station art-inspection specimens.
- New regressions cover operation counts, exact fog-surface bytes and visibility
  boundaries, alliances/colonies/discovery/effects, same-tick modifier/source
  changes between presentation scopes, nesting and exceptional restoration,
  serialization invariance, real public scope wiring, exact bounds across
  station families/factions/attachments, normalized cache size and unchanged
  terrain keys under reordering/live mutations. A negative sensor-scope control
  costs 504 multiplier calls instead of the required 12 and fails its test.
- 39 focused visibility/math/new regression tests passed before integration.

## 7. Whole-tree acceptance and safety

The full suite ran serially against the immutable candidate using native Cocoa
before discovery. The scratch runner isolates all five persistence paths per
unsafe fixture and Python child. A native descendant-inherited deny-write
sandbox protects the actual checkout and Application Support data; an audit
barrier adds actionable diagnostics. Self-test passed with its three intentional
rejections. Final full-suite safety: original user data and source preserved,
zero unexpected audit violations, exit zero.

Final result: **1,645 tests run, zero failures, zero errors, nine skips**:
seven native-Windows filesystem tests, one fixture whose ship has shields, and
one Git-checkout-only ignore test (archive has no `.git`). The last test was
separately run in the actual checkout behind the same native protection and
passed without a skip; it is supplemental, not added to the discovery count.

The first completed pre-optimization suite had two failures, retained in the
evidence rather than hidden: benchmark child no-import validation was broken by
the scratch launcher's preimports; the launcher now exempts only that exact
child test while retaining native protection. LAN launch recovery reported host
tick 6 versus 8. Focused ordinary repetitions passed on candidate and pristine
base; controlled scheduling probes reproduced the original test failure names
on both revisions with unchanged LAN test/backend bytes. It is a pre-existing
scheduling vulnerability, not a graphics-fixture fix. No production assertion,
LAN pacing rule or timeout was weakened. Both tests pass in the final whole run.

## 8. Reproduction and remaining gates

From the clean checkout, create an evidence directory and run each accepted
fixture with the existing CLI (omit `--units` for fixed-inventory workloads):

```sh
mkdir -p benchmark-reports
SDL_VIDEODRIVER=cocoa .venv/bin/python main.py --benchmark --fixture four-player-stock-combat-v1 --mode full --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --lan-checksum --output benchmark-reports/stock-combat.json --screenshot benchmark-reports/stock-combat.png
PYTHONPATH=tests .venv/bin/python -m unittest test_presentation_sensor_batch test_station_bounds_cache test_orbit_terrain_scan test_visibility test_detmath -q
```

Use the protected immutable-snapshot procedure, not unsafe unisolated discovery,
for full-suite reproduction on a machine with existing user saves. Evidence
includes the scratch launcher, profile/capture/comparison scripts, source
manifests, raw samples, captures and failed-attempt classification. Its absolute
paths identify this Mac run; adapt roots explicitly on another checkout.

Independent code review and final feature-PR checks are delivery gates recorded
in the PR. No merge, release or tag is authorized by this work.

Remaining roadmap gates: owner-approved sustained workload/FPS/resolution,
actual-renderer capital/escort/station visual slice, future catalogue art,
packaged runtime and native Windows graphics/physical mixed-machine LAN.
Filip’s laptop work remains explicitly deferred. Do not infer it from CI.
