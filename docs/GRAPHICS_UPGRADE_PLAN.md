# STAR ARMADA — Graphics upgrade plan

## 1. Approved direction and scope

**Goal: a Homeworld-inspired space RTS, not merely a brighter version of the
current renderer.** Original assets, strong silhouettes, coherent scale,
restrained industrial materials, directional lighting and readable cinematic
combat are required deliverables. Homeworld is an artistic reference, not
permission to copy its models, textures, identity or gameplay.

The owner approved a **hybrid asset workflow**: author the important hull shapes,
station modules and material treatment; use procedural generation for variation,
markings, suitable environment content and effects. No asset purchases initially.
Authoring can use modelling scripts and reusable modules; it does not require
hand-modelling every bolt. Agree a representative visual slice before rebuilding
the whole catalogue. An art-direction label is not approval of every asset design.

Minimum acceptance machines are the owner's Mac and Filip's Windows laptop.
Historical measurements identify an Apple M4 Mac and an Acer Nitro ANV15-52 with
an i9-13900H, Iris Xe and RTX 5060 Laptop GPU (see `PERFORMANCE.md`). Re-record the
actual hardware, active GPU, driver, power configuration and drawable resolution
for each new acceptance run; do not infer current performance from an old report.

### Approved four-player late-game workload

| Component | Per player | Four-player total |
|---|---:|---:|
| Combat ships | 150 | 600 |
| Regular stations, including the command station | 10 | 40 |
| Additional trade stations | 4 | 16 |
| Planets | 2 | 8 |
| Satellites, four on each planet | 8 | 32 |
| Transports, four per trade station | 16 | 64 |

The implemented fixture therefore starts with 760 engine entities, including
eight planet entities (752 non-planet objects). Validate category counts from
the actual fixture, not just an aggregate `ships` flag. Satellites and transports
must not accidentally satisfy the combat-ship quota. Including the command
station within the ten regular stations is an explicit fixture assumption.

The initial versioned mixed fleet uses **906 command points against 78 capacity
per player** with its stock station mix. It is a prebuilt graphics/scale workload,
not proof that this precise fleet is constructible in an ordinary match. No
capacity or balance rules have been changed. Resolve a buildable fleet/station
mix with the owner before calling it representative gameplay acceptance.

"Combat ships" does not silently prescribe 150 supercapital-class hulls. A
versioned, documented catalogue mix is an initial benchmark assumption, not a
new balance rule or an owner-approved final fleet composition. A future change
to that mix requires a new fixture version and new baseline.

### Explicitly not approved yet

- Final target render resolutions and performance thresholds. Proposed discussion
  targets are 60 FPS / 16.67 ms in normal gameplay and at least 30 FPS / 33.33 ms
  in the supported heavy battle. These are **not achieved results or fixed gates**.
- New gameplay, different simulation/tick pacing, an engine switch, lower existing
  MSAA, purchases, or a blanket migration to another graphics context.
- A claim that native Windows gameplay or physical mixed-platform LAN is accepted.

## 2. Architecture and non-negotiables

Follow `ARCHITECTURE.md`: `render/` reads simulation state; `game/core` and systems
remain authoritative. See `DEV_PLAN.md`, `LAN_RECONNECT.md`, `MODERN_GRAPHICS.md`
and `PERFORMANCE.md` for the existing implementation and its acceptance limits.

- **No simulation changes to fund the graphics.** Preserve full-precision state,
  command semantics, the `detmath` tick order, checksums, saves and replay outcomes.
  Benchmark setup may construct a valid initial world, but may not change live
  weapons, health, sensors or economy rules to make measurements look good.
- Preserve fog-of-war across models, VFX, tactical markers, HUD, minimap and picking.
  A benchmark must not turn off detection just to show a larger fleet.
- Preserve 4x MSAA where it is the baseline. Do not silently replace it with FXAA,
  remove passes, or reduce existing quality. Proposed quality trade-offs need
  explicit approval and their own measurements.
- Retain compatibility GL / GLSL 1.20 initially. Probe actual optional features,
  entry points and framebuffer formats on both native drivers. Log fallback reasons.
- Do not promise GPU headroom from CPU-bound evidence: a new pass can create a new
  GPU/fill-rate bottleneck. Profile the current candidate at every milestone.
