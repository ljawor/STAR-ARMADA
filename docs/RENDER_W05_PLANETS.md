# W05 slice 1 — planets

The native window used to draw nothing where a planet was. It now draws the planet the Python
renderer draws: the same procedural surface, the same radius, the same axial spin, and the same
shading maths, lit from the same star.

W05's measure is the owner's: *play a skirmish in the new window and not be able to tell it apart.*
So the evidence here is a pair of pictures of the same planet in the same world, plus the numbers
that say nothing was silently dropped.

## What travels, and what does not

A planet in `render/renderer.py` is a textured sphere. The expensive, interesting half is the
texture: `render/textures.py::planet_texture` builds a procedural equirectangular surface seeded
from the planet's *name*, so a reload cannot change the world. The other half is a sphere — a few
hundred triangles on the far side.

So the bridge carries **textures**, not planet surfaces:

| Item | Where it comes from | Crosses the bridge | Frequency |
| --- | --- | --- | --- |
| Surface texture | `render/textures.planet_texture`, seeded by `blake2s(name)` | one `ARMPLN01` blob per distinct planet | once per match |
| Position, radius | the frame's instance record | packed frame instance, as before | every frame |
| Axial spin | the viewer's clock, 0.48 rad/s (`kPlanetSpinRadPerSecond`, 60% slower than the Python renderer's 1.2) | not carried | per frame |
| Lighting | the map's star position | `--star x,y,z`, default `0,2000,0` | once |

A planet therefore needs **no frame-format change**: it rides as an instance whose binding names
the texture (`planet:<kind>:<name>`) and whose scale is the planet's radius. Asteroid fields are
still omitted (`omitted` is counted, not hidden) because they are drawn as rocks, not a sphere.

## The blob format (`ARMPLN01`)

```
offset  size  field
0       8     magic "ARMPLN01"
8       2     version (1)
10      2     width in pixels   (1..2048)
12      2     height in pixels  (1..2048)
14      2     name length       (1..128)
16      4     crc32 over name + pixels
20      n     name, UTF-8
20+n    4*w*h RGBA pixels, top row first
```

`render_bridge/planets.py` encodes; `render_cpp/include/planets.hpp` decodes; the native decoder
refuses the whole blob on any failed check — a half-decoded texture paints a corrupt planet, which
is much harder to attribute than a refusal. `planetKind` / `planetTextureName` parse the binding;
the name is everything after the **last** colon, because the middle field is the planet kind
(`temperate`, `industrial`, …), not an asset id.

## The native draw

* One unit sphere, 48 × 24 segments (1,225 vertices, 2,304 triangles), built once.
* Textures live in a table keyed by name; a body whose texture has not arrived yet draws with a
  grey 1×1 fallback and increments `untextured_bodies` — counted, never silently dropped.
* One submit per body, each rebinding geometry and state: bgfx clears the draw state after every
  submit, so a loop that binds once and submits eight times draws once.
* The body matrix is built through `bridge::write_instance`, the same helper the fleet's 638
  instances use. `bx::mtxMul` multiplies in the opposite order from what its name suggests — it
  produced a translation of `radius × distance` (1,890,000 instead of 1,400) and the planet was
  silently off-screen. The proven path is now the only path.
* `--focus x,y,z` aims the orbit camera at a world point; a planet sits tens of thousands of units
  out, so any comparison against the Python renderer needs it.

### Shading is a port, not a re-invention

`render_cpp/shaders/fs_planet.sc` reproduces `render/fleet_materials.py::PLANET` term for term:
ambient `(0.025, 0.035, 0.065)`, a `smoothstep(-0.10, 0.85, N·L)` terminator, the ocean highlight
(`smoothstep(0.02, 0.12, b - r)`, specular exponent 70), the atmosphere rim
`(0.19, 0.48, 1.0) × pow(1 - N·V, 3.8)`, and the `pow(…, 0.88)` display transfer. `L` points at the
map's star, as `GL_LIGHT0` does in `render/renderer.py` (y raised to at least 2000 so a system in
the ecliptic still has a day side).

Two renderers that light a planet differently are two different worlds, and the owner's measure is
that a player cannot tell them apart — so the maths is copied, not approximated.

## Evidence

Same world (`four-player-combat-v1`), same planet (id 11, `temperate`, radius 600, at
`-3500, 0, 24000`), same camera (`yaw 90`, `pitch 8`, `distance 2200`), same frozen clock
(`time 3.0`).

| Renderer | Screenshot | Mean RGB |
| --- | --- | --- |
| Python (`tools/render/capture_python_planet.py`) | `python-planet.png` | 0.0432, 0.0592, 0.0938 |
| Native (`armada_viewer --focus … --star 0,2000,0`) | `native-planet.png` | 0.0519, 0.0776, 0.1236 |

Both frames show the same continents and cloud bands on the same limb, the same terminator sweeping
the lower-left, and the same blue atmosphere rim. The native frame is slightly brighter overall
(0.052/0.078/0.124 against 0.043/0.059/0.094) because it is a live frame with the Python HUD
composited over it while the reference has no HUD; the planet's own pixels sit in the same range.

Live path (`render_cpp/live.command`, 8 planets in the demo fixture):

```
planets: bodies_drawn 4824, textures 8, untextured_bodies 0, decode_failures 0,
         texture_failures 0, pose_failures 0
producer: generated 8, published 8, reused 3608, failures []
```

Codec agreement: `render_cpp/tests/test_planets.cpp` loads blobs written by the Python encoder,
checks every field, re-encodes and compares **byte for byte**, and refuses a flipped pixel, a
truncated payload, the wrong magic, a zero dimension, a short header and every malformed binding.

## Limits, stated rather than implied

* **No atmosphere shell pass yet.** Python draws a second, additive sphere at 1.018× radius; here the
  rim is a term in the surface shader. The pictures are close, but this is not a pixel-identical
  claim — the shell is a candidate for the effects slice.
* **No owner ring, no selection rings, no background stars.** They belong to slice 2
  (markers/selection rings) and are visibly absent next to the Python reference.
* **`--star` defaults to `0,2000,0`**, which is exactly the demo fixture's star. A map with a
  different star needs the flag; the launcher does not read it from the map yet.
* **No frame-rate claim.** This slice adds 8 draws and 2 MB of texture traffic; an equal-workload
  benchmark is slice 6 and nothing here should be read as an fps number.
* **A planet is only visible when the visibility pass says so**, exactly like a ship: the frame
  carries the instance or it does not. `collect.py` still counts `asteroid_field` as omitted.
