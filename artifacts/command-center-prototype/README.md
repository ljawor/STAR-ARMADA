# Galactic Imperium Command Center — directly playable visual specimen

## Result

Original Blender-authored orbital command fortress: stepped armored citadel and bridge, four massive bastions, open hangar mouths, truss links, radiator banks, grouped service details, restrained faction paint, warm windows and small sensors. Uses the existing production renderer and six material roles; no global shader or gameplay change.

11,012 triangles / 6,632 vertices / 563 editable parts. Previous core command station: 2,184 triangles. This is a visible-quality experiment, **not a fleet-performance claim**. Owner appearance review is pending; the Vigil's approval does not approve this station.

## Play

`Play Imperium Command Center.command` starts a real stock Imperial skirmish, selects/frames the starting Command Station, and enables both prototypes. The Desktop shortcut points to the same launcher. The original Vigil launcher still focuses the Vigil and now includes the Command Center in the match.

Uses the existing isolated `~/Library/Application Support/STAR ARMADA/Vigil Prototype/` profile. Normal app, saves and settings remain untouched. The approved-look Vigil mesh remains byte-identical.

## Evidence and focused checks

- Producing code commit and renderer/source/runtime hashes: `provenance.json`.
- `before-after.jpg`: equally cropped close/rear comparisons from the real GL renderer; full-resolution PNGs are beside it and in `full-resolution-pairs.zip`.
- `report.json`: close/rear/tactical pairs, same cameras, 4× MSAA, unchanged simulation digest. Changed pixels respectively: 103,566 / 102,139 / 18,308; these are visual differences, not frame-rate measurements.
- `gameplay.png` and `gameplay.json`: real main-loop startup, selected station, both packs accepted, usable production HUD.
- `PYTHONPATH=tests .venv/bin/python -m unittest test_vigil_prototype test_command_prototype -v`: 3 focused tests passed. Exercises real pack loading, exact station-only override, unchanged Vigil, unaffected siblings, return to core, and isolated profile setup.
- Existing normal user-data snapshot remained unchanged after verification.

No full suite, package rebuild or fleet benchmark was run during this bounded visual iteration. No merge or release authorized.
