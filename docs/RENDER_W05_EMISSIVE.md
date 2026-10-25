# W05 slice 3a — weapon fire, beams, glows and jump rings

The window now draws the emissive layer: bolt tracers, beam ribbons, muzzle and impact glows, jump
rings and fire glows. As with W02–W05 so far, the game decides and the window draws — but this
slice carries two different *units* on purpose, and the reason matters.

## What travels, what does not

| Cue | Decided in Python | Drawn by the window |
| --- | --- | --- |
| Which projectiles/effects are live | the fog predicates (`is_position_visible`, `effect_visible`), evaluated in the renderer and passed as id sets | — |
| Beam layering | three ribbons — a wide soft sheath at 9 world units, a bright one at 3, a hot core at 1.2 — with each layer's own tint and alpha, fading over 0.25 s | the quads, built camera-facing from the axis and the eye vector |
| Glows | radius (14 at the muzzle, 8 at impact), colour, alpha, and whether the impact glow exists at all (`resolved_contact`) | the fan, hot centre to transparent rim |
| Jump rings | radius growth `60 + 160 × (1 − alpha)` over 1 s, stroke half-width 2.5 | the ring quads |
| Bolts | the shape (elongated along the heading, or square), the **pixel** extents from `projectile_extents`, the halo and core alphas, the whitening of the core | the world size, converted at *its own* camera depth |

**Two units.** A beam's width is a world size: capital-ship fire should thicken as you zoom in. A
bolt's extents are pixels: the Python renderer derives them from `px_per_world` at its own camera,
and in live mode the window owns the camera, so it converts the same pixel extents at its own
depth. Carrying world units for bolts would make a volley grow and shrink as the player zoomed.

## Format (`render_bridge/emissive.py`)

```
header  <8sHHII         20 B   magic "ARMEMIT1", version 1, count (<=4096), reserved, crc32
record  <BBH4B3f3fffHH  44 B   kind, shape, flags, rgba, a xyz, b xyz, radius, width,
                               segments, reserved
```

* kinds: `RIBBON 1`, `DISC 2`, `RING 3`, `BOLT 4`.
* `a`/`b` are the ribbon endpoints, the disc/ring centre, or the bolt position and heading.
* `radius` is a world radius for discs and rings, and a half-length in **pixels** for a bolt;
  `width` is a world half-width for ribbons and rings, a pixel half-width for a bolt.
* Everything is additive (`BGFX_STATE_BLEND_ADD`) with no depth write, matching the renderer's
  `glBlendFunc(GL_SRC_ALPHA, GL_ONE)` and `glDepthMask(False)` for effects.

## Evidence

* `tests/test_render_emissive.py` — 11 tests: byte-identical round trip, five damaged batches
  refused, the 4096 ceiling, a beam being three ribbons plus two glows with the renderer's widths
  and a lifted core, alpha fading with age and the beam expiring at 0.25 s, `resolved_contact`
  dropping the impact glow, a jump ring growing as it fades (60 → 220 world units), and bolts
  carrying *pixel* extents with the heading (or the square shape) intact.
* Live, `four-player-combat-v1`, four-way melee at 1200 units: **12 emit batches, 0 decode
  failures, 0 dropped vertices**, ~2,700 primitives and ~5,800 triangles per frame; the window
  shows white-hot bolt cores with their haloes over the fleet
  (`artifacts/cpp-renderer/w05/emit.png`).

## Known gaps (not claims)

* ~~**Explosions are not carried.**~~ **Done in slice 3b** — see `docs/RENDER_W05_EXPLOSIONS.md`.
  A blast crosses as position/size/age/seed in the existing `EXPLOSION 5` record and the window
  rebuilds `_draw_explosion`'s layers from its own formulas.
* **Shield hits, hull hits and the standing shield shell** are still drawn by nobody in the native
  window (slice 3c).
