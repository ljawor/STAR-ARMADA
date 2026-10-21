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

*The window draws it.* A second viewer attached to the same rings while the game was running:
`frames_applied 7`, `full_frames 1`, `patches_applied 97`, `decode_failures 0`. The captured frame
(`artifacts/cpp-renderer/w05/live-switch.png`) shows the resources bar (`EN 2,000  CRW 4,008
CMD 9/34`), the ACTIONS / BUILD panel with its FLEET COMMAND text, the minimap with contacts, the
ships, the owner rings and a planet — the same HUD code, the same match.

## What is not connected, and why

**Input does not come back yet.** The frame ring carries no camera, so the window's camera is its
own: a click leaves the window in window pixels and would be resolved in Python against the *game's*
camera. Two views, so a click would select or order something the player is not looking at. W04's
`RingInput` is written and tested (`render/input_bridge.py`, `tests/test_input_bridge.py`,
`render_cpp/tests/test_input.cpp`), and `LiveSession` still creates the input ring — it is the
attachment point — but `main.py` does not poll it. The next package is a camera ring: the pose the
game's camera already holds, published beside the frame, applied by the window so both views agree,
and only then is the input ring safe to read.

Until then `--renderer cpp` is a **display of a live match**, not yet a way to play one: the window's
camera can be orbited and zoomed freely and the world stays correct, but the game does not see those
clicks, and the game's own keyboard does not reach it (the SDL window is not the focused one).

**The window needs a snapshot for its mesh catalogue.** `armada_viewer` loads asset bindings from an
offline snapshot, so `STAR_ARMADA_CPP_SNAPSHOT` must name one:

```sh
STAR_ARMADA_CPP_SNAPSHOT=~/star-armada-live/live.snap ./.venv/bin/python main.py --renderer cpp
```

Without it the match still runs and the rings are still published; `cpp_window.spawn` says so
instead of pretending a window is up. Buildings created mid-match arrive as meshes over the W05
slice 3e ring, so the snapshot supplies the catalogue and the ring supplies the rest.

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
