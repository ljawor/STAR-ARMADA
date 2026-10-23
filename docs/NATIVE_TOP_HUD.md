# Native upper HUD — first migration slice

Ordinary `main.py` activates this path through `LiveSession`; no settings switch or
separate viewer is needed. Python still owns simulation, income, command usage,
translation and player commands. C++ owns the top strip's measured layout, font
rasterization and GPU drawing at the actual drawable size.

Only the top resource strip, clock, pause readout and FPS readout migrate. The
selection/action panels, minimap, event log, mission panel, placement prompt and
centred game-over banner remain in the existing Python overlay. FPS moves out of
the right panel header into the native strip.

## Boundary and ordering

- `render_bridge/top_hud.py` copies authoritative display values into bounded
  UTF-8 JSON. `top-hud.ring` carries complete version-1 snapshots, not bitmap
  pixels or dependent patches; a late consumer can use the latest record.
- `render_cpp/include/top_hud.hpp` / `src/top_hud.cpp` validate and lay out the
  model and rasterize the bundled open-licensed Noto Sans font. Latin and
  Cyrillic remain available; Russian is not disabled.
- The font file is a pinned trusted asset, checked before the native font reader
  sees it. It is not a user-selectable arbitrary font parser.
- GPU order: world (view 1), native strip (view 2), remaining HUD and application
  overlays (view 3), embedded readback (view 4). Modal/presentation overlays stay
  above the strip instead of having native type painted across them.
- The strip is `round(34 * drawable_height / 800)` pixels high. The input
  controller retains its existing `(0, 0, 1280, 34)` logical occlusion region;
  pointer coordinates still pass through the existing physical-to-logical map.
- The rest of `hud.ring` remains at 1280×800; this slice does not increase the
  bitmap codec's limit or claim to sharpen unmigrated panels.
- Native presentation mode activates only after session initialization succeeds.
  A failed constructor closes all rings it already created and retains the prior
  shared-HUD mode. Successful teardown restores that mode and is idempotent.

## Wire v1

Maximum JSON payload: 16,384 bytes. Exactly five resource cells, in the existing
CR / MT / EN / CRW / CMD order. Fields:

```json
{"version":1,"active":true,"cells":[
  {"label":"CR","value":"12,345","rate":"2.5/s","color":[86,140,220],"rate_color":[128,142,164]},
  {"label":"MT","value":"2,345","rate":"0/s","color":[200,170,120],"rate_color":[232,92,76]},
  {"label":"EN","value":"18","rate":"0/s","color":[150,220,240],"rate_color":[232,92,76]},
  {"label":"CRW","value":"84","rate":"0/s","color":[110,200,120],"rate_color":[232,92,76]},
  {"label":"CMD","value":"27/120","rate":"","color":[214,224,238],"rate_color":[128,142,164]}
],"clock":"02:05","paused":"ПАУЗА","fps":"60 FPS"}
```

Labels are bounded to 16 UTF-8 bytes, other strings to 96. Native validation
rejects malformed/oversized payloads, invalid UTF-8/control characters, wrong
versions/types/cell counts and invalid colours, preserving the last good model.
An inactive valid model clears the native strip. No schema field authorizes a
simulation action.

## Verification commands

Use a scratch output directory, not the source tree's user saves. Rebuild the
existing `render_cpp/build-w02` targets first; a source checkout alone does not
replace the native library.

```sh
cmake --build render_cpp/build-w02 -j8
ctest --test-dir render_cpp/build-w02 --output-on-failure
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m pytest -q tests/test_native_top_hud.py
.venv/bin/python tools/render/probe_native_top_hud.py --out "$TMPDIR/native-top-hud-pixels"
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/render/capture_native_top_hud_game.py --out "$TMPDIR/native-top-hud-main"
```

The windowless probe exercises the production library's pixels, glyph colours,
language snapshots, stale-state removal and app-overlay ordering. It compares an
otherwise identical inactive-native control, resumes against a clean strip
captured before native pause/FPS were ever drawn, preserves the last good strip
after malformed input, clears an inactive strip, and checks opaque application
coverage across the entire header. Its backdrop is the offline catalogue, not
an ordinary running match.

The game capture runs the actual `main.py --skirmish` bootstrap and unmodified
loop body in a hidden Cocoa/GL window. Before/after use the same paused match
and camera: the control retains the Python top strip; the after uses the default
native path. Real SDL pause/resume and top-strip click occlusion are checked.
Settings/campaign/balance paths are isolated; protected user files must remain
byte-identical. These tools do not establish frozen-app/Windows acceptance or a
whole-game FPS target.
