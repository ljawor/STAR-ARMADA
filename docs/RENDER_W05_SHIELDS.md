# W05 slice 5 — the standing shield shell

A shield bubble is a view-aligned hemisphere whose per-vertex alpha bakes the rim falloff, tinted by
the strength ramp. Python builds one display list per strength octant and reuses it for every
shielded unit at every heading; the window builds one mesh per detail level and draws it instanced.

## What crosses the bridge

| Field | Meaning | Decided by |
| --- | --- | --- |
| `a` | world-space centre | the simulation |
| `radius` | world-space shell radius (`ship × 1.08`, `station × 1.35`) | Python (`emissive_batch.shield_radius`) |
| `width` | the shield fraction (`mean quadrant / max_shield_total`) | Python (`emissive_batch.shield_fraction`) |
| `colour rgb` | the strength ramp at that fraction, quantised to eight octants | Python (`render/primitive_batch.py::shield_color`) |
| `colour a` | the fade alpha, floored at `0.20` so a failing field stays legible | Python (`SHIELD_FADE`) |

`kind = SHIELD = 6`, in an existing 44-byte `ARMEMIT1` record. No new ring, no record growth, no
change to `render_bridge/protocol.py`.

Nothing about *whether* a unit has a shield, how strong it is, or what colour that strength reads as
is computed in the window. A hull-damage guess inside the window would be a second opinion about
game state.

## What is native

Two things, both of which need the camera:

* **the readability floor** — `SHIELD_MIN_PX` (74 px) grows a bubble that would otherwise collapse
  to its rim, exactly as `renderer.py::_shield_bubble` does with `want_r = SHIELD_MIN_PX * 0.5 / ppw`;
* **the detail level** — `< 20 px` low (20×5), `< 40 px` medium (30×8), else high (40×10), the same
  thresholds and the same lat/lon counts as `_shield_shell_list`.

The baked latitude terms are the renderer's own numbers: `BASE_A = 0.001`, rim `0.18 · graze²`, and a
capped `0.18 · graze³` whitening toward the limb.

## Why instanced rather than rebuilt

The first implementation rebuilt the hemisphere on the CPU every frame: 2,400 vertices per shell,
which at battle scale (622 bubbles) is 1.49 M vertices — more than a transient vertex buffer holds
(9,600 vertices of that layout), so the whole list was dropped and *no* bubble drew. Chunking fixed
the drop but left ~155 submits and 48 MB of memcpy per frame.

The shell is view-aligned, so in **view space** its geometry is identical for every unit at every
heading — the observation that lets Python cache one display list per octant. The window does the
same: three meshes built once, eight floats per shell per frame (view-space centre, radius, tint,
fade), three instanced draws. Live at 622 shells: `instances_by_detail.high = 622`, `dropped_vertices 0`.

## Measurement

`tools/render/write_shield_fixtures.py` encodes four bubbles through the real bridge encoder — full,
half, nearly spent, and a station — lifted to `y = 6000` so the fleet is out of frame (a lit hull is
brighter than a rim and would make the sampling meaningless).
`tools/render/capture_python_shields.py` renders the same four with the real `_draw_shields`, every
other pass skipped. `tools/render/compare_shield_frames.py` labels coloured blobs in both frames
against each renderer's own clear colour, matches them by centroid, and reports size, light and rim
hue. Synthetic, and labelled as such: nothing in the fixture is a real engagement.

| bubble | centre offset | radius ratio | energy ratio | rim hue (native / Python) |
| --- | --- | --- | --- | --- |
| full (blue) | 0.22 px | 1.003 | 0.997 | 0.92 / 0.92 / 0.93 |
| half (yellow) | 0.10 px | 1.019 | 1.006 | 0.89 / 0.89 / 0.94 |
| spent (red) | 0.20 px | 1.017 | 0.988 | 0.83 / 0.80 / 0.84 |
| station | 0.41 px | 1.008 | 0.998 | 0.955 / 0.954 / 0.950 |

The nearly-spent bubble is ~17 % dimmer in the window than in Python; the other three are within
1.4 % of the reference light. The cause is the alpha floor and the coarser silhouette at that size,
not a different rule — it is reported rather than tuned away, because the strength cue is Python's
and both sides received the same record.

Frames: `artifacts/cpp-renderer/w05/native-shields.png` (window),
`artifacts/cpp-renderer/w05/python-shields.png` (reference),
`artifacts/cpp-renderer/w05/shields-live.png` (a live ring, 622 bubbles),
`artifacts/cpp-renderer/w05/shields-parity.json` (the numbers above).

## Not carried by this slice

* **shield and hull hit flashes** (`render/hit_effects.py`) — separately tracked as slice 3c;
* **per-quadrant damage on the bubble face** — the renderer deliberately does not bake it either
  (quadrant state moves with heading *and* camera, so baking it would reintroduce an unbounded cache);
* **anything about shield regeneration** — that is simulation, and it stays there.