- One reviewable branch/PR per implementation milestone; never commit to `main`.
  Retain user-owned/uncommitted files and leave the separate prototype tree intact.
- Do not change menus to an unrelated visual family. Retain Clean Classic and its
  existing accessibility/layout contracts; the new world art is not a menu redesign.

## 3. Delivery order and gates

| Milestone | Deliverable | Gate before advancing |
|---|---|---|
| M0 — Scope and baseline | This roadmap and reproducible representative scenes | Exact inventory, deterministic runs, inspected real-GL captures; explicit machine/driver and open gates |
| M1 — Stable geometry | Shared emissive/plating depth-order repair | Intended emitters visible on both draw paths; no unintended geometry/state regression |
| M2 — Measured headroom | Hull/station batching, HUD caching and measured remaining bottleneck work | Whole-scene improvement without silent quality loss; no claim that instancing solves all scaling |
| M3 — Representative visual slice | Capital, escort, station, planet and combat in the intended look | Owner approves tactical/close captures and motion; native Mac/Windows cost measured |
| M4 — Catalogue rollout | Apply approved language to every existing ship and station role | Complete coverage matrix, distinguishable classes/factions and player colours, bounded asset memory |
| M5 — Combat/environment polish | Weapons, shield impacts, damage, explosions, lighting/background integration | Sustained combat stays readable and within agreed frame-time envelope |
| M6 — Equal-quality HDR and delivery | Optional measured HDR/post-FX; packaged platform validation | Actual equal MSAA, clear HUD, state parity and native package/LAN acceptance |

Asset development for M3 can run beside disjoint M1/M2 work, but cannot bypass
M2's integration budget. Core-profile migration is a separate decision, not an
automatic stage. M0 is useful even when it exposes an unacceptable baseline.

## 4. M0 — Representative benchmark and measurement contract

`GRAPHICS_BENCHMARK.md` records the implemented CLI, fixture IDs, exact catalogue
mix, setup assumptions, commands and baseline evidence. Required views are:

1. **Distributed late game:** all four economies and fleets exist, trade traffic
   moves, eight colonies/satellite groups operate, and the ordinary local-player
   fog/visibility rules apply. This measures the whole simulation, not a promise
   that remote hidden units cost GPU time.
2. **Concentrated four-way battle:** all four combat fleets are staged within
   relevant detection/weapon ranges, with the same background economy. Record
   observed visible/firing participants and combat activity, not merely 600 objects
   in the graph. A camera cannot replace a detection/range proof.
3. **Close inspection:** the same representative world, framed around a named
   capital/escort/station group, with appropriate background planet content. Its
   purpose is material/silhouette/readability evaluation, not worst-case throughput.

Use genuine factory-built hulls, commercial routes and orbital satellites, with
stock game rules. Report start and end category counts plus per-sample activity;
casualties are genuine outcomes, not reasons to refill fleets or suppress damage.
Reject an interval that has stopped simulating or become vacuous. Document any
bounded scene limitation, such as absent strategic AI, player input or audio.

### Reproducibility

- Version fixture IDs and retain seed, exact unit mix, commands, tick count,
  initial/final precise state hashes, renderer settings and raw timing samples.
- Measure simulation-only and real SDL/OpenGL modes separately. Retain stage
  mean, median, p95, p99 and maxima; use repeated fresh-process trials rather
  than interpreting one short run as a stable hardware bound.
- Distinguish requested window size, drawable size, actual viewport and capture
  size. Re-measure after fullscreen/resize. Do not mix Retina logical and physical
  pixels when comparing costs or framing.
- Retain actual GPU/driver, shader/fallback state, MSAA and swap interval. A
  requested Windows graphics preference is not proof of the selected GL device.
- Synchronized full-mode `glFinish` timings include CPU/driver/completed-GPU
  durations and remove normal overlap. They are **not interactive gameplay FPS**.
- Measure canonical LAN checksum work separately where supported. A local checksum
  sample is not socket/barrier cost or physical-network pacing acceptance.
- Native gameplay acceptance additionally needs ordinary SDL Clock pacing and a
  mixed Mac/Windows match; the lockstep one-tick-per-frame pipeline stays intact.
