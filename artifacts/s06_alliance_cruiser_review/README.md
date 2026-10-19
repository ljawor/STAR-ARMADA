# S06 B1 — Liberty Cruiser specimen (pending owner approval)

## Authoritative corrected evidence

Use `fixed-review/capture/review-sheet.png`, `fixed-review/capture/paired-motion.mp4` and `fixed-review/capture/metrics.json`. The earlier `final/`, `attempt-02/` and `parent-run/` recipes incorrectly inherited focus-fire commands and selection from a shared scene helper; this orbit harness actually executed **no explicit commands** and rendered **empty selections**. The corrected full run records that truth. All 23 corrected PNGs are byte-identical to their earlier `final/` counterparts; mesh/master bytes are unchanged. Earlier evidence and failed review are retained, not rewritten.

Eleven focused tests now pass, including empty recipe metadata, same/relative/symlink/hardlink master-output protection and exactly four emitter centers bound to exported geometry. Corrected exporter reproduced identical runtime bytes twice with unchanged master; see `fixed-review/reproducibility.json`. Repeat/feature counts remain measurements, not formal S09 acceptance thresholds. The fix worker was interrupted after capture; parent recovered and verified outputs and completed bookkeeping.

## Delivered

Original Alliance `rebel:cruiser` / gameplay `rebel_cruiser` Blender specimen. Editable master is **blend-authoritative**: `art/blender/alliance_cruiser.blend`. No third-party meshes or textures. The seed recipe is initial authoring tooling only and refuses overwriting the master by default. Normal future rebuild/export must use `tools/art/export_alliance_cruiser.py`, not the seed.

Geometry: continuous chamfered pressure hull and crown, pointed stepped armor, low bridge bastion/window banks, deep keel, swept broadside batteries, two separated outrigger nacelles, broad machinery gutters and radiators, owner-painted recognition bands, four recessed cyan engines. Six existing engine material roles, evaluated Blender geometry and explicit double-precision per-triangle normals.

**No model appearance approval, registry approval, production binding, default cutover, commit or push.** Only the diagnostic tool injects candidate geometry in process. It first validates the entire candidate through the existing production `_load_profile`, then monkeypatches `render.asset_selection.mesh_for` for the already existing `rebel:cruiser` key, leaving all other bindings on the normal preview resolver. The patch is restored after capture; the ordinary resolver rejects/selects no cruiser replacement both before and after. No forged approved manifest or pack exists.

## Measured results

- Blender 5.0.1, resolved by the existing `model_pipeline.resolve_blender(load_pipeline())` mechanism (not a new hardcoded path).
- 6,264 evaluated triangles; 3,492 indexed vertices; 409,447 runtime bytes.
- Envelope exactly `[[-66,-11.265,-99.925],[66,19.3,97.5]]`, the legacy cruiser's full bounds. Same 197.425 nominal Z span and existing normalization: 160.300875 world-length, scale 0.8119583386095987. Gameplay radius stays 88; gameplay data untouched.
- Two export-only runs from one unchanged master: byte-identical runtime SHA-256 `38b4e9f92040e67ffc1655910de39c24de4156397a94c76c34f94738a383ba84`. Blend before/after SHA-256 `96cdcc024a304d317e7e95d6f096675322971c9671521338f248a140ddd77fd6`.
- Four focused tests pass, including five corruptions rejected by the real loader, six roles/normals/winding/bounds/budgets/metadata/features, export-only AST and four emitters x five clear aft rays. The buried-emitter negative control is obstructed for each engine. `test-red.txt` records the initial missing-specimen failure before authoring.
- Actual game renderer: 1280x800, actual four samples, production material shaders, ordinary fog/sensor handling, Apple M4 / OpenGL 2.1 Metal 90.5. No skip passes or material-debug fallback.
- Union-safe identical close, low aft, tactical and common-scale cameras; capital and escort context. All eight frozen baseline/candidate view repeats have **zero** changed pixels.
- Close before/after: 136,116 pixels differ by >3 RGB levels (13.2926% of frame); low rear 100,030; tactical 8,785; common scale 9,102. These are geometry/material/presentation differences, **not an automatic quality or silhouette acceptance score**. Derived shield bounds can also contribute; no claim that every changed pixel is hull geometry.
- Each named recessed engine separately ablated from its actual production material display-list path: 212 / 222 / 245 / 239 visible changed pixels, broad aft faces individually visible. Restoring full geometry reproduces the original rear frame exactly (0 changed pixels).
- Close material-role ablation: accent 2,481 changed pixels, of which 2,478 meet the documented blue-owner hue predicate; trim 13,746 changed; dark 3,397 changed. Existing player palette is `[0.35,0.65,1.0]`; no alternate paint or state alteration was used.
- Paired MP4 is 5.000 seconds, 150 frames, 30fps, 2560x800 (left legacy, right candidate). The two underlying movies each use real 1/30s simulation steps and the same orbit. All **150** per-frame precise state digests match baseline/candidate. Draw calls themselves assert state hashes unchanged.
- Source manifest and protected source/user-file hash inventory unchanged across capture. All five menu persistence paths isolated by the existing capture helper. This is Python write isolation, not a claim of native OS sandboxing.

