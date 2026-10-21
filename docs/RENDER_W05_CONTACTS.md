# W05 slice 3c — damage contacts on shells and hulls

Small, damage-resolved contacts: a geodesic cap crawling on a standing shield with two ripples, or a
warm flash with a little smoke and seeded metal sparks on bare hull. They are not explosions, not
opaque billboards, and they last half a second. Source of truth is
`render/hit_effects.py` (`hit_geometry`, `draw_hit`).

## What crosses

A contact is a parameter record, like a blast: position, normal, size, age and seed. The ~90
triangles of curved shell and sparks are rebuilt in the window. Everything that is a decision stays
in Python — which contacts exist, how big the damage system made them, how old they are, the
renderer's cool/warm colours, the ripple timing and the spark seeds.

| field | shield contact | hull contact |
| --- | --- | --- |
| `kind` B | `SHIELD_HIT = 7` | `HULL_HIT = 8` |
| `shape` B | the effect's size in tenths (2..18 → 20..180) | `0` (camera-facing flash) |
| `flags` H | bit2 `FLAG_VISUAL_CONTACT` when the simulation resolved the contact visually | same |
| `colour` | unused (the renderer derives cool/warm) | unused |
| `a` 3f | **shell centre** | contact point |
| `b` 3f | outward normal | outward normal |
| `radius` f | shell radius | effect size |
| `width` f | age in seconds | age in seconds |
| `segments` H | seed | seed |

No new ring and no record growth: both kinds ride the existing 44-byte emissive record
(`ARMEMIT1`), beside ribbons, discs, rings, bolts, explosions and standing shells.

Why the size crosses in the `shape` byte for a shell contact: the cap's aperture is
`min(.19, max(.055, size/radius))`, so the window cannot derive the contact's angular width from the
shell radius alone. A hull contact carries its size in `radius` because that is the only number its
geometry uses.

## What stays native

Two numbers need the camera, and both are pixel floors that the renderer also applies with its own
`px_per_world`:

* a shield contact is aligned with `SHIELD_MIN_PX` (74 px across, `renderer.py:46`), so a distant
  contact still sits on the bubble the player can see;
* a hull contact keeps a 7 px floor and is capped at the effect's own size, because at tactical zoom
  a physically sized spark falls entirely between pixel centres.

The detail of the cap (12 segments, two ripples of 16) and every alpha envelope are the renderer's
constants, ported term for term:

| quantity | value |
| --- | --- |
| lifetime | 0.55 s shield, 0.42 s hull |
| fade | `(1 - t/life)^1.7` |
| cap alpha | `0.20 * fade * exp(-t*12)` |
| ripples | delays `0` and `0.085`, `theta = min(.42, aperture*.65 + age*.9)`, strength `0.26*fade*(1-age/.6)` |
| hull flash | `exp(-t*32)*fade`, radius `size*.32*(1+.18*sin(5φ+seed))` |
| smoke | from 25 ms, radius `size*(.10+t*.24)`, `(0.11,0.12,0.14)` at `0.10*fade` |
| sparks | 9 fragments (5 on a shield), travel `size*(.08 + t*2.5|4.0*speed)` |

The sparks come from Python's `random.Random(seed)`. The window has a port of CPython's Mersenne
Twister with the same seeding path (`init_by_array` for an int seed), not a lookalike hash, so a seed
produces the same flecks on both sides — `render_cpp/tests/test_hit.cpp` pins the first four draws
and the first and last fragment for seeds 0, 7, 11 and 65535 against numbers printed by CPython.

Blending is alpha, with no depth test and no depth write: a contact is a surface marking whose
contact radius is an approximation, so Python composes it above opaque armour, and the window does
the same. Smoke rides its own submission before the triangles because a dark mass may not be drawn
additively.

One thing does **not** cross: the renderer also emits a one-pixel `GL_LINES` pair per spark. bgfx has
no line primitive; the tapered ribbon under each line is the part with real raster coverage, and the
comment in `hit_effects.py` says so. The line is the only omission in this slice.

## Parity

Two measurements, both from committed artefacts.

