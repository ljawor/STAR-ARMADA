# World-anchored HUD elements are drawn by C++

The placement banner, the placement ghost, the construction ring with its percentage and the
floating sim messages used to be rasterized on the pygame overlay with the Menlo bitmap font
while the panels, minimap and notifications beside them were already native vector geometry.
Side by side, the bitmap ones read as a 640x480 layer: monospaced, heavier, and upscaled by the
overlay texture instead of being drawn at the display resolution.

They now go through the same `vector_hud` layer as everything else, at native resolution, in the
bundled Noto Sans atlas, with hairline strokes:

| element | before | after |
| --- | --- | --- |
| `PLACE <STATION> — left-click …` banner | pygame `font_big` (Menlo bold 19) blitted | native text, size 28.5 em, `fit=center`, plate measured with the same font metrics |
| ghost ring / crosshair | stroke 2 | stroke 1 |
| `✓ place <station>` / `✕ <reason>` | pygame `font_small` blitted | native text, size 18 em |
| construction ring | stroke 2 + 48 chords of width 4 | stroke 1 + one filled annulus polygon, 3 px band |
| `66%` | pygame `font_small` blitted | native text, size 18 em, centred under the ring |
| `Station complete` (floating text) | pygame `font_small` blitted | native text with the same plate |

Two supporting changes:

* `render/hud.py` gains `_native_layer()` (a full-screen identity `Sink`, so world coordinates stay
  world coordinates), `_screen_text()` and `_text_box()`. Layout is still measured with pygame,
  which keeps plates and anchors pixel-identical in both layers; only rasterization moved.
* `render_cpp/src/vector_hud.cpp` gains U+2713 as a vector icon (a 0.11 em ribbon). The atlas has
  no check glyph, so the native label would otherwise have fallen back to `?`. The existing `✕`
  was already in that icon set.

U+2713 was added to the shared `incomingIcon` coverage test, which now clips at the check's elbow
because its ink deliberately occupies the lower half of the em box.

## Evidence

`before-*` / `after-*` crops come from the production embedded renderer (`armada_embedded`
`armada_frame`, BGRA readback) with a real skirmish HUD published through `LiveSession`; the
placement, ring and floating-message states were set on the real `HUD`. Sizes: 1280x800 and a 1:1
1920x1080 run (HUD logical size equal to the drawable, as in the game window).

This is pipeline evidence, not owner acceptance: the owner's own `main.py --skirmish` run is what
decides whether the change lands.