* **Legacy point-sprite projectiles** (`projectile_shape(...) == 'legacy'`) are counted
  (`legacy_shots` in the producer report) and not drawn.
* The counters in the viewer report are **cumulative over frames drawn**, not per frame: a batch
  that is redrawn for 500 frames counts 500 times.
* No frame-rate claim: the equal-workload benchmark is still slice 6, and this pass adds draw
  calls to a scene that has never been measured under equal work.

## 1. Combat presentation amendment — world-axis flight

The preceding sections describe the original W05 implementation. The combat presentation pass
supersedes its pixel-sized **live** bolts, not its historical wire fixtures:

- `FLIGHT = 9` carries the actual head in `a`, full world velocity in `b`, world half-length in
  `radius` and world half-width in `width`. `shape` is laser 0, missile 1 or torpedo 2. One record
  replaces the old pair of screen-facing halo/core rectangles. The existing header/version and
  44-byte layout remain unchanged; an old consumer refuses unknown kind 9, so rebuild it.
- Flags are depth-test plus additive (3), without depth writes; `segments` is reserved zero.
  Position, velocity and extents must be finite and bounded in magnitude by 1e8; dimensions and
  speed must be positive. Both codecs enforce the new kind's contract.
- Laser cores and their soft glow follow the world trajectory. Guided shots have a pointed body,
  an engine core and a tapering exhaust (warm for missiles, cooler/longer for torpedoes).
  Exhaust follows the current velocity, **not** a fabricated curved history. The renderer does not
  change or infer a target, muzzle, turn rate, accuracy, damage or projectile speed. All-round
  capital mounts still use the simulation's existing single nose muzzle: correcting their physical
  launch positions is a separate gameplay-bound change, not something this projection fix proves.
- All long-axis vertices stay behind the physical head. Perspective, including the depth component
  of velocity, determines the projected angle. End-on flight becomes a small glow, not an invented
  horizontal streak. A **1.2-pixel full-width** readability floor prevents the core vanishing into
  MSAA; length and plume length are world-sized and never enlarged to a pixel-length floor.
- The historical `BOLT = 4` decoder and fixed-pixel fixture behavior remain supported. The legacy
  Python/OpenGL projectile renderer is unchanged by this native-renderer pass.

Verification commands (run native workloads serially and under process-group deadlines):

```sh
SDL_VIDEODRIVER=cocoa PYTHONPATH=tests .venv/bin/python -m unittest test_combat_presentation test_render_emissive test_render_frame_pacing test_projectile_aim test_detmath
cmake --build render_cpp/build-w02 -j8
ctest --test-dir render_cpp/build-w02 --output-on-failure
.venv/bin/python tools/render/verify_combat_fire.py --out <new-evidence-directory>
.venv/bin/python tools/render/capture_native_combat.py --out <new-battle-directory> --distance 1600 --frames 360
```

`verify_combat_fire.py` runs isolated production-producer/native-consumer shots, background-subtracts
real Metal/D3D pixels, requires nonempty subjects, checks visible length scaling across a 4x camera
distance change and compares the off-axis streak with the exact perspective derivative. The
unchanged baseline measured zoom ratios 1/1/1 and a 27.63-degree off-axis error; that fails the same
bars. Initial candidate attempts whose MSAA coverage lost too much of the distant tail are retained
as failed attempts, not counted as passes. The final soft-sided streak keeps a readable body before
its tapered end rather than a single bright midpoint.

`capture_native_combat.py` runs the real `main.py` initialization, commands, simulation and embedded
native presentation with a small stock-weapon fleet fixture, isolated user paths and hidden display.
Its receipt lists each frame's simulation tick/hash, live weapon types and hull+shield total, and
asserts real fire, damage, state-neutral presentation and worker cleanup. The fixture uses spawned
fleets, not a claim of paid construction or stock fleet-cap eligibility. Pixel probes and macOS
clips are not Windows runtime acceptance, full-suite acceptance or owner appearance approval.
