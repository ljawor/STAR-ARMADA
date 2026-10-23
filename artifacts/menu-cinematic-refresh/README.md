# Redesigned-fleet menu movie refresh

## 1. State

Look development only. The existing `assets/menu/battle.zip` remains byte-identical.
The owner's request is to update the video on the skirmish feature branch because
the left-hand ships were obsolete. It is not approval of the new capture or a merge.
Full 384-source-frame render, final 360-frame/15-second ZIP, playback audit,
installation, owner playback acceptance and merge remain pending.

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

## 3. Next gate

Owner approves or requests changes to the pictured look before the full GPU bake.
After approval, generate all384 frames using the identical committed script/plan,
encode/package without resizing, enforce42dB and95MiB gates, decode every frame,
verify seam/cache/decode latency and final actual-main composition. Install and
commit the exact audited ZIP on this branch; no merge/tag/release without approval.
