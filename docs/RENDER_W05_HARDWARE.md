# W05 slice 3e — surface hardware crosses as a mesh

A planet building is the first thing in the world the window cannot look up. Its binding is
`<faction>:<kind>`, and neither catalogue it owns can name it: the offline snapshot lists the 18
assets of the entities that were on the map when it was taken, and `assets/models/registry.json`
holds 119 bindings of which none mentions a planet. A building is added during a match, so a
window that only reads catalogues can never draw one.

The silhouette is therefore the part that has to travel. What travels with it is a transform the
window is not allowed to reconstruct.

## What crosses

`render_bridge/hardware.py` — `ARMHWR01`, one blob per binding, published once:

```
u8[8] magic "ARMHWR01" | u16 version | u16 name length | u16 triangles
u16 role blocks | u32 crc32 | name (utf-8)
per block: u8 role | u16 count | count * (normal xyz, 3 vertices xyz) as float32
```

* **Role colours are not on the wire.** `base`, `dark`, `trim`, `accent`, `lit` and `cool` have
  meant the same material on both sides since W01; a colour field would be a second copy of a
  decision that already has an owner.
* **Refuse-whole.** A mesh that decodes to a plausible but wrong shape renders as a building
  nobody can attribute, so a bad magic, version, count, crc, length or non-finite coordinate
  rejects the whole blob. `tests/test_render_hardware.py` (17 tests) and `test_hardware` both
  refuse the same malformed variants.
* The blob is the same encode the renderer's own mesh comes from:
  `render.asset_selection.mesh_for`, the call `fleet_geometry.station_mesh` makes.

## What stays in Python

* **Whether a building exists, where, and which binding** — `render_bridge/collect.py` reads
  `planet_id` and `planet_building_slot`; a hull without both is not surface hardware.
* **The basis.** `FLAG_SURFACE_FRAME` (`1 << 3`, `render_bridge/packed.py`) says the 12-float
  matrix is a **full basis, not a heading plus a uniform scale**: a building stands on the
  foundation the site generator chose, which no yaw can describe. The window copies it verbatim
  and does not interpolate it — a building does not move, so there is nothing to interpolate.
* **The scale** — `entity.radius / 50`, applied to the columns exactly as `station_frame` does.
* **The session table** reserves a binding for every `BUILDING_TYPES` kind per faction, so a
  building created in the middle of a match does not need a table revision to appear.

## Native side

`render_cpp/include/hardware.hpp` decodes into the window's own `Mesh`, expanding each triangle
corner the way `load_mesh` does, and maps the role index onto the shared palette. `viewer.cpp`
drains `--mesh-ring` once per frame, uploads a vertex buffer per binding, and submits the
buildings of the current frame as one instanced draw per binding — shadow pass included, because
a building casts a shadow like any other solid.

The frame record is not extended: a surface building is an ordinary instance with one flag set.

## Measured

| Measure | Value |
|---|---|
| Vertices, Python mesh vs C++ decode | **7,500 both sides, 0 mismatches**, worst delta **5.0e-07** (float32) |
| Triangles | 2,500 (authored extractor), 6 roles |
| Live frames | 16 bindings published, **0 decode failures**, 50 instances drawn, **0 dropped**, **0 unmeshed** |
| Control run (building removed, planet left in place) | **0 instances drawn** |
| Refusals | short blob, foreign magic, flipped byte, truncated payload, bad role index |

`tools/render/compare_hardware_geometry.py` diffs the rebuilds through `test_hardware --dump`, so
the comparison runs against the same decoder the viewer uses rather than a second reader written
for the test.

## Two bugs this slice found

1. **The basis was hoisted out of the entity loop.** `surface = None` sat above the loop, so the
   first building's foundation was inherited by every entity after it in id order. Those entities
   took a building binding the session table has no mesh for, the collector skipped them, and
   **they vanished from the frame** — a fleet disappearing because one planet had a refinery.
   `tests/test_render_packed.py::SurfaceHardwareTest::test_a_hull_after_a_building_is_not_surface_hardware`
   asserts on the hull that follows the building; restore the hoist and it fails with
   `hull 26 disappeared from the frame`.
2. **`plant()` left `is_ship` set.** A relabelled hull was claimed by the ship pass as well as the
   station pass, and the ship pass crashed on `ship_size()` returning `None`. A building is not a
   hull; the flag is cleared.

## Honest wrinkles

* **No pixel parity is claimed for this slice.** The geometry is byte-identical and the transform
  is exact, but the two cameras do not agree: `bx::mtxProj` takes radians where it is handed
  degrees, so the window's effective vertical FOV is ~88° against the renderer's 55°, and the
  pitch/azimuth conventions differ too. The A/B sheet (`hardware-ab.png`) is therefore for the eye,
  not a metric. This is the outstanding projection audit at `viewer.cpp:1246`, and it blocks any
  framing or fps comparison, not just this one.
* **The Python reference has to narrow the frame cache.** `_draw_ships` owns both the hulls and
  the stations, so skipping it for a station-only reference skips the building; the tool narrows
  the visible list to the building instead and keeps the pass's lighting and material state.
* **The skirmish map has no colonies**, so the building is planted by
  `tools/render/hardware_scene.py` — labelled synthetic everywhere it is used. The path it
  exercises (fields, binding, basis, mesh) is the path a paid building takes.

## Files

| Path | What it does |
|---|---|
| `render_bridge/hardware.py` | `ARMHWR01` encode/decode, refuse-whole |
| `render_bridge/packed.py` | `FLAG_SURFACE_FRAME` |
| `render_bridge/collect.py` | binding reservation, surface basis per entity |
| `render_cpp/include/hardware.hpp` | decoder, role → palette |
| `render_cpp/src/viewer.cpp` | `--mesh-ring`, upload, instanced submit, `hardware` report |
| `tools/render/hardware_scene.py` | the planted building, its camera, the catalogue walk |
| `tools/render/write_hardware_fixtures.py` | publish the catalogue as blobs + ring |
| `tools/render/capture_python_hardware.py` | Python reference, building present and absent |
| `tools/render/compare_hardware_geometry.py` | vertices, Python vs C++ |
| `tools/render/hardware_ab.py` | the A/B sheet |
| `tools/render/stream_ring.py` | `--plant-building`, `--hide-building`, `--mesh-ring` |
