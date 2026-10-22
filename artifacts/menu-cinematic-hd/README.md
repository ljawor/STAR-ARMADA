# Native 1440p startup battle cinematic

## Scope

Offline menu-movie replacement only. The gameplay renderer, simulation, approved
model catalogue, saves and video runtime dependencies are unchanged. The scene
uses the approved core mesh bytes at real class lengths; cinematic materials,
lighting, nebula, camera, weapons and shield treatment live in the offline tool.

## Owner appearance gate

The owner reviewed the native-resolution look through the actual startup
compositor and answered **“Approve this look—build the full animation”**.
`look-development/approval.json` preserves that wording, source/model pins and
three native probes. This approves the visual direction and full bake, **not**
merge, release, gameplay graphics or final playback acceptance.

The early look probes were captured from uncommitted authoring code. Their raw
Blender/helper SHA-256 pins are retained rather than falsely labelling them as a
committed capture. The full bake used the identical approved Blender script;
frame24's mean absolute RGB difference from the approved PNG was below0.002 per
channel. Final handover needs a committed candidate and a fresh actual-main
capture before owner playback/merge approval.

## Completed render and candidate audit

- Native **2560×1440**, 100% render scale, Blender5.0.1 EEVEE, 64samples.
- 384source frames completed under an independent process-group deadline;
  exit0, original authoring source hash unchanged.
- Final **360frames / 15seconds / 24fps**; smoothstep overlap loop.
- Delivery JPEG86, **4:4:4colour**, no resizing or AI upscaling. Every PNG/JPEG
  comparison exceeded the predefined42dBPSNR floor; minimum43.2017dB.
- Exact staged ZIP: **96,737,678bytes**, SHA-256
  `33fdd93e67ad66201ce9def49d6f9ba1cb5a2d502fee2ab1f14196e6fca93ae7`.
- All360 frames decoded through the actual pygame `MenuMovie` runtime. Local
  native decode mean4.92ms / p955.11ms / max11.72ms; cache retained22,118,400bytes,
  at most two frames. These are codec measurements, not interactive gameplayFPS.
- Last-to-first mean absolute RGB difference1.3998, below the predefined8 bound.
  Reduced Motion returned identical pixels at distinct elapsed phases.
- Full MP4 decoded successfully with ffmpeg; ffprobe read360frames at2560×1440
  and24/1fps. `full/preview.mp4` is a review copy, not the runtime asset.
- Real `main.py` startup capture at2560×1440, plus9 production SDL/OpenGL
  compositor captures across800×600,1280×800,1440×900 at start/middle/wrap.
  Navigation to main, Reduced Motion and cinematics-off moving-star fallback
  passed. Narrow windows deliberately cover-crop the cinematic; not every hull
  remains fully in-frame. Menus/logo remain readable.
- Focused CPU suite103passed,2 opt-in GPU/full-package tests skipped by default;
  additional menu/resolution/language regression suite24passed. The full bake,
  decode and compositor gates above were executed separately, not inferred from
  those skipped tests.

## Review and limitations

The first independent code review found two offline-tool issues: ffmpeg could
block before reaching its wait timeout, and an encoding report could overwrite
source/output images. The streaming helper now uses nonblocking pipes and one
encoding deadline; report paths are preflighted and exclusively created. CPU
regressions exercise stalled/early-exit encoders and source/output alias cases.
Independent re-review passed with no remaining security or logic findings;
its69 focused CPU tests passed. The optional extra publication-race regression
was suggested as coverage, not an unresolved implementation defect.

An initial fallback probe failed due to a NumPy comparison in the probe itself;
it was corrected to compare a copied array and rerun successfully. No failing
product result is hidden by that correction.

`full/scene.blend` is an editable still master; animation authority is
`tools/cinematics/blender_scene.py` plus its pinned plan and helper. Raw full PNG
sequences remain in scratch and are not duplicated in Git. Recorded paths in
historical receipts are capture locations, not portable build inputs.

Windows, Retina-specific device behaviour, frozen packages and the project-wide
long acceptance suite were not established by this local movie task. Owner final
playback approval and merge are pending. The verified ZIP is installed in this
feature checkout for that test; main/releases still retain the original movie.