**Geometry, vertex for vertex** (`tools/render/compare_hit_geometry.py`, `artifacts/cpp-renderer/w05/contact-geometry.json`):
the fixture batch is decoded by the real decoder, rebuilt by `appendHit` at `px_per_world = 1.54` and
compared with `hit_geometry` fed the same records and the same camera basis.

| quantity | Python | native |
| --- | --- | --- |
| contact triangles | 528 vertices | 528 vertices |
| smoke triangles | 72 vertices | 72 vertices |
| structural mismatches | 0 | 0 |
| worst component delta | — | **4.99e-10** (the dumper prints nine decimals) |

That is the port, exactly: positions, colours and alphas agree to print precision.

**Live frame, contacts present and absent** (`artifacts/cpp-renderer/w05/contacts-live.png` vs
`contacts-live-control.png`): one real skirmish batch (337 contacts, 622 shells, beams), read from a
live `emit.ring`, published twice — as decoded, and with the contact records removed. Same camera,
same scene, same frame count.

| frame | lit pixels below the HUD (threshold 0.004 over background) | notes |
| --- | --- | --- |
| with contacts | 267,120 | 337 contact marks |
| without contacts | 267,120 | the same fleet and shells |
| where they differ (threshold 0.02) | **3,902 px** | ~11 px per contact |

The lit-pixel count is identical to the pixel: a contact's marks are brighter than the threshold
*inside* pixels that the shield bubbles already lit, so the coarse count cannot see them and the
difference image is what shows the 3,902 pixels they add.

`artifacts/cpp-renderer/w05/contacts-ab.png` is that difference at 6× on one ship: a pale cool fleck
on the nose of the hull.

A pixel A/B of the two *renderers* is **not** offered for this slice and the reason is on record: the
window's projection is handed degrees where `bx::mtxProj` wants radians (`docs/RENDER_W05_PLANES.md`, audit still owed), so its apparent field of view is far wider and it will not frame a target at the
pitch the reference camera uses. Contacts are a few pixels wide, so that framing difference, not the
port, would dominate any pixel comparison. The floors are in pixels on both sides, so once the
projection is corrected the contacts should land at the same size on screen.

## Two bugs this slice found in the shared draw path

**One draw call per vertex.** `submitEmissive` asked
`bgfx::getAvailTransientVertexBuffer(1, cueLayout)`. That function returns `min(available, requested)`,
so asking for one vertex returns exactly one, and the chunk loop issued a draw call per vertex. It
never mattered while the largest batch was a few hundred vertices; a frame with 337 contacts holds
~75k, which burned bgfx's 65535 draw-call ceiling. Every draw after that point was **silently
discarded** — no failed call, no dropped-vertex count — and the standing shield shells vanished from
the frame while the report still said `622 shells, dropped_vertices 0`. Fixed by asking for the
number of vertices still wanted. The symptom is worth remembering: a scene that loses whole passes
with a clean report is a draw-call budget problem, not a geometry problem.

**Instance memory is claimed in allocation order.** Transient vertex and instance memory come out of
one per-frame pool. A large triangle batch allocated before the instanced shell draws can leave them
with nothing, so the shells are now allocated first and submitted last: memory timing and Python's
layering (`_draw_effects` at `renderer.py:502` before `_draw_shields` at `:510`) agree.

## Commands

```bash
# regenerate the fixture (blob for the decoder tests, ring for the viewer)
PYTHONPATH=. .venv/bin/python tools/render/write_hit_fixtures.py --out DIR
# the window's geometry vs Python's, vertex for vertex
PYTHONPATH=. .venv/bin/python tools/render/compare_hit_geometry.py \
    --batch render_cpp/tests/fixtures/hit/hits.bin \
    --dumper render_cpp/build-w02/dump_hit_geometry
# the Python reference frame (the real draw_hit, everything else skipped)
PYTHONPATH=. .venv/bin/python tools/render/capture_python_hits.py --out DIR
```

Tests: `tests/test_render_emissive.py::ContactTests` (9 cases) and
`render_cpp/tests/test_hit.cpp` (RNG parity, shell cap on the sphere, flash/smoke counts, fade
monotonicity, the 7 px floor and the visual-contact cap). The render suite stands at 161 Python tests
and `ctest` 11/11.
