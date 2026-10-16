# Handoff: S00 approved prototype preservation

Status: in-progress — durable source checkpoint, not production integration acceptance.

## Scope and authority

The owner approved the battleship's Blender geometry/material captures and then the frigate/shipyard comparisons in this conversation on October 16, 2026. The owner subsequently authorized preserving this work in Git while merging performance separately. This checkpoint enumerates only `rebel_battleship`, `rebel_frigate` and Alliance-owned `shipyard`; it is not approval of the rest of the catalogue or a final default switch.

Base commit: `42e0348664fbba9b8432d749175edbe694c0ee48`.
Branch: `feat/blender-approved-trio-checkpoint`.
PR: draft; retrieve its current exact head with GitHub rather than relying on local scratch paths.

## Contents

- Three editable Blender files in `art/blender/`.
- Reproducible author/export scripts in `tools/art/` (Blender 5.0.1).
- Three runtime mesh exports in `assets/models/`.
- Authored loader, faction facade integration and material fixes.
- Focused regression tests and unselected-catalogue fingerprint fixture.
- Selected actual-game images/video and verification receipts in `artifacts/alliance_blender_trio/` and `artifacts/alliance_battleship_materials/`.
- `art/manifests/approved-trio-source-hashes.json` binds this checkpoint to preserved source bytes.

Approved runtime export hashes:

- Battleship: `57a5496c539a0252a237ef7a3671509f705308416da3f2afe0c9555ff17e9fec`.
- Frigate: `045d1383ac8a774d0bb9733a598ca83777dfcdc26645e6900b9d23ee7392348c`.
- Shipyard: `67d4db64c8677a8898f74d6e966a1b2476ffc721fd72c363ddbc992360630aaf`.

The authored sources are script-authoritative: rebuilding reconstructs scenes. Preserve manual `.blend` edits before running a generator. Read the build scripts and authoring README first.

## Existing verification, not new acceptance

Trio receipts record 79 focused tests, 181 equal per-tick combat hashes, 37 weapon events per variant, four individually visible yard lights, repeatable exports and 660 user-data files unchanged. The runtime model data and approved battleship hashes were read back by the parent before preservation.

These are the earlier captured candidate's results, not a full-suite run of this checkpoint. No Windows-native graphics, frozen packaging, paid-construction walkthrough, final performance or generic registry/mod acceptance is claimed. An earlier whole-suite LAN recovery tick mismatch remains not reproduced in isolated repetitions; it is not classified as fixed.

## Integration boundary and blockers

This draft preserves the current prototype, including its hardcoded authored-model activation and third draw-local renderer optimization. **Do not merge this draft as a final production/default migration.** Performance is being separated into PR #113. After that merges, update this draft against main without discarding the art/material portions.

S00 remains in progress until coherent source dependencies, approval records, README accuracy and preview/default boundary have been reviewed. S04 still owns generic registry/mod support and an explicit preview gate; S11 remains the final full-catalogue switch.

The old battleship README's initial “not approved/no material fixes” section is historical and superseded by this handoff and the later material/trio receipts. Update that README as part of completing S00.

## Next executable task

Read the main-branch roadmap and this draft's exact current head. Review the preserved prototype dependencies and material/asset integration; add the explicit preview boundary before any production art merge. Keep the three approved designs unchanged unless the owner reviews a new revision. Never depend on local scratch paths as the source of truth.

No merge, tag, release, user-data cleanup or broader catalogue approval is implied by this preservation checkpoint.
