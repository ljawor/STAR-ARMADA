# W05 — world parity: what the window is still missing, and in what order

Status: **plan, backed by a census of both renderers.** No code yet. `main` is `7d68b63` (W04 merged).

The measure of W05 is the one the owner set: *play a skirmish in the new window and not be able to
tell it apart from the old one.* That is a list of things that exist in Python and not in
`render_cpp`.

## 1. The census

| Feature | Python | C++ window today | Notes |
| --- | --- | --- | --- |
| Ships, stations, satellites | `render/renderer.py`, authored meshes | **drawn** (frame instances + bindings) | W01/W02 |
| HUD, text, menus | `render/hud.py`, `menus.py`, SDL_ttf | **drawn** as a composed surface (W03) | menus not exercised over the bridge |
| Input | `render/input.py` | **returns** to the controller (W04) | menus not bridged |
| Planets | `_draw_planets` (renderer.py:1024) — procedural equirect texture per planet type, 512², seeded by name, axial spin, culling, asteroid fields separately | **absent** — `grep -c planet viewer.cpp` = 0 | planets are also excluded from the frame (`dump_snapshot.py:124`, `omitted_features=['planets (W05)', …]`) |
| Planet buildings, shields | `render/planet_building_geometry.py` (253 lines), `_planet_shield_dome` | absent | depends on planets |
| Fog | `render/fog.py` (172 lines, 22 GL calls) | absent (`fog` appears twice, in comments) | visibility *decisions* already come from Python; the raster does not |
| Markers | `render/markers.py` (162 lines) | absent (`marker` = 0) | |
| Hit effects, beams, projectiles | `render/hit_effects.py` (222 lines), effect records in the frame | **drawn**: beams, glows, jump rings, blasts, shield and hull contacts | the renderer's per-spark `GL_LINES` pair has no bgfx equivalent |
| Selection rings, damage states | `renderer.py` ~3900 | absent (`selection` = 0) | |
| Orbits | `renderer.py` orbit paths | absent (`orbit` = 3, comments) | |
| LOD | `renderer.py` | flag exists, no mesh LOD | |

The frame producer is the first thing to change: planets, fog and effects are *omitted by design*
until the window can draw them, and that omission is why the window looks like white triangles over
a starfield.

## 2. Design decision this package inherits

W03 settled the shape: **compose the expensive thing in Python, carry it, draw it natively.** Planets
fit that mould even better than the HUD, because the hard part is the texture, not the geometry:

* `tex.planet_texture(kind, size=512, seed=…)` is procedural, per planet type, seeded from the
  planet's name so a reload does not change the world.
* What is left is a textured sphere with an axial spin, back-face culling and a ring/atmosphere
  shell — a few hundred triangles.

So W05 slice 1 carries **planet textures, not planet surfaces**: a blob ring keyed by
`(data_id, name)` publishes each distinct planet texture once (512² RGBA = 1 MiB, or 256² = 256 KiB
for the first pass), the window keeps them in a texture table, and the frame gains planet instances
with a texture id. A planet that appears twice costs one blob.

This is deliberately *not* a per-frame surface: a planet texture is static for the life of a match,
so the transport is one upload per distinct planet, not per frame.

## 3. Slices, in the order they become visible

1. **Planets — landed, see `docs/RENDER_W05_PLANETS.md`.** No frame change was needed: a planet
   rides as an instance whose binding is `planet:<kind>:<name>` with the radius as scale, and the
   blob ring `ARMPLN01` carries one procedural texture per distinct planet, published once.
   The native sphere pass ports `fleet_materials.py::PLANET` term for term and lights from the
   map's star (`--star`). Reference frame captured from the same fixture, planet and camera with
   `tools/render/capture_python_planet.py`. Not yet: the 1.018× atmosphere shell (effects slice),
   owner rings and background stars (slice 2). Asteroid fields are still omitted and counted.
2. **Markers and selection rings — landed, see `docs/RENDER_W05_CUES.md`.** A primitive batch of
   rings, chevrons and diamonds; the marker's pixel footprint is derived from the window's own
   camera so the icon keeps its 9–15 px size at any zoom.
3. **Effects, beams, projectiles — landed (3a), see `docs/RENDER_W05_EMISSIVE.md`.** Additive native
   pass; beams and glows in world units, bolts in pixels.
   3b. **Explosions — landed, see `docs/RENDER_W05_EXPLOSIONS.md`.** A blast crosses as position,
   size, age and seed and the window rebuilds the layers.
4. **Fog raster — landed, see `docs/RENDER_W05_FOG.md`.** The mask was carried as a texture rather
   than reproduced: it is the classifier's answer, one texel per visibility cell, and the parity
   frame agrees on 1.0000 of the labelled pixels.
5. **Shields — landed, see `docs/RENDER_W05_SHIELDS.md`.** The strength ramp and the fade cross;
   the rim bake and the readability floor are native, drawn as one instanced view-space hemisphere
   per detail level. Four fixture bubbles match the Python reference within 0.41 px, 1.9 % radius,
   1.4 % light.
5b. **Damage contacts (slice 3c) — landed, see `docs/RENDER_W05_CONTACTS.md`.** Shield and hull
   contacts cross as position, normal, size, age and seed; the window rebuilds the cap, the ripples
   and the sparks, seeded from a port of CPython's own Mersenne Twister. Geometry agrees with
   `hit_geometry` to 4.99e-10 on all 600 fixture vertices. The slice also found and fixed two bugs
   in the shared draw path: a chunk loop that asked for one vertex at a time (one draw call per
   vertex, which burned bgfx's 65535 ceiling and silently discarded later passes) and instance
   memory claimed after a large triangle batch. **Planet buildings are still open.**
6. **`--renderer cpp` flag, then the equal-workload benchmark** (200/400/600 ships, HUD, planets, fog)
   before any frame-rate statement is made.

## 4. Gates

* Slice 1 is done when the *same snapshot* rendered by both renderers shows the same planets in the
  same places at the same scale, with the Python side's colour/spin, and the window reports
  `planets.drawn`, `textures.uploaded`, `textures.reused`, `decode_failures`.
* Every slice keeps the rule from W02–W04: Python decides, the window draws. No planet state lives
  only in C++.
* No fps claim until the equal-workload benchmark exists. CI stays disabled by owner instruction;
  local evidence and a pristine-archive test run stand in for a green check.

## 5. First concrete step

`tools/render/dump_snapshot.py` already has the hook: the snapshot lists `omitted_planets`. Slice 1
removes planets from that omission in the *live* producer (`stream_ring.py`) first, because the live
loop is where the owner will play, and leaves the frozen W00 JSON profile alone as agreed.
