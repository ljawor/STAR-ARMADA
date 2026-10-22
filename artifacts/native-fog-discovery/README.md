# Fog-of-war: reproduced stale native texture, then repaired

CPU gameplay sensors and the publisher already updated correctly. The actual live
native renderer received generations 1→2→3, but continued sampling the initial mask.
`createTexture2D(..., initialPixels)` creates an immutable texture in the pinned bgfx;
`Context::updateTexture` refuses later writes to it (bgfx.cpp createTexture2D,
bgfx_p.h updateTexture). A fresh viewer per mask hid the defect.

Repair: create the fog texture without initial memory, then upload its first pixels
via updateTexture2D; later same-size generations update the same mutable texture.
No sensor ranges, exploration rules, smoothing, fog colors or hidden-information
policy changed.

## Executed checks

- 13 CPU fog/discovery+codec tests passed: ship/station reveal, movement→charted
  ground, adding a station, live-ring republication, unchanged-cache behavior and
  enemy sensors not revealing our mask.
- Actual Metal standalone and one continuously running embedded renderer: nine
  world-point checks per path, three generations. Bright diagnostic floor controls
  ensure opaque/transparent cells are discriminating; no fabricated game frames.
- RED: fresh viewer path passed, live path failed with max channel error 155/255.
- GREEN: both paths passed; maximum live error 0.451/255, within the predeclared
  8/255 bound. New ship position clears, previous position becomes charted, added
  station clears its area, unknown control cell stays opaque.
- Viewer and library rebuilt; 13 native CTest checks passed.
- PNGs are losslessly re-encoded captures, not substitute artwork. The bright
  floor is a diagnostic fixture, not the game's intended space appearance.

`source-sha256.json` pins the tested files; raw bounded receipts and failure output
are retained. Independent fog-only review was requested separately. Existing WIP
host lifecycle/concurrency/packaging blockers remain open; this is not approval
of the entire renderer, Windows acceptance, or a shipped release.

Reproduce sequentially under a process-group deadline:

```sh
PYTHONPATH=tests SDL_VIDEODRIVER=dummy .venv/bin/python -m unittest test_native_fog_discovery test_render_fogmap -v
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/render/verify_native_fog_discovery.py --out "$TMPDIR/fog-proof"
```
