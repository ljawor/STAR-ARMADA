# W09: cue weight and a background

Two visible differences from the legacy picture are closed here; the rest are listed at the end
rather than quietly dropped.

## Cues were hairlines

bgfx has no line width, so every ring, planet owner ring and marker outline in the window was a
single pixel while `render/primitive_batch.py` draws 2-3 px. A thinner cue is not a smaller version
of the same cue; on a busy tactical map it reads as a different one.

`pushThickSegment()` widens each segment into a screen-aligned quad on the CPU: the offset is
perpendicular to the segment inside the camera plane, and the caller sizes it from the segment's own
depth (`1.25 * depth / focal` for rings, `1.0 * depth / focal` for marker outlines) so the stroke is
a constant number of pixels at any zoom.

Measured on the pinned marker fixture (`tools/render/write_marker_fixtures.py`, a 135-unit ring at
`(100, -20, 30)`, camera 2200/pitch 65) by scanning the green stroke horizontally:

| stroke width | rows |
|---|---|
| 1 px | 19 |
| **2 px** | **94** |
| 3 px | 26 |
| 4 px | 14 |

Mode 2 px, wider where a segment crosses the scan line at a shallow angle - which is what a widened
segment looks like. A 1 px line primitive cannot produce a 2 px run, so this is not a measurement
artefact. Artifact: `artifacts/cpp-renderer/w09/cues.png`.

## The background was empty

`render/renderer.py` draws a 1400-point starfield. The window drew nothing behind the fog, so space
was flat black where the game has stars. The window now builds its own starfield once, from a fixed
xorshift seed, on a 90,000-unit sphere (~1.2 px half-size at 1280x800), drawn before the scene with
no depth test or write so it can never occlude a hull.

This is the one thing in the picture the window invents, and it is deliberate: stars carry no
gameplay meaning and nothing in the simulation can be wrong about them. Everything that *can* be
wrong still crosses as an answer.

Measured: **5,828 non-background pixels in an otherwise empty frame** (1400 quads at ~4 px each).
Artifact: `artifacts/cpp-renderer/w09/stars.png`.

## Still different, and staying that way for now

- **Planet atmosphere shell** - not drawn. Planets are textured spheres.
- **Asteroid fields** - not drawn; counted and reported, never silently omitted.
- **Legacy point-sprite projectiles** - `renderer.py` draws bolts as point sprites; the window draws
  the emissive batch, which covers beams and impacts but not every legacy sprite.
- **Planet owner rings** are drawn flat (no depth test), so they can overlap a hull in front of the
  planet. Python draws them over the planet too, so the ordering is only wrong for objects between
  the camera and the ring.
- **Surface hardware** has geometry parity (7,500 vertices, 0 mismatches) but no pixel parity claim.

None of these change what the game does; they are picture differences, and they are listed here so
the next reader does not have to rediscover them.