- Check renderer read-only behaviour and matching sim/full initial/final hashes.
  For frozen-pixel comparisons, fix the view animation time and retain a repeat
  same-path control. Do not demand identical rasterization across unrelated GPUs.
- A nonuniform screenshot can consist only of sky or HUD. Inspect captures and
  validate subject/combat presence separately before calling a scenario accepted.

M0 introduces no new production visual treatment. Its results are the baseline
against which later milestones are assessed, not a claim of graphics completion.

## 5. M1 — Shared geometry depth ordering

The separate batch prototype found emissive panels effectively coplanar with
trim/plating. Its historical frozen captures differed by 0.98% of pixels on a
frigate close-up and 0.26% in a 40-ship melee; repeated same-path controls reported
zero differences. These are prototype observations, not fresh acceptance runs.

Repair model authoring/building so the intended visible surface is explicit:
use a deliberate exposed emitter or an actual recess/border rather than a depth
tie. `render/fleet_geometry.py:finish()` is a shared candidate choke point, not
permission to offset every surface indiscriminately. Verify signed normal
orientation, shared geometry and near/far camera behaviour before choosing the
margin; do not bury emissive geometry inside an opaque solid.

**Acceptance:** named intended emitters survive on the legacy and new paths,
across close and tactical views and native drivers. Preserve mesh contracts or
update them with justified authored changes. State digests remain unchanged.
A same-driver batch/legacy difference must be explained and localized; an
intended geometry reveal is not permission for arbitrary pixel drift.

## 6. M2 — Headroom before whole-fleet art rollout

### Hull and station batching

Batch by material role and mesh, upload per-instance transforms/colours together,
and avoid duplicate per-entity GL/state-query work in the hot path. Runtime
capability detection and a clearly separated cold fallback are required.

Historical prototype means, M4 / GL 2.1 Metal / 1280x800 / 4x window MSAA:

| Units | Path | World ms | Frame ms | Instanced draws/frame |
|---|---|---:|---:|---:|
| 150 | Legacy | 28.79 | 40.77 | — |
| 150 | Batch | 27.13 | 39.05 | 8.17 |
| 500 | Legacy | 81.87 | 116.86 | — |
| 500 | Batch | 76.19 | 110.78 | 8.40 |

The existing prototype achieves world reductions of 5.8% / 6.9% and frame
reductions of 4.2% / 5.2%. It **does not meet** the earlier proposed gate of
10% world / 5% frame at 150 units. Keep that status explicit; either improve the
implementation or review its value as a measured foundation. Do not silently
lower its gate or claim ship count stops mattering. At 500 units the batch-on
frame mean/median/p95 are 110.78 / 87.51 / 166.50 ms in the saved run; the mean
alone conceals the combat spikes. These figures are not the new mixed-fleet result.

The 7.9x per-call microbenchmark is not a whole-world or whole-frame speedup.
The remaining world cost needs actual pass/CPU profiling: shields, hits,
projectiles, particles, planets, visible-list processing and GL state queries are
candidates, not an already-proven ranking. Optimize only measured bottlenecks.

### HUD caching

Measure software composition, text rendering, serialization, upload and GL draw
separately. Cache static panels and glyphs, allocate texture storage on
creation/resize, coalesce dynamic subimage uploads, and invalidate old **and** new
bounds when a control/text/selection moves. Minimap and resource readouts remain
live; "static top bar" cannot mean stale dynamic values.

**Acceptance:** frozen visual/composite equivalence, live minimap/readouts,
natural click/keyboard/scroll reachability, translated small/large-window layout,
and measured cost reduction. Do not assert that 1440p can come within 10% of
800p from upload changes alone. Retain a full invalidation fallback for uncertain
regions and resize, not an unconditional parallel hot path.

## 7. M3/M4 — Original assets and contemporary material treatment

The required first slice is one capital, escort and station in a scene with a
planet and representative combat. Catalogue entries and faction roles must be
read before selecting specimens; do not invent new gameplay units to fit art.

### Art requirements

- **Silhouette first:** distinct faction languages and class/function cues,
  deliberate hull proportions, major bevels, recesses and engines. A repaint is
  not a new faction geometry design. Ownership paint remains a separate channel.
- **Scale:** fixed comparison framing for scale sheets, plus individually framed
  detail views clearly labelled as such. Window, panel, turret and exhaust scales
  must support the same physical story.
