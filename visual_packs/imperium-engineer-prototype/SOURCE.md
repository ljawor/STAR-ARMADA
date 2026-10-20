# Engineering Corps Corvette — local appearance-review prototype

Original Blender-authored replacement for only `imperial:constructor`. The accepted Vigil, Command Center, Shipyard and Mining Station source/runtime bytes remain unchanged.

## Play

Run `Play Engineering Corps Corvette.command` from repository or local Desktop launcher. The real stock Imperial skirmish includes this unit; it is selected/framed on launch. All six original prototype packs are enabled. Saves/settings stay in the existing isolated playtest profile under `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`. The installed app and normal user data are not replaced.

Construction abilities, build rules, weapons and gameplay data remain unchanged.

## Authoring

- Blender 5.0.1: `tools/art/build_engineer_prototype.py`.
- Editable source: `art/blender/imperium_engineer_prototype.blend`.
- Metadata: `.venv/bin/python tools/art/package_flight_prototypes.py`.
- Existing six material roles and original binding envelope/scale; no global shader changes or proprietary assets.

Appearance pending. Keep the review pair local until owner review; no push/PR addition, merge or release authorized.
