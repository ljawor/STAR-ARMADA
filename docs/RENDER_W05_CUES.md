# W05 slice 2 — ownership cues: selection rings, markers, planet owner rings

The window now draws the three overlays the Python renderer paints on top of the world. The rule
from W02–W04 holds: **Python decides, the window draws.** What crosses the bridge is a batch of
primitives (`ARMARK01`), not a picture and not a decision.

## What travels, what does not

| Cue | Decided in Python | Drawn by the window |
| --- | --- | --- |
| Selection ring | which ids are selected, the colour (owner, or orange < 70% hull, red < 35%), whether a ring is shown at all (a shielded unit hides its ring behind the bubble), flat vs upright | the line segments, from the world radius and segment count |
| Ownership marker | whether the unit gets a marker for this relation and marker mode, the shape (`render/markers.py::shape_for`) and the colour (`marker_color`) | the billboard, with a pixel footprint derived from **its own** camera so the icon stays 9–15 px at any zoom |
| Planet owner ring | the colonist, its colour, and the `radius + 120` clearance | the depth-tested line loop (40 segments) |

Nothing about *who is selected* or *who owns what* is recomputed natively. The window never learns
an entity id, a relation or a hull fraction.

## Format (`render_bridge/markers.py`)

```
header  <8sHHII       20 B   magic "ARMARK01", version 1, count (<=1024), reserved, crc32(records)
record  <BBH4B3fffHH  32 B   kind, shape, flags, rgba, centre xyz, size, width, segments, reserved
```

* `kind` 1 circle, 2 marker.
* circle `shape` 0 flat (the ecliptic), 1 upright (stations, worlds) — matching the Python
  `glRotatef(-90)` and the flat XZ loop.
* marker `shape` 0 chevron, 1 diamond.
* `flags` bit0 depth test (planet rings), bit1 alpha blend.
* circle `size` = world radius; marker `size` = the hull's world radius, from which the window
  derives the icon's pixel footprint.

A batch that fails magic, version, count, length, crc, kind or reserved checks is refused whole —
a cue batch that half-decodes paints a ring around a unit that is not selected. The decoder keeps
the last good batch and counts the failure instead.

## Evidence

* `tests/test_render_markers.py` — 16 tests: byte-identical round trip, six kinds of damaged batch
  refused, and the *rules* (shielded unit draws no ring; 20% hull → red, 50% → orange; station and
  world rings upright; a world ring is `radius + 120` and depth-tested; hostile → diamond; own
  marker lifted toward white; `hostiles` mode hides own markers; a marker carries the hull radius,
  not pixels).
* `render_cpp/tests/test_markers.cpp` — loads Python-written `cues.bin`, checks every field,
  re-encodes **byte for byte**, and refuses five damaged variants. ctest **7/7**.
* Live run (`four-player-combat-v1`, 638 instances): **9 cue batches, 0 decode failures,
  0 dropped vertices**; ~638 markers per frame, ~22 rings per frame (8 planet owner rings plus
  unshielded selected units), ~12 k cue vertices per frame.
* Screenshots: a world at `-3500,0,24000` with its colonist's ring circling it in the ecliptic
  (`artifacts/cpp-renderer/w05/planet-owner-ring.png`), and a fleet view with the orange hostile
  diamonds over enemy hulls (`artifacts/cpp-renderer/w05/cues-fleet.png`).

## Known gaps (not claims)

* **Selection rings are sized from `ship_size(...).radius`** — the hull's world radius, so a ring
  encloses the hull that was drawn. The legacy renderer additionally multiplies by a
  camera-dependent *readability* inflation (`render/ship_sizes.py::readable_size`); the window does
  not, and uses a 9 px floor instead. At default zoom the two agree; on a far-out camera the legacy
  ring is larger than the native one.
* **Stations and worlds** ring at `entity.radius`, since their world radius is the drawn radius.
* **Line width.** bgfx has no line width, so every cue is one pixel. The legacy renderer draws
  selection rings at 2 px and planet rings at 3 px, so the native cues read thinner.
* **Cue depth.** Planet owner rings set the depth flag, but view 1 has no depth buffer bound, so
  the ring is currently drawn over the body instead of behind it.
* **Live selection** is still W04 debt: the input bridge records orders, not a selection. A ring is
  inspected with `--select <id>` (or `ARMADA_SELECT="26 27"` through `live.command`), and
  `--select-owned` is a *diagnostic* stand-in that rings every own ship.
* Markers are drawn for everything the detection frame carries, so a crowded view is busier than
  the legacy decluttered default (`hostiles` mode exists but is not the live default).