- **Material separation:** exposed metal, paint, glass, recesses and emission have
  deliberate responses, not uniform white highlights and repeated seams everywhere.
- **Lighting:** directional form, restrained ambient fill and bounded occlusion;
  keep shadowed hardware readable without flattening the scene.
- **Original reproducible source:** retain model-generation scripts and/or source
  modelling files, export settings, stable asset IDs, units/axes, material roles
  and derivative texture sources. An exported mesh alone is not a maintainable
  asset pipeline. Record authorship/licensing even when everything is original.

### Performance and platform requirements

Use shared meshes/materials and repeated modules; put major outline changes in
geometry and small seams/vents in suitable baked/normal detail. Prepare measured
screen-size detail levels and check popping/shimmer in motion; changing existing
quality or visibility requires explicit approval. Include mesh/texture memory,
load time, bounds, transparency and draw/material counts in the asset manifest.
Set concrete budgets from M0/M3 measurements, not an arbitrary triangle quota.

Keep material capability separate from context migration. Faction parameters,
procedural masks, atlases and cubemaps can provide useful variation without
requiring texture arrays. PBR describes a shading approach, not a requirement
for deferred shading, compute or a core profile. A modest forward material and
lighting slice should be measured before selecting a broader renderer rewrite.
Normal/roughness maps do nothing useful unless the renderer actually consumes
them correctly; an export format alone is not a rendering implementation.

**Acceptance:** owner-approved actual-renderer tactical and close captures plus
motion, no fog/ownership regression, native Mac/Windows measurements and a complete
catalogue coverage matrix for rollout. No screenshot of a mockup stands in for a
production-renderer result. A cross-faction studio contact sheet must isolate
shape using the same ownership paint and lighting.

## 8. M5 — Combat, damage and environment

Required follow-up, not an optional glow pass:

- Weapon-family-specific launch/travel/impact timing and shapes; readable firing
  direction and localized shield/hull contacts.
- Restrained shields that preserve hull silhouettes and ownership/damage cues;
  avoid a fleet becoming overlapping saturated circles.
- Layered explosions, debris and persistent damage presentation using bounded
  render-only state, private cosmetic randomness and simulation-derived identities.
- Engine/exhaust presentation and a coherent planet/space lighting palette.
- Readable collection/selection/threat cues and consistent HUD integration.

Batch suitable effect geometry and bound cosmetic allocations and transparent
screen coverage. Do not add one dynamic light per projectile or unlimited debris
by default. Preserve important weapon/state information and exact sensor rules;
no reduced gameplay visibility disguised as an effects budget. Measure sustained
combat peaks, not only the idle scene, and keep motion/reduced-motion options.

## 9. M6 — HDR/post-processing, equal quality only

HDR is a presentation investment with a positive frame cost, not a performance
optimization. Preserve crisp HUD and tactical overlays outside cinematic grading.
Use restrained bloom; grain, chromatic aberration and vignette must be separately
optional rather than necessary to hide weak assets.

### Correct the prototype comparison

The prototype `tools/postfx_proto.py` in the separate test tree defines:

- `hdr`: single-sample RGBA16F scene target with FXAA-lite in the composite.
- `msaa`: four-sample RGBA8 scene target with blit resolve.

Its quoted extra costs (+1.54 / +2.15 / +2.55 ms for HDR at 20 / 60 / 150 ships,
1280x800) **do not isolate float-versus-byte format cost**. Window MSAA does not
multisample an unrelated single-sample FBO. The HDR path cannot be adopted as a
preserved-4x-MSAA replacement based on those timings.

Benchmark **RGBA16F + actual 4x scene MSAA + resolve** against **RGBA8 + actual
4x scene MSAA + resolve**, at the same drawable, scene, shader settings and view.
Check FBO completeness and actual samples after create/resize on both drivers.
An alternative FXAA path requires separate explicit quality approval. If the
required float+MSAA path is unavailable, retain the accepted baseline and log it.

### One colour-space contract

Production target: linear scene lighting/emission -> linear bloom extraction,
blur and combination -> exposure/tonemap -> output encoding -> crisp HUD/cues.
Bloom combines **before** tonemapping. Decode/encode around a composed legacy
frame is only a transitional approximation: existing hull/planet shaders apply
custom display transfers, and a float attachment cannot recover values clipped
upstream. Inspect source and intermediate formats before making HDR claims.

