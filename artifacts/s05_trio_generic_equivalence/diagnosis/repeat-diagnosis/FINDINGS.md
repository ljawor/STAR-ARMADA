# S05 frozen-repeat diagnosis — unresolved, bounded investigation

No production/game/render/assets/harness/test source edited. Only this diagnosis directory was written. No tolerance or quality change; no offscreen-FBO experiment run.

## Measured

- Original failed PNG pair independently confirms 96 pixels / 99 RGB channels / maximum absolute delta 1, bbox [21,10,861,315] (top-left PNG coordinates). `failed-mask.png` and `failed-region.png` retain spatial evidence. Differences are distributed over the upper/background planet and left-hand distant ship, not the central approved escort hull. Spatial attribution is not a proven originating pass.
- A direct simulation replay to exact tick 270 reaches state SHA256 `f064a052365d0035ae653c13fc9dd811a8ea3df3590d6de7da1ee8e1cdae2f86`, equal to the failed parent state. Camera target [-3706.044178793169,0,2685.5466055940738], distance 155, yaw 61.5, pitch 35; view/projection matrices equal to the full-history replay.
- The replay's RGB output is byte-exact equal to parent's FAILED first image and differs by 96 pixels from parent's FAILED repeat. Thus the scene/state was actually reproduced, not merely approximated.
- `run1/result.json`: 20 additional frozen draws and 20 immediate rereads all equal; four subsequent full frames with readbacks at 12 production pass boundaries also stable. Pass readbacks do perturb synchronization and are diagnostic only.
- `run2/result.json`: 500 additional frozen draws and 500 immediate rereads all equal. Same first image as run1. Simulation digest checked before/after each draw; no GL error; immutable source manifest preserved.
- `exact1/summary.json`: original harness executed in memory with ONLY bounded-stop/failure-diagnostic additions; retained original initial-view/palette/feature-ablation/motion history and peer comparison. All 87 sampled frames through tick 270 have zero differing pixels vs parent control; tick-270 frozen pair stable. Exited deliberately with SystemExit at 270; summary status `failed` is this bounded diagnostic stop, not a repeat instability.
- Actual quality retained: 1280x800, 4 samples / 1 sample buffer, production GLSL available, normal render.fog, GL_DITHER enabled; Apple M4, OpenGL `2.1 Metal - 90.5`, cocoa driver. No passes removed. Source manifest preservation true in both probes and exact replay.

## Renderer paths inspected

`render/renderer.py`: draw/_draw_read_only 419-515 clears color/depth each frame and freezes animation when diff_render=True; camera.apply resets projection/modelview (render/camera.py 90-107). Planet surface and additive atmosphere 968-1018; production shader/uniform scopes render/fleet_materials.py 104-131,188-203. Shield history mutation 3689-3745 updates presentation caches even at dt=0, but observed stable repeats do not demonstrate that mutation causing the failure. No application FBO/resolve calls found in renderer; this harness reads the default multisampled back buffer with glReadPixels after glFinish, without swaps.

At the original 96 changed pixel locations, incremental stable-frame pass snapshots indicate planet pass affects 66, ship pass 28, shield pass 86 (overlap is expected). Last observed RGB-changing pass is shield for 86 and ship for 10. This is NOT enough to assign cause to shields: preceding RGB differences could simply be composited by the shield pass. Captures reside in run1/stage*.png. No quality/pass ablation used.

## Conclusion / recommendation

Root cause remains unresolved. Real original instability exists, but neither a shortened replay nor the original full history through the exact failure reproduced it; 500 additional frozen draws and rereads stayed stable. Evidence does not justify asserting dither, precision, driver shader recompilation, resolve, or renderer-history caches as the specific cause. Do not change production code, increase warmups, weaken equality or report this as an acceptance pass.

Next discriminating experiment, requiring a separate explicit measurement decision: dual capture of the same full production draws into a measurement-only offscreen framebuffer with the SAME 4xMSAA, color/depth formats, production materials and passes plus explicit resolve, alongside the existing default framebuffer. Instrument GL state/matrices/uniforms and per-pass outputs when a bad pair actually occurs. This would separate window-backed implicit resolve/presentation behavior from draw-level divergence; it is a proposal, not performed or accepted here.

## Executed commands (repo cwd)

`.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/probe.py run1 > /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/run1.log 2>&1`

(The probe was then extended from 20 to 500 diagnostic repeats; current probe.py is that version.)

`.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/exact_probe.py > /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/exact1.log 2>&1`

`.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/probe.py run2 > /Users/lukaszjawor/.hermes/cache/scratch/s05-repeat-diagnosis/run2.log 2>&1`

Spatial/readback details: spatial-analysis.json, run1/result.json, run2/result.json, exact1/summary.json and exact1/stopped-at-270.json. No acceptance suite/benchmark run.
