# Redesigned-fleet menu movie refresh

## 1. State

The complete refreshed movie is now installed in `assets/menu/battle.zip` on
`feat/skirmish-maps-spawn-selection`. The owner approved the look and authorized
full rendering/installation in `LOOK_APPROVAL.json`; final owner playback and merge
remain separate gates. Source geometry and the approved composition are unchanged.
See `full/audit.json` and `full/evidence-manifest.json` for measured delivery results.

The look-development receipts below are historical: they correctly record that the
old movie had not been replaced when those captures were reviewed.

## 2. Revision and evidence

Capture source revision: `71242a080964d204352a79bfd100d6e3206670c2`.
`look-development/scene-plan.json` pins all seven instances to the shipped default
visual-pack geometry, the same ordered selection as ordinary fresh game settings.
The previous cinematic resolved core assets without the default replacement packs;
all seven movie instances therefore used older revisions, not just the left fleet.
Camera, lighting, layout, samples, resolution and analytic motion are unchanged.
No ship source/runtime mesh, simulation, settings or save file was modified.

- `before-after.png`: source frame24 before/after; 482,642 pixels differ by more
  than12 RGB levels (13.0925% of3,686,400 pixels). This is a change measurement,
  not an appearance-approval threshold.
- `preview_00024.png`, `preview_00144.png`, `preview_00264.png`, `phase-sheet.png`:
  three2560×1440 renders,24fps sampling,64 EEVEE samples, pinned Blender5.0.1.
- `actual-main.png` / `actual-main.json`: real main.py startup compositor using
  an isolated review-only one-frame ZIP, native2560×1440. This proves composition,
  not completed animation or installation. User files isolated under scratch.
- `scene.blend`: editable still master; script + plan remain animation authority.
- `render-report.json`, `review.json`: raw source/mesh hashes and render receipts.
- Deadline receipts: both processes exited0 and were reaped; no timeout.
- `menu-refresh-tests-01.log`:106 passed,2 skipped,7 subtests passed. The skips are
  explicit opt-in fresh GPU/full-movie build tests, not established animation gates.
- Both original RED logs retained: old planner fails all seven revision comparisons;
  missing shared Blender pack-input validation fails before implementation.

## 3. Full delivery

All384 source frames rendered with the unchanged committed script/plan, Blender5.0.1,
64samples. Delivery is360frames/15seconds/24fps at2560×1440, no resize or frame drops.
The first quality86 package was rejected at104,306,254bytes by the unchanged
99,614,720-byte (95MiB) cap. Quality85 with4:4:4 passed:99,320,554bytes and minimum
42.64736dB across all384 PNG→JPEG comparisons, above the unchanged42dB floor.
All failed-attempt receipts remain in `full/`; neither acceptance bound was relaxed.

All360 frames decoded at native size and1440×900; native mean4.825ms/p955.152ms;
cache stayed at most2frames/22,118,400bytes. Last→first mean absolute RGB1.679,
below the existing5-level seam bound. Reduced Motion is identical across time;
the complete MP4 decodes. The nine real-GL compositor captures cover start/middle/
wrap at800×600,1280×800,1440×900, with Reduced Motion and natural splash→main.
Cinematics-off rendered at three phases without calling the decoder.

106 cinematic tests passed,2 opt-in GPU/full-bake tests skipped explicitly;
25 skirmish/layout/presentation regressions passed after installation. Direct384-frame
rendering and full package auditing are recorded separately, not claimed as those
skipped pytest invocations. Independent source review found no blockers.

PNG hashes at the three approved phases are not identical: decoded differences are
rounding-scale (maximum channel mean below0.00185), with zero pixels above12levels.
See `full/approved-phase-differences.json`; this is not a byte-identity claim.

`full/preview.mp4` is a derived local-only review copy, intentionally ignored by the
existing repo rule. `assets/menu/battle.zip`, script/plan, generated still master,
selected PNGs and all receipts are the reproducible committed delivery closure.
Regenerate using the documented render command, then the existing offline Python API
`encode_frames(full, encoded, quality=85)` and `assemble_movie(encoded, destination,
jpeg_quality=85, max_archive_bytes=95*1024*1024, provenance=<pinned render metadata>)`.
No runtime codec or dependency changed.

## 4. Remaining owner gate

Run ordinary `main.py` from this checkout and inspect the animated menu background.
Final owner playback acceptance and merge are not implied by look approval or the
machine gates. No merge/tag/release has been performed.