## Review files

Primary owner sheet: `final/review-sheet.png` (aspect-correct).

Full-size: `final/before-close.png`, `final/after-close.png`, corresponding `*-rear.png`, `*-tactical.png`, `*-common-scale.png`.

Motion: `final/paired-motion.mp4`; `final/before-motion.mp4`; `final/after-motion.mp4`; `final/video-verification.json` contains ffprobe output. `final/motion-inspection.png` is a decoded once-per-second paired overview; `final/motion-all-frames-01.png` through `05.png` decode **every** candidate video frame into ordered close-cropped sheets.

Machine receipts: `final/metrics.json`, `final/motion-state-hashes.json`, `reproducibility.json`, `source-hashes.json`, `test-final.txt`, and raw build/export outputs. No approval record was changed.

## Actual commands exercised

From repository root:

```sh
# Initial seed only, already executed once; master exists so it now refuses.
# Blender executable obtained through the existing pipeline resolver:
python3 -c "from tools.art.model_pipeline import *; import subprocess; b=resolve_blender(cfg=load_pipeline()); assert blender_version(b)=='5.0.1'; subprocess.run([str(b),'--background','--python-exit-code','1','--python','tools/art/build_alliance_cruiser.py'],check=True)"

# Correct repeatable workflow for the blend-authoritative master (run twice):
python3 -c "from tools.art.model_pipeline import *; import subprocess; b=resolve_blender(cfg=load_pipeline()); assert blender_version(b)=='5.0.1'; subprocess.run([str(b),'--background','--python-exit-code','1','--python','tools/art/export_alliance_cruiser.py'],check=True)"

PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_cruiser -v
.venv/bin/python -m py_compile tools/art/build_alliance_cruiser.py tools/art/export_alliance_cruiser.py tools/diag_alliance_cruiser_review.py tests/test_alliance_blender_cruiser.py

# Fresh directory required; final exists, so choose another child to reproduce:
.venv/bin/python tools/diag_alliance_cruiser_review.py --out artifacts/s06_alliance_cruiser_review/reproduction
```

The harness writes the individual videos; the paired movie was assembled with ffmpeg hstack and ffprobe-verified. All log files use `.txt`, not ignored `.log`.

## Failed attempts and visual inspection

1. Initial shell discovery contained an unmatched parenthesis; corrected without any repository mutation.
2. An exploratory read imported a nonexistent `asset_selection.resolver`; removed that import, no production code change.
3. First evaluated export gave float32 representation `-99.925003`, just outside the deliberately strict original envelope. The initial loader check failed. Exporter now snaps only values within five millionths of an original envelope plane to that exact plane and recomputes normals afterward; no bound, cap or test tolerance was widened. Original `export-first.txt` retained.
4. `attempt-01` rejected the proposed low-rear camera because a contextual battleship was too near the eye. Moved that context ship for **both** variants (1850 -> 1600 Z), retained failed output, then reran the complete pair. No camera safety check bypassed.
5. `attempt-02` captured successfully, but its first contact sheet compressed image height. Final sheet preserves 1280:800 aspect ratio, adds per-role ablation, and reruns all captures/motion. The earlier artifact remains for honesty, not the final review sheet.

Inspected full-resolution candidate close/rear, both final sheets, paired decoded motion overview and all 150 decoded candidate frames. The new cruiser reads as a tapered medium armored spear with low bastion and separated drives, not the old three parallel tubes. Four aft emitters remain distinct; warm bridge and blue paint separate from the gray armor. No obvious hull geometry popping in the inspected ordered frames. This was decoded-frame inspection, not a claim of interactive native video playback or certified shimmer testing. Existing bright rectangular combat projectiles and a planet/background horizontal band are visible in both variants; neither is an asset fix or introduced renderer change, and neither was hidden by lowering quality.

## Remaining gates / ownership

Owner appearance approval is the next gate. Parent agent owns pending catalogue/pipeline/manifests/roadmap/handoff metadata; none was edited here. `build-model --asset rebel:cruiser` is not yet claimed registered/accepted. Parent must declare `authority: blend` and export-only script in pending metadata, never route rebuild through the seed. Production activation still requires the owner-approved revision record and later authorized cutover. No Windows authoring/native graphics, packaged acceptance, full suite or benchmark was attempted for this bounded specimen.
