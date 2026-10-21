# W08: the window is told what the player is told

The HUD was already composed by `render.hud` inside the session (design A), but the session told it
a constant: `paused=False, message='', flash_left=0, fps=0`. Everything that is *not* about the
world - whether the match is paused, the status line, the fps counter, the live drag box, the
floating texts - never crossed, so a paused match looked like a running one and a replay showed no
status.

## One place decides

`main.py` now computes the view state once per frame, before either display path, and hands the same
values to the window and to the legacy renderer:

```python
view_paused, view_msg, view_flash, view_fps = paused, flash_msg, max(0.0, flash_left), fps
view_drag = (inputc.drag_start, inputc.drag_cur)
view_texts = renderer.floating_texts_screen()
```

`LiveSession.publish(paused=..., message=..., flash_left=..., fps=..., drag_box=..., floating_texts=...)`
applies them to the HUD object before composing, so `set_drag_box` / `set_floating_texts` /
`compose(...)` see exactly what the native path sees.

Two things stay in the match's own hands and are deliberately *not* in the window:

- **paused** is the simulation's flag; the window only draws the label.
- **floating texts and the drag box arrive as finished screen pixels**, projected from the game's
  camera, so the window decides nothing about where a "+120 hull" belongs.

## Verified live

Key `p` sent through the input ring (KEY_DOWN/KEY_UP, code 112) toggles the pause, traced as
`CPP_VIEW paused=True`. Screenshots of the same window before and after:

| state | pixels in the PAUSED label band (1060..1280, 0..40) |
|---|---|
| paused | 370 px of warn amber `(232, 168, 76)` |
| running | 0 px of amber, 248 px of text grey `(214, 224, 238)` |
| difference | **836 of 8,800 px** in that band |

Artifacts: `artifacts/cpp-renderer/w08/paused.png`, `running.png`.

## A trap worth writing down

A viewer attached to a running match is up to **2 s** behind the HUD: patches are only meaningful
after a keyframe, and keyframes go out every `overlay_keyframe` seconds (2.0 by default). A capture
taken in the first second shows the HUD as it was at the last keyframe - which reads exactly like
"the HUD does not update". Use `--seconds 4` (not `--frames 25`) for HUD captures; the report then
shows `full_frames >= 1`. The earlier W08 attempt "proved" no change with `full_frames: 0`.

## Tests

`tests/test_render_live.py::test_the_window_is_told_what_the_player_is_told`: publishes twice, once
running and once paused with a drag box, and asserts the drag box reached the HUD and the composed
overlay actually changed (sampled every 4 px). 211 render tests OK, `ctest` 12/12 OK.

## Still in SDL, by design (unchanged from the W05 plan)

Menus, the pause menu, tooltips drawn as native windows and the recovery overlay stay in the game's
own window; the window shows the match. `Esc` opens the menu in the SDL window and the match HUD
pauses; there is no menu rendered by the C++ window.
