# S05 — blocked engineering checkpoint

**S05 is not accepted or complete. No model approval has been transferred.**

The initial execution produced 102 exact prototype/generic frame pairs, all eight owner colours,
361 matching simulation hashes over 360 ticks, real combat and individually measured lamps/emitters.
That original publication is preserved byte-for-byte under `initial-run/`, including its original
107-entry file manifest and exact original harness. Its passing result applies to that execution.

The parent's full reproduction failed at `motion-0270-escort-close`: identical frozen draws differed
by **96 pixels / 99 colour channels, maximum delta 1**. Evidence is under
`attempts/parent-reproduction/`; `parent-reproduction.json` and the top-level `verification.json`
are authoritative for current status. The passing scoped code review did not include this failure.

## Bounded diagnosis

- The exact scene, digest, camera and parent's first image were reproduced. 500 further draws and
  500 immediate rereads remained identical; root cause remains unresolved.
- A same-format, actual 4×MSAA offscreen/explicit-resolve experiment retained production shaders,
  fog, dither and passes. Neither route reproduced the unstable pair.
- Default and FBO routes differed by 10,170 pixels (maximum delta 63), despite their matching exposed
  formats. **FBO capture is not accepted as a replacement, rebaseline or fix.**
- No threshold, warmup, quality or production code change was made to get a pass.

See `diagnosis/` for measured reports and frozen diagnostic-script records. Those scripts refer to
historical scratch paths and are forensic records, not the maintained reproduction command.

## Reproduction and tests

The maintained harness is `tools/diag_trio_generic_equivalence.py`. It now resolves pinned commits
independently of live HEAD, reads approved pins from the archived candidate and accepts guarded
`--scratch-root` / repeatable `--user-root`. Its capture logic and strict gates match the preserved
original AST; `reproducibility-fix-check.json` records the comparison.

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_trio_generic_equivalence \
  test_alliance_blender_trio test_alliance_blender_battleship \
  test_ship_material_passes test_asset_selection test_detmath

.venv/bin/python tools/diag_trio_generic_equivalence.py run \
  --output "$HOME/.hermes/cache/scratch/s05-new-reproduction"
```

The output must be a new directory. All **53 focused tests** pass; model validation is **34/34** and
runtime metadata reproduces. These are not a strict real-GL repeatability pass, native Windows
rendering/package acceptance, a full suite, or permission to merge/release/activate S11.

## Selected evidence

- `initial-run/review-sheet.png`: prototype / generic / legacy close views.
- `initial-run/owner-palette-sheet.png`: all eight supported owner colours.
- `initial-run/paired-motion.mp4`: five seconds containing 60 frames over twelve seconds of simulation.
- `initial-run/candidate/features-*.png`: feature-specific lamp/drive views.
- `initial-run/verification.json`: original successful run only, superseded for acceptance by the
  top-level blocked status.

Next gate: resolve the repeatability failure under the unchanged capture contract, or obtain an
explicit owner decision about a revised acceptance contract. Do not quietly infer a tolerance from
these measurements. Approved sources, runtime meshes, exporters, gameplay and renderer stay unchanged.
