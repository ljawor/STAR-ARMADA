# W05 · the switch: `main.py --renderer cpp`

Status: **in the tree**, opt-in. `--renderer legacy` (the default) is unchanged; `--renderer cpp`
hands the running match to the native window and draws nothing in this process.

## What the switch is

`legacy` draws with this process's own GL context. `cpp` publishes the same match into rings and
lets `armada_viewer` draw it:

```
main.py --renderer cpp
  simulate (unchanged)
  ├─ render_bridge/live.py::LiveSession.publish(state, selection=…, visible_ids=…, dt=…)
  │    ├─ frame.ring      instances, effects, projectiles, tables   (W02)
  │    ├─ hud.ring        the composed HUD surface and its dirty rects (W03, design A)
  │    ├─ markers.ring    ownership cues                            (W05 s2)
  │    ├─ emit.ring       fire, beams, shields, blasts, contacts, domes (W05 s3a–s3d)
  │    ├─ fog.ring        the visibility mask                       (W05 s4)
  │    └─ planets.ring    planet textures                           (W05 s1)
  └─ render_bridge/cpp_window.py spawns render_cpp/build-w02/armada_viewer pointed at those rings
```

The invariant is the one every slice has held: **Python decides, the window draws.** `LiveSession`
reads no input, moves no ship and resolves no contact. Even the visibility answer is handed in —
`main.py` computes it with `state.can_see` (≈45 ms p95 over a full fleet) and passes the id set,
because deriving it in the window would be a second opinion about the game.

The HUD crosses as a picture (design A): `render.hud` paints a `pygame.Surface` exactly as it does
for the legacy window, so text stays SDL_ttf and no glyph rasterisation moved into C++. A whole
surface is published first and every 2 s after that; the frames between carry only dirty rects.

## Evidence

*Play-through.* `main.py --smoke --renderer cpp` runs the same 30-second skirmish the legacy smoke
runs, through the producer path, and ends with the same result line:

```
SMOKE_DONE     t=30s winner=None entities={0: 7, 1: 12} P0(cr=8030 mt=4000 techs=0) P1(cr=4750 techs=0)
SMOKE_CPP_OK   t=30s winner=None entities={0: 7, 1: 12} P0(cr=8030 mt=4000 techs=0) P1(cr=4750 techs=0)
```

*Producer cost*, 345 published frames of that skirmish (17 instances, 5 emit primitives, 7 cues —
a small skirmish, not a battle):

| stage | median | p95 |
|---|---|---|
| frame | 0.040 ms | 0.059 ms |
| HUD (compose + encode) | 1.128 ms | 1.856 ms |
| emissive | 0.047 ms | 0.057 ms |
| fog | 0.033 ms | 0.045 ms |

`LiveSession.report()` says the same thing in its own note: *publish cost only; it excludes
simulation, the renderer and the window.* No frame rate is claimed for this mode — there is still no
equal-workload benchmark, and adding one is not part of this switch.

*The window is a child of the game.* It starts when the session starts and is gone when the game
exits: `kill -TERM` on the game left no `armada_viewer` behind, so a crashed or quit match cannot
leave a window drawing a dead ring.

*The window draws it.* A second viewer attached to the same rings while the game was running:
`frames_applied 7`, `full_frames 1`, `patches_applied 97`, `decode_failures 0`. The captured frame
(`artifacts/cpp-renderer/w05/live-switch.png`) shows the resources bar (`EN 2,000  CRW 4,008
CMD 9/34`), the ACTIONS / BUILD panel with its FLEET COMMAND text, the minimap with contacts, the
ships, the owner rings and a planet — the same HUD code, the same match.

## The camera crosses too (`ARMCAM01`)

