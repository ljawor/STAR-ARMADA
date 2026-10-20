# Imperial Mining Station — local appearance-review prototype

Original Blender-authored model, replacing only `imperial:mining_station` in this data-only pack. The accepted Vigil and Command Center source/runtime bytes remain unchanged.

## Play

Run `Play Imperial Mining Station.command` (repository or local Desktop launcher). All four original prototype models are enabled in the existing isolated playtest profile. For immediate visual review only, this launcher uses a disposable copy of the stock map with one extra prebuilt Mining Station for the local player. Normal construction/economy rules and source map data are unchanged. Other launchers still use the stock starting fleet.

Profile: `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`. Normal saves/settings and installed application are not replaced.

## Rebuild

- Blender 5.0.1: `tools/art/build_mining_prototype.py`.
- Editable master: `art/blender/imperium_mining_prototype.blend`.
- Metadata: `.venv/bin/python tools/art/package_industry_prototypes.py`.
- Six existing material roles; original binding envelope/scale, no shader or gameplay data changes.

Appearance pending. Keep these additions local until owner review; no push/PR update, merge or release authorized.
