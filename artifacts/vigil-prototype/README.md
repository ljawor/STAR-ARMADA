# Vigil — first visual prototype

User scope: improve Vigil Corvette visibly, put it in the real game for playtesting, and decide whether to extend the method only after this ship succeeds. No catalogue migration or fleet optimization is started here.

## What changed

Original Blender-authored industrial gun-corvette: layered armor, dark service trenches and vent banks, bridge visor/windows, defined gun turrets, restrained owner paint and hollow twin engine nozzles. The large cyan fin is gone. Six-role existing renderer, no global shader or gameplay changes. Editable source and standalone builder retained. This is a review prototype, not an approved revision of the original catalogue.

The pack replaces only `imperial:corvette`; the original approved `.blend`, mesh, registry, approval records and lock are unchanged. Geometry is 8,456 triangles versus the original 2,348: the visual experiment does not claim a fleet-performance win.

## Evidence

- `before-after.jpg`: equal crops from full-frame captures; before left / after right.
- `before/after-{close,rear,tactical}.png`: production GL captures with the same cameras, same simulation state and actual 4x MSAA.
- `report.json`: 57,725 / 51,772 / 3,784 changed pixels at close/rear/tactical views; unchanged simulation digest during both variants; near-identical declared drawn length within the original binding envelope.
- `gameplay.png` + `gameplay.json`: real `main.py` launch, stock skirmish, prototype accepted through the production settings seam, starting Vigil selected/followed, 12 normal composed frames and clean exit. This is not an interactive-FPS measurement.
- Two focused tests passed: real loader accepts the one-binding replacement and disables back to core; the directly playable launcher isolates its settings and normal saves remain byte-identical. The first build correctly failed strict unit-normal validation; exporter precision was corrected from eight to fifteen decimals before successful loading. No validator tolerance was weakened.
- 673 existing normal source/app save/replay files were hashed before and after the captures/verification: none changed. Playtest output is in a separate profile.

## Play

The repository launcher is `Play Vigil Prototype.command`. The local Desktop launcher with the same name invokes it. It starts the real current source game in a stock Imperial skirmish and selects/follows a starting Vigil. Ordinary input, construction and combat remain available.

Playtest data lives at `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`. The installed `/Applications/STAR ARMADA.app` was inspected and is version 0.5.1; it does not contain the current model system and was not modified. Use the prototype launcher rather than that older app for this review.

## Deliberately not claimed

No full-suite, package/release, native Windows graphics, dense-fleet timing, new texture pipeline or catalogue-wide appearance acceptance. No merge or release. The next gate is the owner's in-game judgement of this ship, not a validation campaign.
