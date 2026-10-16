# S05 bounded same-quality FBO diagnostic

## Outcome

**No discriminating causal evidence for the original frozen-repeat failure. No fix accepted; E2 remains incomplete.** Both default framebuffer and explicit-resolve FBO were stable in this bounded run. FBO output is measurably different from default output and is not a byte-identical replacement.

Only this scratch directory was written. No repository/harness/game/render/assets/tests edits, commits, pushes, tolerance changes, or production settings changes.

## Recipe and quality

Fresh serial processes used immutable parent source snapshots at control `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c`, candidate `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c` preview, and candidate legacy selection as negative control. The original harness was executed in memory without editing it, preserving initial views, palette, restored feature-ablation history, simulation commands and every six-tick motion capture through tick 270 (87 frames per variant). Then 30 draws per route alternated order, with no added warmup. Each draw had an immediate second readback. Full history remained default-backed; FBO was introduced only at tick 270.

Exact tick-270 state: `f064a052365d0035ae653c13fc9dd811a8ea3df3590d6de7da1ee8e1cdae2f86`. Camera/matrices are recorded in per-variant measurement.json. The candidate default capture is byte-exact equal to the original failing pair's FIRST image. Control/candidate camera matrices agree. All simulation draws retained state digest equality.

Queried Apple M4, OpenGL `2.1 Metal - 90.5`, actual default 1280x800, RGBA 8/8/8/8 unsigned-normalized linear encoding, depth 32 unsigned-normalized, stencil 0, sample buffers 1, samples 4. Extensions and callable EXT entrypoints were checked before use; no unsupported core call guessing. Driver MAX_SAMPLES_EXT = 4.

Allocated complete EXT multisample FBO with RGBA8 and DEPTH_COMPONENT32 renderbuffers. Actual attachment sizes, types, dimensions, internal formats and actual samples=4 were queried and asserted. Both FBOs asserted GL_FRAMEBUFFER_COMPLETE_EXT. Resolve uses explicit glBlitFramebufferEXT COLOR_BUFFER_BIT/NEAREST into a single-sample RGBA8 FBO. Production GLSL materials, normal fog, all passes, GL_DITHER, depth test and multisampling remained enabled. Each route asserts samples=4/depth=32/dither/MSAA before drawing. The single-sample resolve destination is not a reduction of rendering quality.

Default framebuffer does not expose a named sized internal-format token or guarantee identical sample locations to a renderbuffer. Matching exposed component type/encoding/bit depth and sample count therefore does not prove identical implementation-internal layout.

## Measured matrix

| Source | Route | Additional draws | Consecutive comparisons | Failed repeat comparisons | Immediate rereads | Failed rereads |
|---|---|---:|---:|---:|---:|---:|
| control | default | 30 | 29 | 0 | 30 | 0 |
| control | FBO | 30 | 29 | 0 | 30 | 0 |
| candidate | default | 30 | 29 | 0 | 30 | 0 |
| candidate | FBO | 30 | 29 | 0 | 30 | 0 |
| legacy | default | 30 | 29 | 0 | 30 | 0 |
| legacy | FBO | 30 | 29 | 0 | 30 | 0 |

Total 180 additional sampled draws, 174 consecutive same-route comparisons, 180 immediate rereads. One image hash per source/route. The final restoration-verification default draw per source is separate from this matrix.

| Comparison, tick 270 | Changed pixels | Changed RGB channels | Max channel delta |
|---|---:|---:|---:|
| control vs candidate, default | 0 | 0 | 0 |
| control vs candidate, FBO | 0 | 0 | 0 |
| control vs legacy, default | 126128 | 284586 | 246 |
| control vs legacy, FBO | 126108 | 284490 | 246 |
| default vs FBO, control/candidate | 10170 | 26872 | 63 |
| default vs FBO, legacy | 8620 | 22693 | 67 |

Per-variant before/after settings match exactly: read/draw FBO zero; default read/draw GL_BACK; 4 samples; 32-bit depth; viewport; color sizes; dither; MSAA; depth test. Cleanup rechecked default restoration after deleting owned FBO/renderbuffers. Source manifests preserved in all three processes. All GL-error assertions passed.

## Interpretation and safe next step

Negative legacy control discriminates model paths, and same-route control/candidate equality holds for this measured frame. That is output-route comparison evidence, **not** proof the FBO cures the original intermittent 96-pixel/99-channel/max-1 failure. The default route did not fail here either. The stable route-to-route difference is a separate phenomenon; this experiment does not identify its exact originating mechanism or pass.

Do not replace the production capture route, rebaseline reference frames, disable dither/MSAA/passes, add warmup, loosen equality, or close E2. Retain the original failing pair. If further diagnosis is authorized, instrument a genuinely failing default pair with matched state/GL metadata and paired explicit-resolve output; obtain a failing-vs-stable discriminator before considering an engineering change. No further GL work started here.

## Evidence

- `result.json`: aggregated matrix, pixel metrics, source revisions, original-first comparison, history hash comparisons, explicit E2/causal flags and limitations.
- `driver-query.json`, `query.py`, `query.log`: first query, extension/function availability and driver limit.
- `experiment.py`: complete scratch-only in-memory instrumentation; `aggregate.py`: deterministic metric aggregation.
- `{control,candidate,legacy}/measurement.json`: attachments, quality, camera/state, each draw/reread metric/hash and restoration receipts.
- `{control,candidate,legacy}/summary.json`: original harness report/history/source seal. Status `failed` with `BoundedStop('bounded measurement complete')` is the deliberate bounded exit, not an unstable pair; use measurement.json for diagnostic completion.
- `{control,candidate,legacy}/{default,fbo}-first.png` and `.npy`; `default-restored.png`; `route-difference-x8.png`.
- `contact-sheet.png`: inspected actual captures; aligned upright full scenes with planet/background/shields and distinct legacy hull, no blank route. Pixel identity rests on arrays, not visual judgment.
- `{control,candidate,legacy}.log`: complete process output.

## Commands (cwd `/Users/lukaszjawor/.hermes/cache/scratch/star-armada-s05`)

```sh
.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-fbo-diagnosis/query.py
.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-fbo-diagnosis/experiment.py control
.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-fbo-diagnosis/experiment.py candidate
.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-fbo-diagnosis/experiment.py legacy
.venv/bin/python /Users/lukaszjawor/.hermes/cache/scratch/s05-fbo-diagnosis/aggregate.py
```

All exited 0. Initial query was extended only in this scratch script to additionally query attachment component type/encoding before allocating any FBO. No acceptance suite or production changes were attempted.
