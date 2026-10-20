# Galactic Imperium Command Center — visual prototype

A second original Blender-authored asset in the visible-first playtest, requested after the owner approved the Vigil Corvette's appearance. Replaces only `imperial:command_station`; the already reviewed Vigil mesh and all core approved assets remain unchanged.

## Play

Run `Play Imperium Command Center.command` from the repository (or its local Desktop launcher) to open the real game in a stock Imperial skirmish with the Command Center selected and framed. Both this pack and the Vigil pack are enabled. `Play Vigil Prototype.command` still starts focused on the Vigil, with the new Command Center also present in the match.

Test saves/settings remain beneath `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`, separate from normal user data. The installed application bundle is not replaced.

## Authoring

- Original design; no proprietary models or textures.
- Editable Blender source: `art/blender/imperium_command_prototype.blend`.
- Script-authoritative builder/exporter: `tools/art/build_command_center_prototype.py`, Blender 5.0.1.
- Pack metadata builder: `.venv/bin/python tools/art/package_command_prototype.py`.
- Six existing material roles, no global shader changes or new texture pipeline.
- Original command-station envelope, pivot, runtime scale and gameplay data retained.
- Command Center appearance review pending; the earlier Vigil approval does not approve this station.

Focused integration check: `PYTHONPATH=tests .venv/bin/python -m unittest test_vigil_prototype test_command_prototype -v`.

Actual-renderer pair: `.venv/bin/python tools/diag_vigil_prototype.py --subject command --out <fresh-scratch-directory>`.
