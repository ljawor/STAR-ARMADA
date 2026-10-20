# Vigil Corvette — visual prototype

One original Blender-authored visual replacement for `imperial:corvette` / Vigil Corvette. This is a review candidate, **not an approved catalogue revision**.

The original approved mesh, its Blender master, registry, approvals and release lock are unchanged. The pack contains data only and uses the existing supported six-role material pipeline; it does not add texture maps, alter global shaders or change gameplay statistics.

## Play

Run `Play Vigil Prototype.command` from the repository. It launches the real game directly into a stock Imperial skirmish, follows/selects a starting Vigil and enables this pack.

Preferences, saves and replays for this playtest are isolated beneath `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`. Normal source-checkout data and installed-application data are not changed. The installed `/Applications/STAR ARMADA.app` is not replaced.

The second starting Vigil also receives the replacement: the pack changes that ship type, not a single entity. All other hull/station bindings retain the core catalogue.

## Source and rebuild

- Editable source: `art/blender/vigil_prototype.blend`.
- Standalone, script-authoritative authoring/export: `tools/art/build_vigil_prototype.py` (Blender 5.0.1).
- After an intentional rebuild, regenerate pack metadata: `.venv/bin/python tools/art/package_vigil_prototype.py`.
- Focused integration checks: `PYTHONPATH=tests .venv/bin/python -m unittest test_vigil_prototype -v`.
- Actual-renderer comparison: `.venv/bin/python tools/diag_vigil_prototype.py --out <fresh-scratch-directory>`.

Original industrial sci-fi design; Homeworld serves only as a visual-quality reference. No proprietary model or texture is incorporated. Six roles, one mesh LOD, no textures. Appearance and fleet-scale performance acceptance remain pending.
