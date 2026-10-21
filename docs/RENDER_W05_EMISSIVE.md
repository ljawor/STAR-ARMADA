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

* **Explosions are not carried.** `_draw_explosion` builds a per-effect particle sequence from a
  seed; it needs its own vocabulary (or a great many discs), so it is slice 3b.
* **Shield hits, hull hits and the standing shield shell** are still drawn by nobody in the native
  window.
* **Legacy point-sprite projectiles** (`projectile_shape(...) == 'legacy'`) are counted
  (`legacy_shots` in the producer report) and not drawn.
* The counters in the viewer report are **cumulative over frames drawn**, not per frame: a batch
  that is redrawn for 500 frames counts 500 times.
* No frame-rate claim: the equal-workload benchmark is still slice 6, and this pass adds draw
  calls to a scene that has never been measured under equal work.
