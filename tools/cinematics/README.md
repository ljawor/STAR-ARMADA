# HD startup cinematic — offline authoring

This builds a native **2560×1440** menu movie from the game's approved core
ship meshes, with cinematic-only materials, lighting and effects. It does **not**
change the native gameplay renderer, gameplay models, simulation, or saves.
The scene is script-authoritative: `scene_spec.py` + `blender_scene.py` + a pinned
JSON plan reproduce the scene. The generated `scene.blend` is an editable still
master, not a replacement for the script's analytic animation.

## Build environment

- Project `.venv/bin/python` and its existing pygame dependency.
- Pinned Blender **5.0.1**. On the development Mac its binary is
  `/Applications/Blender.app/Contents/MacOS/Blender`.
- Optional offline Pillow: `uv pip install --python .venv/bin/python -r tools/cinematics/requirements.txt`.
- Optional local `ffmpeg`/`ffprobe` for an MP4 review copy, not for the game.
- An idle GPU. Close the game before rendering; do not run two render jobs or
  a native acceptance probe concurrently. Use an outer process-group deadline.

The game still decodes read-only JPEG ZIPs using pygame + stdlib. It imports
neither Pillow nor Blender and needs no additional video codec.

## Look development before the full render

Use a **fresh** output directory each time; the authoring tool refuses to
replace an existing `scene.blend` or write candidates under shipped `assets`.

```sh
OUT="$HOME/.hermes/cache/scratch/menu-cinematic-hd"
mkdir -p "$OUT"
.venv/bin/python -m tools.cinematics.scene_spec --out "$OUT/plan.json"
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/cinematics/blender_scene.py -- \
  --plan "$OUT/plan.json" --out "$OUT/look" --frames 24,144,264 --samples 64
```

Inspect the actual PNGs, then capture the proposed still through real `main.py`
with `verify_preview.py --movie <review-only-still.zip> --out <fresh-directory>`.
The probe uses isolated settings/saves and verifies the 2560×1440 host viewport,
menu surface and final GL readback. A one-frame review ZIP is clearly labelled
look-development-only: its constant loop is seamless but proves no animation.
Do not present a beauty render or three samples as the finished movie. Get owner
look approval before the expensive full loop.

## Full loop and delivery

After approval, run the same authoring command with `--out "$OUT/full" --frames all`.
It emits **384 source frames** (16 seconds at 24fps), exact-size PNGs, high-quality
source JPEGs, a generated `.blend` and a source/model-hash-pinned render report.
No source geometry or approved catalogue files are written.

Prepare separate delivery JPEGs without resizing, preserving 4:4:4 colour:

```sh
.venv/bin/python -m tools.cinematics.prepare_frames "$OUT/full" "$OUT/encoded" \
  --report "$OUT/encoding.json"
.venv/bin/python -m tools.cinematics.movie_pack "$OUT/encoded" "$OUT/battle.zip" \
  --jpeg-quality 86 --max-archive-mib 95 --preview "$OUT/preview.mp4"
```

The report path must be fresh, outside both input/output directories, and have
an existing parent. Preflight rejects image aliases before encoding; exclusive
publication also refuses files or symlinks that appear after preflight. MP4
encoding has one180-second deadline covering streaming, close and encoder exit,
with bounded stderr diagnostics and cleanup that preserves an earlier preview.

Use `--provenance '<JSON>'` (or the Python API) to embed the pinned scene plan and
render-code hashes in a release candidate. Every encoded PNG is checked at its
native dimensions and measured against its decoded delivery JPEG. The default
minimum PSNR is 42dB, JPEG quality86, no chroma subsampling and **zero resize
operations**. The 95MiB archive cap prevents an oversized GitHub object; lowering
resolution or dropping frames is not a substitute for this gate.

Packaging omits the first second from normal output and smoothstep-crossfades
the final second with that head. The resulting movie is **15 seconds / 360
frames / 24fps**, with a fixed frame180 for Reduced Motion. Normal delivery JPEG
bytes are copied without re-encoding; only crossfade frames are recompressed.
The ZIP is `ZIP_STORED` with bounded v1 metadata, JPEG SOF dimensions and each
frame checked by the actual `MenuMovie` decoder before atomic replacement.
Failures preserve the previous destination; predictable temporary path aliases
are never used.

Before installing the exact candidate into `assets/menu/battle.zip`, validate
all frames, the last-to-first seam, decoded detail, CPU decode/scale latency and
bounded cache bytes. Decode the MP4 completely with ffmpeg. Capture the finished
movie through the real startup compositor, test Reduced Motion and cinematics
off, then obtain owner playback acceptance before merging. MP4 is a review copy,
not the asset played by the game.

## Tests

```sh
TMPDIR="$HOME/.hermes/cache/scratch" .venv/bin/python -m pytest -q \
  --basetemp="$HOME/.hermes/cache/scratch/cinematic-tests" \
  tests/test_cinematic_scene.py tests/test_cinematic_pack.py \
  tests/test_cinematic_delivery.py tests/test_cinematic_encoding.py tests/test_menu_movie.py
```

The optional Pillow-only tests skip explicitly when the offline extra is absent.
The runtime playback tests continue to use pygame only. `test_menu_movie.py`
previously referenced the retired `tools/build_menu_movie.py`/legacy renderer;
its authoring tests now target this pipeline instead of resurrecting it.

Opt-in gates are distinct:
- `STAR_ARMADA_GL_TEST=1`: three fresh Blender look-development renders (despite
  the legacy flag/test name); requires pinned Blender and an idle GPU.
- `STAR_ARMADA_MOVIE_BUILD_TEST=1 STAR_ARMADA_CINEMATIC_FRAMES=<completed-full-directory>`:
  package, MP4-encode and exercise lazy playback of the completed PNG sequence.
  This is a packaging gate, **not** a hidden second full GPU rebake.

The full-suite, Windows, Retina-specific device behaviour and frozen-package
acceptance remain separate from local cinematic authoring and playback evidence.
