# W06 + W07: the window's picture and the window's pointer

W06 (projection) and W07 (input) land together because the second cannot be honest without the
first: a click is resolved against the game's camera, so if the window frames the world differently
the pointer selects something the player is not looking at.

## W06: the projection was not the FOV, it was the units

The W05 camera ring scaled the crossed distance by **0.62** to make native captures line up with
Python references. That factor compensated a projection defect and has been removed.

The defect: `camera.fov` is degrees, and `bx::math.h` documents `mtxProj`'s `_fovy` as radians, so
the call was "fixed" mid-project by wrapping it in `bx::toRad`. That is wrong for this bx version:

    bx_source-src/src/math.cpp:  height = 1.0f/tan(toRad(_fovy)*0.5f)

`mtxProj` applies `toRad` itself, so passing degrees is correct and passing radians yields a ~1 deg
field of view. Measured with the report's own probe:

| input | `proj[5]` | effective vFOV |
|---|---|---|
| `camera.fov` (55) | **1.920982** | 55 deg (matches Python's `1/tan(27.5 deg)`) |
| `bx::toRad(camera.fov)` | 119.37 | ~0.96 deg |

The viewer now reports the projection in numbers, so this cannot drift silently again:

```json
"projection": {"fov_deg": 55.0, "fov_input_rad": 0.9599, "proj_scale": 1.9209821224,
               "expected_scale": 1.9209821575, "focal_px": 768.39}
```

`proj_scale` is `proj[5]`; `expected_scale` is `1/tan(toRad(fov)/2)`. A capture is only used for a
parity claim when the two agree. `camera_ring.distance_scale` is now `1.0`: the pose crosses
verbatim, and no capture needs a compensating distance.

Consequence for older evidence: any W05 parity number taken at a compensated distance was taken
through a window that framed 1.6x closer than the game. The W05 documents say so where they rely
on it; the numbers that are geometry-level (vertex dumps, ring radii at a stated camera) stand.

## W07: the pointer enters the same controller a native window feeds

`main.py` polls `RingInput` (`render/input_bridge.py`, W04) once per frame, so the window's events
become the same pygame events `InputController.handle_event` already handles. Nothing about input
authority moved: the controller still builds `PlayerCommand`s and the simulation still validates
them.

**One batch per frame** is deliberate: draining a backlog would deliver a press and its release
before the game ran an update, and a held key would be lost.

**Closing the window** sets `CPP["quit"]`, which leaves the match the way Escape does rather than
killing the process.

### The bug this found: the camera was measured in the wrong pixels

The window and the HUD are 1280x800 (`CPP_HUD_SIZE`). The game's camera was measured at the hidden
SDL window's size — **2560x1440** on this display — because `camera.apply(W, H)` set it from the SDL
surface every frame. `world_to_screen` turns a world point into *camera* pixels, so:

- the station the window drew dead centre projected to `(1280, 720)` — the centre of a 2560x1440 view;
- a click at `(640, 400)` in window pixels was resolved as if it were at the top-left quarter;
- the pointer selected nothing, and the drag box selected the wrong ships.

Fix: in `cpp` mode the camera is applied at `CPP_HUD_SIZE`, so camera pixels, HUD pixels and window
pixels are one space. Verified live (game running, real window, events through the ring):

| gesture | result |
|---|---|
| click the station at screen centre (640, 400) | `CPP_SELECTION [16]` |
| box-drag (502, 92) -> (750, 429) over three ships | `CPP_SELECTION [16, 17, 18]` |
| click ship 19, whose projected position is (334, 183) | `CPP_SELECTION [19]` |
| right-click empty ground with three ships selected | `command_queue` 0 -> 3, last `PlayerCommand` |
| close the window | match leaves cleanly, no `armada_viewer` left behind |

The off-centre click is the point of the last test: it is resolved from the *game's* projection of
that hull, and it selects that hull, which is only possible if the window drew it where the game
thinks it is.

## Tests

`tests/test_render_pointer.py` (new, 3 tests, with the real HUD rather than a stub):

- a click on a ship selects that ship;
- a click on empty space clears the selection;
- a click on the minimap pans the camera and does not select.

Existing suites: **210 render tests OK**, native `ctest` **12/12 OK**.

## Diagnostics

`STAR_ARMADA_CPP_TRACE=1` prints what the window sent (`CPP_EVENT`), the controller state after each
event (`CPP_STATE`), bridge counters (`CPP_INPUT`) and selection changes (`CPP_SELECTION`). It is off
by default and prints nothing otherwise.

## Not claimed

- Keyboard parity is by construction (same controller, same events) but has not been exercised key
  by key; the arrow/WASD pan and the hotkeys share the path the mouse now proves.
- Input latency is not measured: events are sampled once per game frame by design.