**Acceptance:** agreed native-platform whole-frame budget, unchanged state,
legible hull/material detail, measured edge stability and motion, bounded bloom,
no unexplained clipped armour highlights, no HUD tint/blur and correct resize/
restart/cleanup. Intentional emitter saturation is not the same defect as lost
armour detail. The earlier cited station result still had 586 clipped pixels;
it did not satisfy the earlier blanket "zero clipped highlights" criterion.

## 10. Deferred infrastructure decisions

Core-profile migration, additional shadow passes and deferred rendering need
separate bounded prototypes and cost/quality evidence. They are not universally
impossible in compatibility GL, nor automatically valuable. Select the simplest
native cross-platform path that produces the accepted slice within budget.

An engine-port study is not an approved port. `UNREAL_PORT.md`, if present in a
local working tree, is background material; do not make an untracked private
study a prerequisite for executing this roadmap. Duration estimates for a port
are estimates, never "measured" facts.

## 11. Verification and delivery

Run benchmarks, full suites and GL captures sequentially on a settled source
tree. No competing benchmark, second suite or source-mutating sabotage harness.

1. Record source SHA and source-file manifest; never benchmark mutable sibling
   experiments as if they were the candidate. Keep raw evidence and report any
   uncommitted source in the manifest.
2. Run focused fixtures/CLI/lifecycle checks and compile gates. Preserve legacy
   benchmark defaults and serialization/checksum contracts.
3. Compare same-input precise initial/final digests and renderer read-only state.
   For correctness-only renderer changes require controlled pixels; for intended
   look changes inspect localized deltas rather than requiring the old appearance.
4. Inspect exported tactical and close captures yourself, plus short motion clips
   for material shimmer, AA, effect timing and LOD transition acceptance.
5. Run the protected whole-tree suite before release/integration acceptance. Test
   fixtures must not write real settings, balance, campaign, saves or replays.
   Compare failure **name sets** against an actually executed pristine baseline;
   classify an isolated failure before labelling it pre-existing/environmental.
6. Native Windows GL/runtime and packaging are separate from headless Windows
   LAN tests. A job using SDL dummy video proves no graphics-driver acceptance.
7. Verify the exact pushed PR head and current checks. Do not merge/tag/release
   until separately authorized and the relevant gates are satisfied.

### Retained diagnostic lessons

- Some tests set SDL dummy video at import. Real-GL suites need an explicit native
  driver; the Mac command is `SDL_VIDEODRIVER=cocoa`. Do not export Cocoa on Windows.
  Isolate module/subprocess driver selection properly rather than weaken tests.
- The historical M4 depth-readback probes returned constant 1.0 even with a real
  depth buffer. Use colour controls and geometric analysis for that driver's
  depth-tie investigation; do not generalize a broken probe to every GPU.
- Freeze animation, use the same role/pass isolation on both sides, and inspect
  the case's own result block. Aggregate pixel-difference percentage does not
  establish visibility; location and amplitude matter.
- Fullscreen shaders output clip space. A 0..1 vertex quad must be explicitly
  mapped to -1..1; otherwise it paints one quadrant and leaves stale pixels.
- Per-pass forced synchronization changes overlap. Do not sum diagnostic pass
  stalls and present that as the normal added frame cost.

## 12. Historical prototype location and status

`~/Downloads/Project/STAR-ARMADA-TEST` is the separate uncommitted batch/post-FX
prototype. Its saved `artifacts/fleet_batch/` JSONs and README supply the historical
batch means in section 6; `artifacts/showcase/` and `artifacts/postfx/` hold its
look and post-FX evidence. This is not tracked production implementation.

Tools such as `bench_fleet_batch.py`, `parity_fleet_batch.py`, `probe_plate_depth.py`
and `postfx_proto.py` are not shipped merely because the old plan named them.
Prototype-tree commands are not clean-checkout commands. Relevant harnesses must
be committed with their implementation milestone before its results are accepted.

This roadmap and the representative benchmark begin M0. M1–M6 remain pending;
no substantial new graphics treatment, accepted frame budget or native Windows
visual result is implied by this document.
