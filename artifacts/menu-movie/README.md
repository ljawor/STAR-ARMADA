# Menu backdrop re-baked from the authored catalogue

The menu cinematic is a pre-rendered movie, so it kept showing the legacy models after S11 switched
the live renderer. This replaces the shipped movie with a bake of the same scene from the approved
Blender catalogue.

## Bytes

| | Old (legacy bake, 13 Oct) | New (authored bake) |
|---|---|---|
| bytes | 24,575,007 | **23,919,980** |
| sha256 | `fd0676a0b6af434520535cc7783dda44787d061df293e2e1c55140851a2102f2` | `ab715ab0ff508aff3f2d9b6f3c8c43b082eedd5d32333c4c72df189aeb83b0c5` |
| format | 1280×720, 24 fps, JPEG-in-ZIP | identical |

## How it was made

```
.venv/bin/python tools/build_menu_movie.py \
    --model-preview \
    --output-dir <fresh dir> \
    --asset <zip outside assets/> \
    --ffmpeg <ffmpeg>
```

The baker selects the catalogue through the same `render.asset_selection` seam the game uses, fails
closed on any fallback, and records its own provenance: `selection_policy: preview`, every entity's
binding, asset, revision and `runtime_sha256`, plus `code_sha256` for each renderer module it used.
`render-report.json` beside this file is that record.

| Check | Value |
|---|---|
| MSAA | 4 |
| GL errors across the full render | 0 |
| loop seam (mean abs RGB) | 1.39 |
| render + encode | 26.3 s |
| scene | unchanged from the original bake: 2 Imperial capital hulls, 3 Rebel hulls, same camera move |

## Verification

- `pytest tests/test_splash_movie_integration.py tests/test_menu_movie.py` → 38 passed, 2 skipped.
- `pytest tests/test_s07_movie_provenance.py` → 15 passed (the movie's provenance gates accept this
  bake).
- Rendered the real splash surface offscreen against these shipped assets and inspected it:
  `splash-authored-1280x800.png` shows the plated hulls behind the title.

## Not changed

The scene, camera path, loop length, format and the runtime's decode path. Only the geometry source
changed. If the owner prefers a live-rendered menu instead of a baked movie, that is the separate
decision `E23` in `art/manifests/inventory_audit.json`, not this change.
