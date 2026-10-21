# W05 slice 3d: colony shield domes

A colonized world whose surface `planet_shield_generator` is online carries a translucent shell
just above its foundations. The Python renderer draws it in `_draw_planet_shields` /
`_planet_shield_dome` with the same view-aligned unit sphere a ship bubble uses, scaled to the
planet and blended additively. That is the last decision-free part of the planet layer the window
was missing.

## What crosses

Nothing new. A dome is a `kind 6` (`SHIELD`) record — the record slice 5 introduced for ship
bubbles — with the planet's centre, the field radius, the field's strength fraction and the
strength ramp's tint:

| field | meaning for a dome |
| --- | --- |
| `a` | the planet's centre |
| `radius` | `planet.radius * 1.04 + 48.0`, the figure `planet_building_geometry.planet_shield_fields` already owns |
| `width` | the generator's pooled fraction, `total_shield() / max_shield_total()` |
| `colour` | the renderer's strength ramp: RGB stops quantised to eight buckets, alpha floored at `SHIELD_FADE[0]` |

No new ring, no record growth, no shader change, no viewer change. The dome is drawn by the
instanced shell pass that already carries 622 hull bubbles per frame in a live skirmish.

## What stays in Python

* **whether a dome exists.** Only an operational generator of the kind `planet_shield_generator`
  whose owner is the planet's colonizer raises one. `PlanetDomes.step` asks
  `planet_building_geometry.planet_shield_fields`, the single pass the renderer itself uses, so the
  window cannot disagree with the simulation about who is protected.
* **the radius.** It comes from that same function, not from a guess about planet size in the
  window.
* **the pulse after a loss.** `_planet_shield_dome` shows a hit by drawing the same additive shell
  `1 + round(flash * 2)` times, and for `(SRC_ALPHA, ONE)` repeated draws compose by addition — a
  brightness multiplier, not a hue. The producer keeps the same flash state (raised to 1.0 when the
  pool drops, decayed at 3.0/s) and publishes the record two or three times. A tinted pulse would
  have meant inventing a colour the renderer never shows.
* **an empty field raises nothing.** `fraction <= SHIELD_MIN_FRACTION` (0.001) is the renderer's own
  visibility line; a spent generator is drawn nowhere on either side.

## What the window decides

Only the two things slice 5 already made native: the shell's detail level (20×5, 30×8, 40×10
quads) and the `SHIELD_MIN_PX` readability floor, both derived from its own camera. A planet dome
projects hundreds of pixels across, so it always lands on the high-detail mesh and never touches
the floor.

## Measured

`tools/render/dome_scene.py` holds the one scene both sides render: a planet of radius 900 at
`(0, 6000, 0)`, its field at 984, camera 2600 back at pitch 22 / yaw 10. The Python side is the
renderer's own `_planet_shield_dome`; the window side is the fixture ring
`render_cpp/tests/fixtures/dome/` through `--emit-ring`, captured at the same camera distance
(equal distance is the framing that matches — the projection defect compensates for nothing here).

| | python | window | ratio |
| --- | --- | --- | --- |
| rim radius (peak of the radial profile) | 291 px | 291 px | **1.0000** |
| shell area above the signal threshold | 107,628 px | 108,420 px | 1.0074 |
| limb colour `rgb` | 0.0357 / 0.0555 / 0.0919 | 0.0361 / 0.0558 / 0.0924 | 1.0054 |
| shell-interior colour `rgb` | 0.0032 / 0.0039 / 0.0078 | 0.0032 / 0.0039 / 0.0078 | 1.0000 |
| peak colour `rgb` | 0.0549 / 0.0824 / 0.1333 | 0.0549 / 0.0824 / 0.1333 | 1.0000 |

Both sides are measured against their own background — Python draws over black, the window over
its own sky (`0.0314 / 0.0549 / 0.1059`) — with `tools/render/compare_dome_frames.py`, which reads
the radius off a radial profile rather than a bounding box: a box follows the faintest stray pixel,
and the window's sky gradient trails a few counts past the rim. The bounding-box radius comes out
1.26× on the window for exactly that reason, and is **not** the number to quote.

The pulse frame (a field at half strength, so the renderer re-adds the shell three times) agrees on
radius and on the interior:

| | python | window |
| --- | --- | --- |
| rim radius | 291 px | 291 px |
| shell area | 161,772 px | 162,240 px |
| limb colour `rgb` | 0.1813 / 0.1382 / 0.0321 | 0.2123 / 0.1605 / 0.0384 |
| peak `rgb` | 0.2706 / 0.2000 / 0.0471 | 0.2588 / 0.2000 / 0.0471 |

The limb band is ~17 % brighter on the window and the peak is 5 % lower: the same three additive
passes, spread slightly differently across the band. This is the known quantisation difference
recorded for the spent ship bubble in `docs/RENDER_W05_SHIELDS.md`, at a much larger scale; it is
not corrected here, because "correcting" it means changing the shared shell's falloff for every
bubble in the game.

`artifacts/cpp-renderer/w05/dome-ab.png` is the two-by-two sheet: full field and post-hit pulse,
Python on the left, window on the right.

## Reading the viewer report

`shields.shells` and `emissive.primitives` are **cumulative over every drawn frame**, not per
frame: one dome over a 10-frame run with the default 30-frame warmup reports `40`. Both counters
include the frame warmup, which is where the number comes from — not from 40 domes.

## Still open in the planet layer

Planet **buildings** (`render/planet_building_geometry.py`, the surface hardware the generator
exists to protect) are still drawn by Python only. They are the next slice: the geometry is
procedural `_Hardware` output, so it has to travel as authored mesh data rather than as a shape the
window rebuilds.