The frame ring carries no camera, so the window had its own and the window showed a different place
from the one the game was playing - which is exactly what "the game started but I cannot see it"
looked like. `render_bridge/camera.py` publishes the pose the game's camera already holds, six
float32 behind a 20-byte header: target xyz, distance, yaw, pitch (degrees, as `render.camera.Camera`
and the window's `Camera` both use). `--camera-ring` makes the window apply it before it builds the
view matrix, so the two views agree.

One compensation is applied and named: the window scales the distance by **0.62**. That is not a
preference, it is the documented projection defect - this build feeds `camera.fov` (degrees) to
`bx::mtxProj`, which wants radians, so the vertical field of view is ~88 deg instead of 55 and
everything draws at ~54% of its intended size. Scaling the distance makes the battle frame the way
the game frames it. It comes out in the same change that fixes the defect and re-baselines the
comparisons.

## The window always draws something

Three failures had to stop being silent, because a renderer mode that shows nothing is worse than
the one it replaces:

* **No mesh catalogue**: the window loads mesh bindings from an offline snapshot even in live mode
  (the rings carry transforms and a binding id, not geometry). The catalogue now ships as
  `assets/cpp/catalogue.snap` - 103 approved meshes, 50 KB, built by `tools/render/dump_snapshot.py
  --catalogue` - so `--renderer cpp` needs no setup. `STAR_ARMADA_CPP_SNAPSHOT` overrides it; if the
  shipped file is missing, the catalogue is built in a child process (in-process is refused: "model
  selection changes require a session boundary with renderers closed").
* **The window will not start**: the game says so once and **draws with the legacy renderer** for
  the rest of the match instead of publishing into a void.
* **The producer throws**: the same fallback, with the exception printed, and the window is
  terminated. A fault in the display path must not end a match.

The SDL window is minimized once the native window is up (`pygame.display.iconify()`), so the
unfocused, no-longer-drawn surface is not left in front looking like a frozen game.

## What is not connected, and why

**Input still does not come back.** With the camera crossing, the views now agree on *where* they
look - but not on *how much they see*: the window's ~88 deg vertical field of view against the game's
55 deg means a pixel near the edge of the window corresponds to a different world ray than the same
pixel in the game. A click resolved in Python through the game's camera would therefore pick or
order something the player is not pointing at. W04's `RingInput` is written and tested
(`render/input_bridge.py`, `tests/test_input_bridge.py`, `render_cpp/tests/test_input.cpp`), and
`LiveSession` still creates the input ring - it is the attachment point - but `main.py` does not poll
it. **Fixing the projection is the gate**, and then the input ring can be read.

So `--renderer cpp` is now a **faithful live view** of the match, not yet a way to play one: what you
see is what the game sees, but clicks still go nowhere and the game's keyboard does not reach the
window.

**HUD state is the subset the session knows.** `LiveSession` composes with the selection, the local
player and no pause text (`paused=False`, empty message): menus, tooltips owned by `menus.py` and
the pause banner are not bridged. The in-match HUD — resources, panels, minimap, selection — is.

**Rings live beside the game.** `USER_DIR` is `'.'` in a source checkout, so a development run writes
`cpp-window/` next to `main.py` (git-ignored); a frozen build writes it under the user directory.

## Files

| file | role |
|---|---|
| `render_bridge/live.py` | `LiveSession` — the producer for a running match |
| `render_bridge/cpp_window.py` | spawn/stop `armada_viewer` as a child of the game |
| `main.py` | `--renderer`, `cpp_session`, `cpp_seen_ids`, `cpp_publish` |
| `tests/test_render_live.py` | 7 tests: rings, counts, keyframe-then-rects, decode against the session's tables, memoized radii |

## Testing

```sh
PYTHONPATH=.:tests SDL_VIDEODRIVER=dummy ./.venv/bin/python -m unittest \
  test_render_planets test_render_packed test_render_ring test_render_overlay test_overlay_upload \
  test_render_input test_input_bridge test_render_markers test_render_emissive test_render_fogmap \
  tests.test_render_hardware tests.test_render_live     # 199 tests
(cd render_cpp/build-w02 && ctest --output-on-failure)  # 12 tests
./.venv/bin/python main.py --smoke                      # legacy: SMOKE_DONE
./.venv/bin/python main.py --smoke --renderer cpp       # switch: SMOKE_CPP_OK
```
