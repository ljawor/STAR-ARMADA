# W05 slice 3b — detonations, rebuilt from parameters

Status: **landed on `render/cpp-w05-parity` (PR #150).** Supersedes the "explosions are not carried
yet" line in `docs/RENDER_W05_EMISSIVE.md`.

## The shape of the transport

A blast is not sent as geometry. `render/renderer.py::_draw_explosion` derives the whole event from
two numbers — how old it is (`t`, against a 1.5 s life) and a `seed` — plus its position and size. So
those four values cross as one ordinary `ARMEMIT1` record of kind `EXPLOSION 5`:

| field | meaning |
| --- | --- |
| `a` | the centre, world space |
| `radius` | the blast's size (what the simulation recorded on the effect) |
| `width` | seconds since the blast started — **not** a 0..1 fraction |
| `segments` | the seed the shape comes from |

The window then rebuilds the layers with the renderer's own formulas
(`render_cpp/include/explosion.hpp`). If the geometry crossed instead, one station-scale blast would
be ~2,100 vertices and ~950 triangles *per frame* — more than the frame ring itself — for one effect.

`explosion_small` is the same phenomenon, not a second one: half size, 0.55× the clock, its own 0.6 s
fade, seed 3, exactly as the renderer draws it. Both become the same record with different numbers.

## What the port keeps, because losing it changes what you see

* **`fxRing` reproduces the lumpy silhouette** (radius harmonics) *and* the deliberately subtle
  0.84..1.0 per-angle brightness jitter. A stronger jitter renders as radial spokes.
* **`glowRing` draws one quad strip per band with exactly two vertices per angle.** With three
  vertices per angle a strip pairs `outer(i)` with `inner(i+1)`, which draws a full-width radial quad
  per segment — a pinwheel of dark spokes instead of a shell.
* **A fan gets ONE shared centre vertex.** Per-angle centre copies each carry that angle's jitter, so
  neighbouring wedges disagree in the middle and the puff reads as a pinwheel.
* **The shock front ends on a nearly transparent outer vertex.** A bright outer edge is a crisp
  contour, and a crisp contour at this size reads as a drawn donut.
* **Smoke blends normally, everything else adds light.** A dark puff drawn additively is not smoke.

## Evidence

Reference: `tools/render/capture_python_explosion.py` renders one synthetic blast in open space
(age 0.35 s of a 1.5 s life, size 120, seed 7) with the fog test and overlay disabled, and records
the picture plus its mean RGB. Native: the same numbers through `--fx-demo 120,0.35,7`.

| measure | Python | native |
| --- | --- | --- |
| additive energy over background | 97,371 | 69,608 |
| lit pixels (>0.2) | 72,298 | 51,407 |
| **energy per lit pixel** | **1.347** | **1.354** |
| pixels above 0.5 | 24,409 | 21,135 |
| span (px) | 751 × 488 | 719 × 352 |

Same brightness density; the difference in totals is coverage (the smoke drift is narrower), not
exposure. Frames: `artifacts/cpp-renderer/w05/detonation-python-reference.png` and
`detonation-native.png`.

Layer census at that age, from instrumenting both sides: Python makes 37 glow-ring calls (7 fireball
shells, mid, core, 9 smoke puffs, 18 embers, 1 secondary) with an alpha sum of 13.116; the port makes
36 with 12.480 — the missing one is the secondary pop, which only exists during its 0.24 s window and
depends on the same seed arithmetic.

## Two defects found while getting the picture to match

1. **clang 16 at `-O3` miscompiled the unrolled shell loops.** Every fireball shell came out at the
   world origin with a sixteenth of its radius; `-O2`, `-O0` and `-fno-unroll-loops` were all correct.
   This was the real cause of a blast that looked dim and lobed — not the layer maths. The four
   fixed-count emit loops keep `#pragma clang loop unroll(disable)`, and
   `render_cpp/tests/test_explosion.cpp` ("no vertex escapes the blast", "the blast keeps its size")
   fails at the project's own `-O3` settings if it ever regresses.
2. **`BGFX_STATE_BLEND_ADD` is `(ONE, ONE)`** — vertex alpha is ignored, so every faint shell landed
   at full brightness and the fireball rendered as a solid white plate. Additive blending that honours
   alpha is `BGFX_STATE_BLEND_FUNC(SRC_ALPHA, ONE)`; a single `--fx-demo disc:SIZE,ALPHA` probe reads
   back the requested alpha exactly, which is how this was confirmed rather than guessed.

## Deliberate units split (unchanged from slice 3a)

Everything that decides *what* happens is Python's: whether a blast is alive, where, how big, which
seed, and when a small blast has faded. The window only rebuilds geometry, in world units, from the
values it is given.

## Not carried

* `shield_hit` / `hull_hit` / `impact` flashes and the standing shield shell (slice 3c).
* Legacy point-sprite projectiles (counted, not drawn).
* The 1.018× additive atmosphere shell and background stars.

## Known caveat that affects every framing

`bx::mtxProj` takes the vertical FOV in **radians**; the viewer hands it degrees, so the effective
vertical FOV is ~88° instead of 55° and everything draws at about 54% of Python's apparent size at the
same distance. Feeding `bx::toRad()` empties the frame, because the rest of the view setup is built on
the current matrix — so correcting it means re-baselining every framing and benchmark. Measured, not
modelled: to compare a native frame against a Python one at distance `d`, use about `1.36 × d`
(830 matched 660 to within 4% of width).
