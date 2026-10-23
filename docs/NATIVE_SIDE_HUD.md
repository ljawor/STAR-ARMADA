# Native compact side HUD and minimap

The ordinary `main.py` match path uses the existing embedded C++ renderer for the left selection/status panel, right actions/build/research/refit panel and minimap. This extends the separately approved native upper strip; it does not replace Python gameplay or create another viewer entrypoint.

## Presentation and authority

- `LiveSession` enables `HUD.native_panels` only after every ring/resource has initialized. Shutdown restores the caller's previous mode. Constructor failure closes initialized mappings and preserves the original exception.
- Python owns selected/known entities, visibility, translated strings, resource calculations, row allocation, scrolling, command payloads, validation and execution. C++ receives no simulation authority.
- `HUD` explicitly captures complete left/right collapsible scopes and the minimap. Geometry and text are captured before pygame rasterization; no side-panel/minimap bitmap or pre-rendered glyph is transported.
- Side geometry, effective clips, button rectangles, blocked areas and wheel regions share one edge-rounded 0.75 affine transformation. Left x=10 remains fixed; right x=W−330 becomes W−250; y=44 remains fixed. Both panel width and height shrink approximately 25%, not just their texture resolution.
- The minimap keeps `[W−222,H−222,210,210]` logical bounds and its four-pixel content inset. Fog exports semantic unseen/remembered/currently-visible cell states, with negative-z at the top; private contacts stay filtered by Python's existing known-entity path.
- Event log, mission, floating annotations, placement/targeting prompts, drag box and outcome/application overlays remain on the original Python overlay path.
- Native bar-label positions anchor measured ink inside their bar, rather than centering a padded pygame glyph surface around a native ink origin.
- Noto/stb em-height is corrected before the panel transform so visible text does not accidentally shrink twice. Actual-main heading ink measures 14→11 pixels at 1280×800 and 25→20 at 2560×1440; line boxes still constrain fitting and clipping.

## Wire snapshot

`render_bridge/vector_hud.py` produces complete UTF-8 JSON records into `hud-vector.ring`; the launcher forwards `--vector-hud-ring`. Complete records support late attachment without replaying earlier patches.

The exact top-level fields are:

```text
version: 1
active: boolean
logical_size: [width, height]
ops: array
fog: null | {cells: integer, states: string}
```

Every operation has `kind` and `clip:[x,y,w,h]`. Its only other fields are:

| Kind | Fields |
|---|---|
| rect | rect, color, stroke, radius |
| ellipse | rect, color, stroke |
| circle | center, radius, color, stroke |
| line | points (exactly two), color, stroke |
| polygon | points, color, stroke |
| text | pos, size, text, color, bounds, fit (`shrink`, `clip` or `center`) |
| fog | rect |

Rectangles are `[x,y,width,height]`; points are `[x,y]`; colors are four integer RGBA bytes. Text is unabridged translated content constrained to its source-layout line box. Invisible measurement passes and empty effective clips emit no visible geometry.

Limits: 5 MiB payload; 4,096 operations; 4,096 UTF-8 bytes per text and 65,536 aggregate; 256 points per operation; fog grid 1–2,048 square cells with exactly `cells*cells` characters from `012`; logical dimensions 64–16,384; finite geometry magnitude at most 65,536; nonnegative sizes; stroke at most 64; positive text size at most 256; nesting at most 12. Decoders reject unknown/duplicate keys, malformed UTF-8, forbidden controls and raw NUL before JSON parsing.

## Native path

`armada::vector_hud::decode` validates a complete snapshot. `layout` uses the authenticated bundled `top_hud::FontAtlas`, native vector control symbols and the shared 24-byte vertex/shader layout. It CPU-clips triangles with UV interpolation and preserves operation order, including atlas/fog batch changes. Empty clips draw nothing.

Mesh limits are 65,536 vertices, 393,216 16-bit indices and 8,192 batches. Overflow rejects the whole candidate. The viewer installs geometry and its semantic-fog texture together only after successful decode/layout; malformed snapshots preserve the last good presentation. A valid inactive snapshot clears the slice. Transient buffers are checked for the complete slice before any of its batches are submitted.

Polygon and thick-stroke tessellation additionally shares a cumulative 4,000,000-unit processing budget, independent of visible output. Off-clip bounds reject cheaply; pair-intersection, sorting and slab work are reserved before their corresponding loops. Filled polygons use even-odd coverage; joined thick strokes use a nonoverlapping union so translucent edges do not accumulate alpha at joins.

The shared native atlas is rebuilt at actual drawable height. Native UI is view 2, below remaining/application overlay view 3; readback is view 4. Fog sampling is nearest/clamped. Python keeps the existing physical-to-logical input mapping.

## Reproduce

```sh
cmake --build render_cpp/build-w02 -j8
ctest --test-dir render_cpp/build-w02 --output-on-failure
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m pytest -q \
  tests/test_native_vector_hud.py tests/test_native_vector_integration.py tests/test_native_top_hud.py
SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy .venv/bin/python \
  tools/render/capture_native_top_hud_game.py --side-panels --out <scratch-output>
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python \
  tools/render/probe_native_vector_hud.py --out <scratch-pipeline-output>
# Additional vector-only/hud-only shader and alpha-compositing configuration:
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python \
  tools/render/probe_native_vector_hud.py --vector-only --out <scratch-vector-only-output>
```

The actual-main helper executes the unchanged production loop body with real SDL events and the normal embedded presentation call. It isolates persistence paths and uses a hidden real Cocoa/GL window. Its paired images share one paused match, selection and camera. It checks default activation, compact collapse/restore hitboxes, newly freed world input, unchanged minimap camera mapping, top-bar occlusion, pause/resume and unchanged simulation checksums during presentation-only controls. `--width 1280 --height 800` exercises the smaller application size.

A production-library pixel probe is pipeline evidence, not a replacement for actual-main delivery. Local macOS checks do not establish Windows/frozen-package acceptance, full-game performance targets, owner appearance approval or merge authorization.

Final local evidence is retained in `artifacts/native-side-hud/`: ordinary-main captures at 1280×800 and 2560×1440, English/Polish/German/Russian, collapse/restore, station scrolling, freed world input and minimap camera controls. Normal GPU snapshots pass at 1280×800, 1920×1080, 2560×1440 and 3840×2160; vector-only alpha/shader probes also pass at 1280×800 and 2560×1440. Small antialiased contacts are checked against the matching no-contact scene rather than requiring fully opaque color endpoints. Last-good tests settle valid restoration before publishing malformed records.

## World-anchored HUD elements

The placement banner, the placement ghost ring and crosshair, the construction ring with its
percentage and the floating sim messages (`Station complete`, rejections) are part of the same
layer. `HUD._native_layer()` opens a full-screen identity sink for them, so their logical
coordinates stay logical coordinates and C++ draws the glyphs at the drawable resolution instead
of the pygame overlay upscaling a bitmap font. Plates and anchors are still measured with pygame,
which keeps the layout identical on the fallback path when no native session is running.

Line weights are hairlines here: the ghost ring and crosshair use stroke 1 and the construction
progress is a filled annulus polygon (3 px band) rather than chords. U+2713 is a vector icon in
`vector_hud` because the atlas has no check glyph; U+2715 was already one. Text uses `fit=center`
inside a measured plate, so the native ink cannot drift out of its background.

Pipeline readback crops are in `artifacts/native-world-hud/`.
